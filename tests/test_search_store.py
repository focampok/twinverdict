import asyncio

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from db.models import Job, MetricRow, PolicyRow, RunEvent, SearchRun
from db.session import get_engine
from llm.client import LLMClient
from llm.mock_server import app
from search.config import SearchConfig
from search.loop import run_search
from search.store import format_last, latest_done, persist_search

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE search_runs, runs, metrics, policies, jobs RESTART IDENTITY CASCADE")
        )


def _search():
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client = LLMClient(
        base_url="http://test/v1",
        model="mock",
        api_key="mock",
        concurrency=4,
        http_client=http,
    )
    config = SearchConfig.from_profile("smoke")

    async def _run():
        try:
            return await run_search(config, client, "base", 1, workers=1, holdout_seeds=0)
        finally:
            await client.aclose()
            await http.aclose()

    return asyncio.run(_run()), config


def test_short_search_is_queryable() -> None:
    result, config = _search()
    with Session(get_engine()) as session:
        job = Job(kind="search", status="done", params={"seed": 1, "N": 2, "K": 2, "R": 2})
        session.add(job)
        session.flush()
        run = persist_search(
            session,
            job.id,
            result,
            model="mock",
            config={"N": config.N, "K": config.K, "R": config.R, "model": "mock", "seed": 1},
        )
        session.commit()
        job_id = job.id
        run_id = run.id
    with Session(get_engine()) as session:
        stored = session.get(SearchRun, run_id)
        assert stored is not None
        assert stored.status == "done"
        assert stored.best_objective == result.best_objective
        assert stored.total_simulations == result.simulations_total
        assert stored.raw_json["rounds"][0]["prompt"]
        policies = session.scalars(select(PolicyRow).where(PolicyRow.job_id == job_id)).all()
        assert policies
        metrics = session.scalars(
            select(MetricRow).where(MetricRow.policy_id.in_([row.id for row in policies]))
        ).all()
        assert metrics
        events = session.scalars(
            select(RunEvent).where(RunEvent.job_id == job_id, RunEvent.event_type == "round")
        ).all()
        assert events
        assert "prompt" in events[0].payload
        assert format_last(latest_done(session)).startswith("best_objective=")


def test_rerun_marks_previous_search_superseded() -> None:
    result, config = _search()
    payload = {"N": config.N, "K": config.K, "R": config.R, "model": "mock", "seed": 1}
    with Session(get_engine()) as session:
        job = Job(kind="search", status="done", params=payload)
        session.add(job)
        session.flush()
        persist_search(session, job.id, result, model="mock", config=payload)
        persist_search(session, job.id, result, model="mock", config=payload)
        session.commit()
        job_id = job.id
    with Session(get_engine()) as session:
        rows = session.scalars(select(SearchRun).where(SearchRun.job_id == job_id)).all()
        assert sorted(row.status for row in rows) == ["done", "superseded"]
        assert session.scalar(select(func.count()).select_from(SearchRun)) == 2
