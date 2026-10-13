import uuid

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db.models import Job, SearchRun
from db.session import get_engine
from llm.client import LLMClient
from llm.mock_server import app
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


def test_worker_runs_search_job_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake(concurrency: int = 32) -> LLMClient:
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        return LLMClient(
            base_url="http://test/v1",
            model="mock",
            api_key="mock",
            concurrency=concurrency,
            http_client=http,
        )

    monkeypatch.setattr("worker.main.LLMClient.from_settings", _fake)
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
