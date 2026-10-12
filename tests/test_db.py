import threading
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from db.models import Job, MetricRow, PolicyRow
from db.session import get_engine
from worker.enqueue import enqueue
from worker.main import process_one

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE runs, metrics, policies, jobs RESTART IDENTITY CASCADE"))


def test_migration_applies() -> None:
    names = set(inspect(get_engine()).get_table_names())
    assert {"jobs", "policies", "metrics", "runs"} <= names


def test_enqueue_and_process_one() -> None:
    job_id = uuid.UUID(enqueue("baseline"))
    with Session(get_engine()) as session:
        assert process_one(session) is True
        job = session.get(Job, job_id)
        assert job is not None
        assert job.status == "done"
        policy = session.scalars(select(PolicyRow).where(PolicyRow.job_id == job.id)).one()
        metrics = session.scalars(select(MetricRow).where(MetricRow.policy_id == policy.id)).one()
    assert metrics.n_seeds == 10
    assert metrics.sims_spent == 10
    assert "throughput" in metrics.kpis


def test_concurrent_workers_do_not_take_the_same_job() -> None:
    first = uuid.UUID(enqueue("baseline"))
    second = uuid.UUID(enqueue("baseline"))
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            barrier.wait(timeout=10)
            with Session(get_engine()) as session:
                assert process_one(session) is True
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_run), threading.Thread(target=_run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    assert errors == []
    with Session(get_engine()) as session:
        jobs = list(session.scalars(select(Job).where(Job.id.in_([first, second]))))
    assert sorted(job.status for job in jobs) == ["done", "done"]
    assert {job.id for job in jobs} == {first, second}
