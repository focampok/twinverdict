import asyncio
import uuid

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
from search.freeze_run import freeze
from search.loop import run_search
from search.replay import load_replay, operator_card, replay_curve
from search.store import persist_search

pytestmark = pytest.mark.db

HOLDOUT_SEEDS = 2
KPI_KEYS = (
    "on_time_rate",
    "throughput",
    "unplanned_downtime_h",
    "planned_downtime_h",
    "maintenance_cost",
    "pm_count",
    "failures_total",
)


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE search_runs, runs, metrics, policies, jobs RESTART IDENTITY CASCADE")
        )


def _persist_short_run() -> uuid.UUID:
    """Corre una búsqueda smoke con holdout y la persiste. Devuelve el job_id."""
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
            return await run_search(
                config, client, "base", 1, workers=1, holdout_seeds=HOLDOUT_SEEDS
            )
        finally:
            await client.aclose()
            await http.aclose()

    result = asyncio.run(_run())
    with Session(get_engine()) as session:
        job = Job(kind="search", status="done", params={"seed": 1, "holdout": HOLDOUT_SEEDS})
        session.add(job)
        session.flush()
        persist_search(
            session,
            job.id,
            result,
            model="mock",
            config={
                "profile": "smoke",
                "seed": 1,
                "scenario": "base",
                "N": config.N,
                "K": config.K,
                "R": config.R,
                "llm_source": "mock",
                "holdout_seeds": result.holdout_seeds,
                "train_seeds": result.train_seeds,
            },
        )
        session.commit()
        return job.id


def test_load_replay_returns_the_minimal_keys() -> None:
    job_id = _persist_short_run()
    replay = load_replay(job_id)
    for key in ("job", "config", "run", "rounds", "policies", "best_policy", "curve"):
        assert key in replay
    assert replay["job"]["id"] == str(job_id)
    assert replay["rounds"] and all(item["prompt"] for item in replay["rounds"])
    assert replay["best_policy"] is not None
    # La curva arranca en la política 0 (la regla fija en K semillas), no en el mejor objetivo.
    first_sims, first_best = replay["curve"][0]
    assert first_sims == replay["config"]["K"]
    assert first_best == pytest.approx(replay["fixed_metrics"]["train"]["objective"])
    assert replay["curve"][-1][1] == pytest.approx(replay["run"]["best_objective"])


def test_replay_carries_holdout_and_stress_for_both_policies() -> None:
    """La tarjeta compara la regla fija con la mejor, así que las dos van completas."""
    replay = load_replay(_persist_short_run())
    for metrics in (replay["best_metrics"], replay["fixed_metrics"]):
        assert set(metrics) == {"train", "holdout", "stress"}
        assert metrics["holdout"]["n_seeds"] == HOLDOUT_SEEDS
        assert metrics["holdout"]["ci_low"] <= metrics["holdout"]["objective"]
        assert metrics["holdout"]["objective"] <= metrics["holdout"]["ci_high"]
    # El estrés usa las mismas semillas y el mismo número de ellas.
    assert replay["best_metrics"]["stress"]["n_seeds"] == HOLDOUT_SEEDS
    assert replay["fixed_metrics"]["stress"]["n_seeds"] == HOLDOUT_SEEDS


def test_rounds_carry_prompt_candidates_latencies_and_sims() -> None:
    replay = load_replay(_persist_short_run())
    k = replay["config"]["K"]
    for item in replay["rounds"]:
        assert item["prompt"]
        assert item["latencies_s"]
        assert item["sims_spent"] == len(item["valid"]) * k
        assert len(item["objectives"]) == len(item["valid"])
    # total_simulations = entrenamiento (la política 0 más las rondas) más las cuatro
    # evaluaciones de holdout y estrés, que van fuera del presupuesto.
    training = k + sum(item["sims_spent"] for item in replay["rounds"])
    assert replay["run"]["total_simulations"] == training + 4 * HOLDOUT_SEEDS


def test_every_card_number_comes_from_the_database() -> None:
    """Los números se recomputan desde `metrics` y tienen que coincidir uno a uno."""
    job_id = _persist_short_run()
    card = operator_card(load_replay(job_id))
    numbers = card["numbers"]
    with Session(get_engine()) as session:
        run = session.scalars(select(SearchRun).where(SearchRun.job_id == job_id)).one()
        fixed_row = session.scalars(
            select(PolicyRow).where(PolicyRow.job_id == job_id, PolicyRow.source == "fixed")
        ).one()
        kept = {"fixed": fixed_row.id, "best": run.best_policy_id}
        compared = 0
        for label, policy_id in kept.items():
            rows = session.scalars(select(MetricRow).where(MetricRow.policy_id == policy_id)).all()
            assert rows
            for row in rows:
                seed_set = row.seed_set
                assert numbers[f"objective_{label}_{seed_set}"] == pytest.approx(row.objective)
                assert numbers[f"objective_{label}_{seed_set}_ci_low"] == pytest.approx(row.ci_low)
                assert numbers[f"objective_{label}_{seed_set}_ci_high"] == pytest.approx(
                    row.ci_high
                )
                for key in KPI_KEYS:
                    if key in row.kpis:
                        assert numbers[f"{key}_{label}_{seed_set}"] == pytest.approx(row.kpis[key])
                        compared += 1
    assert compared > len(KPI_KEYS) * 2  # se comparó de verdad, no un caso suelto


def test_freeze_is_idempotent(tmp_path) -> None:
    job_id = _persist_short_run()

    def counts() -> tuple[int, int, int]:
        with Session(get_engine()) as session:
            return (
                session.scalar(
                    select(func.count()).select_from(PolicyRow).where(PolicyRow.job_id == job_id)
                ),
                session.scalar(
                    select(func.count())
                    .select_from(MetricRow)
                    .where(
                        MetricRow.policy_id.in_(
                            select(PolicyRow.id).where(PolicyRow.job_id == job_id)
                        )
                    )
                ),
                session.scalar(
                    select(func.count()).select_from(RunEvent).where(RunEvent.job_id == job_id)
                ),
            )

    before = counts()
    first = freeze(job_id, tmp_path)
    replay_first = first[0].read_text()
    card_first = first[1].read_text()
    second = freeze(job_id, tmp_path)
    assert first == second
    assert second[0].read_text() == replay_first
    assert second[1].read_text() == card_first
    assert counts() == before


def test_the_card_says_what_it_measures() -> None:
    card = operator_card(load_replay(_persist_short_run()))
    assert set(card) >= {
        "job_id",
        "fixed",
        "best",
        "objective_holdout",
        "winning_policy",
        "stress_note",
        "numbers",
    }
    assert card["winning_policy"]["dispatch_rule"] in {
        "EDD",
        "SPT",
        "WEIGHTED",
        "CRITICAL_RATIO",
    }
    assert "throughput" in card["stress_note"]


def test_replay_curve_is_monotone_in_sims() -> None:
    rounds = [
        {"sims_spent": 10, "objectives": [0.2, 0.5]},
        {"sims_spent": 10, "objectives": [0.4]},
    ]
    points = replay_curve(rounds, 0.1, 5)
    assert points == [[5, 0.1], [15, 0.5], [25, 0.5]]
