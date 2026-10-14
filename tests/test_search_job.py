import uuid

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config import Settings
from db.models import Job, SearchRun
from db.session import get_engine
from llm.client import LLMClient
from llm.mock_server import app
from search.repro import git_head
from search.store import format_last, latest_done
from worker.enqueue import enqueue
from worker.main import process_one

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE search_runs, runs, metrics, policies, jobs RESTART IDENTITY CASCADE")
        )


def _fake_client(concurrency: int = 32) -> LLMClient:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        concurrency=concurrency,
        http_client=http,
    )


def test_worker_runs_search_job_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("worker.main.LLMClient.from_settings", _fake_client)
    job_id = uuid.UUID(
        enqueue(
            "search",
            {"N": 2, "K": 2, "R": 2, "seed": 4, "workers": 1, "holdout": 0, "scenario": "base"},
        )
    )
    with Session(get_engine()) as session:
        assert process_one(session) is True
        job = session.get(Job, job_id)
        assert job is not None
        assert job.status == "done"
        run = session.scalars(select(SearchRun).where(SearchRun.job_id == job_id)).one()
        assert run.status == "done"
        assert run.total_simulations == 2 + 2 * 2 * 2
        assert "best_objective=" in format_last(latest_done(session))


def test_search_job_stores_repro_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("worker.main.LLMClient.from_settings", _fake_client)
    job_id = uuid.UUID(
        enqueue(
            "search",
            {
                "profile": "smoke",
                "seed": 4,
                "workers": 1,
                "holdout": 0,
                "scenario": "base",
            },
        )
    )
    with Session(get_engine()) as session:
        assert process_one(session) is True
        job = session.get(Job, job_id)
        assert job is not None
        run = session.scalars(select(SearchRun).where(SearchRun.job_id == job_id)).one()
        sha = git_head()
        for stored in (job.params, run.config):
            assert stored["N"] == 2
            assert stored["K"] == 2
            assert stored["R"] == 2
            assert stored["sim_workers"] == 1
            assert stored["model"] == Settings().LLM_MODEL
            assert stored["profile"] == "smoke"
            assert stored["train_seeds"] == [4, 5]
            assert stored["holdout_seeds"] == []
            assert stored["git_commit"] == sha
            assert stored["seconds_per_sim"] > 0
        summary = format_last(run)
        assert summary.startswith("best_objective=")
        assert "profile=smoke" in summary
        assert "sim_workers=1" in summary
        assert "train_seeds=4-5" in summary
        assert "holdout_seeds=-" in summary
        assert f"git={sha}" in summary
        assert "s/sim=" in summary
