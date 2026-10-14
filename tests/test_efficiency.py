import json

import pytest

from eval.efficiency import (
    DEFINITIVE_NOTE,
    MOCK_NOTE,
    UNKNOWN_NOTE,
    bootstrap_ci,
    build_report,
    curve,
    improvement_target,
    loop_from_replay,
    loop_history,
    sims_to_fraction,
)
from policy.schema import fixed_rule_policy
from search.config import SearchConfig


def test_curve_is_sorted_and_non_decreasing() -> None:
    history = [
        {"sims_acumuladas": 300, "best_so_far": 0.5},
        {"sims_acumuladas": 100, "best_so_far": 0.2},
        {"sims_acumuladas": 200, "best_so_far": 0.4},
        {"sims_acumuladas": 400, "best_so_far": 0.3},  # baja: manda el máximo corrido
    ]
    points = curve(history)
    bests = [best for _, best in points]
    assert [sims for sims, _ in points] == [100, 200, 300, 400]
    assert bests == [0.2, 0.4, 0.5, 0.5]
    assert bests == sorted(bests)


def test_curve_accepts_the_per_candidate_field_and_collapses_repeats() -> None:
    assert curve([{"sims_acumuladas": 2, "objetivo": 0.7}]) == [(2, 0.7)]
    assert curve(
        [
            {"sims_acumuladas": 5, "best_so_far": 0.1},
            {"sims_acumuladas": 5, "best_so_far": 0.4},
        ]
    ) == [(5, 0.4)]


def test_sims_to_fraction_returns_the_first_crossing_or_none() -> None:
    points = [(10, 0.1), (20, 0.5), (30, 0.9)]
    assert sims_to_fraction(points, 0.1) == 10
    assert sims_to_fraction(points, 0.5) == 20
    assert sims_to_fraction(points, 0.95) is None


def test_improvement_target_sits_above_fixed_by_the_gap_fraction() -> None:
    assert improvement_target(0.25, 1.0) == 0.25 + 0.9 * 0.75
    assert improvement_target(0.25, 1.0, fraction=1.0) == 1.0


def test_fixed_rule_is_a_single_point_that_never_improves() -> None:
    points = curve([{"sims_acumuladas": 180, "best_so_far": 0.2489}])
    assert points == [(180, 0.2489)]
    assert sims_to_fraction(points, 0.5) is None  # plana: no alcanza un umbral mayor
    assert sims_to_fraction(points, 0.2) == 180


def test_loop_history_walks_the_persisted_rounds() -> None:
    payload = {
        "fixed_objective": 0.25,
        "policies": [{"n_seeds": 180}],
        "rounds": [
            {"sims_spent": 360, "evaluated": [{"objective": 0.5}, {"objective": 0.4}]},
            {"sims_spent": 180, "evaluated": [{"objective": 0.9}]},
        ],
    }
    rows = loop_history(payload)
    # Una ronda es un punto: las N candidatas se proponen juntas y luego se simulan.
    assert rows == [
        {"sims_acumuladas": 180, "best_so_far": 0.25},
        {"sims_acumuladas": 540, "best_so_far": 0.5},
        {"sims_acumuladas": 720, "best_so_far": 0.9},
    ]
    assert curve(rows)[-1] == (720, 0.9)


def test_bootstrap_ci_of_a_constant_is_that_constant() -> None:
    assert bootstrap_ci([0.5] * 10) == (0.5, 0.5)


def test_bootstrap_ci_brackets_the_mean() -> None:
    values = [0.1 * index for index in range(20)]
    low, high = bootstrap_ci(values)
    assert low < sum(values) / len(values) < high


def _config(**extra: object) -> dict:
    return {"N": 2, "K": 2, "R": 2, "profile": "smoke", "seed": 1, "scenario": "base", **extra}


def _write_results(directory, nofeedback_source: str = "mock", loop_source: str = "vllm") -> None:
    """Tres JSON mínimos del perfil smoke. Los dos métodos del LLM declaran fuentes
    distintas a propósito, para ver que cada uno se etiqueta con la suya."""
    policy = fixed_rule_policy().model_dump(mode="json", by_alias=True)
    (directory / "optuna_smoke_seed1_20261014.json").write_text(
        json.dumps(
            {
                "config": _config(llm_source="none"),
                "history": [{"trial": 0, "sims_acumuladas": 2, "best_so_far": 0.2}],
                "best_objective": 0.6,
                "fixed_objective": 0.2,
                "simulations_total": 2,
                "best_policy": policy,
            }
        )
    )
    (directory / "llm_nofeedback_smoke_seed1_20261014.json").write_text(
        json.dumps(
            {
                "config": _config(llm_source=nofeedback_source),
                "history": [{"batch": 0, "sims_acumuladas": 2, "best_so_far": 0.2}],
                "best_objective": 0.5,
                "fixed_objective": 0.2,
                "simulations_total": 2,
                "best_policy": policy,
            }
        )
    )
    (directory / "search_mock_20261014.json").write_text(
        json.dumps(
            {
                "config": _config(llm_source=loop_source),
                "seed": 1,
                "scenario": "base",
                "fixed_objective": 0.2,
                "best_objective": 0.7,
                "simulations_total": 4,
                "best_policy": policy,
                "policies": [{"n_seeds": 2}],
                "rounds": [{"sims_spent": 2, "evaluated": [{"objective": 0.7}]}],
            }
        )
    )


def _notes(report) -> dict[str, str]:
    return {method.name: method.note for method in report.methods}


def test_the_source_is_read_from_each_json(tmp_path) -> None:
    _write_results(tmp_path)
    # El perfil smoke tiene HOLDOUT_SEEDS=0, así que esto no simula nada: solo lee JSON.
    report = build_report(tmp_path, SearchConfig.from_profile("smoke"), 1, "base", None, 1)
    notes = _notes(report)
    assert notes["regla fija"] == DEFINITIVE_NOTE
    assert notes["Optuna TPE"] == DEFINITIVE_NOTE
    assert notes["LLM sin retroalimentación"] == MOCK_NOTE
    assert notes["bucle con retroalimentación"] == "vLLM real"
    assert report.llm_source == "derivado del JSON"


def test_the_flag_overrides_the_json(tmp_path) -> None:
    _write_results(tmp_path)
    report = build_report(tmp_path, SearchConfig.from_profile("smoke"), 1, "base", "mock", 1)
    notes = _notes(report)
    assert notes["bucle con retroalimentación"] == MOCK_NOTE
    assert notes["LLM sin retroalimentación"] == MOCK_NOTE
    assert report.llm_source == "mock"


def test_a_json_without_the_field_is_undeclared_not_guessed(tmp_path) -> None:
    _write_results(tmp_path)
    path = tmp_path / "search_mock_20261014.json"
    payload = json.loads(path.read_text())
    del payload["config"]["llm_source"]
    path.write_text(json.dumps(payload))
    report = build_report(tmp_path, SearchConfig.from_profile("smoke"), 1, "base", None, 1)
    assert _notes(report)["bucle con retroalimentación"] == UNKNOWN_NOTE


def _report(tmp_path, required: str | None):
    return build_report(
        tmp_path,
        SearchConfig.from_profile("smoke"),
        1,
        "base",
        None,
        1,
        require_llm_source=required,
    )


def test_requiring_vllm_passes_when_both_declare_vllm(tmp_path) -> None:
    _write_results(tmp_path, nofeedback_source="vllm", loop_source="vllm")
    assert _notes(_report(tmp_path, "vllm"))["bucle con retroalimentación"] == "vLLM real"


def test_requiring_vllm_aborts_when_a_run_came_from_the_mock(tmp_path) -> None:
    """Es el guardarraíl de la sesión GPU 2: con el túnel caído, abortar y no medir."""
    _write_results(tmp_path, nofeedback_source="mock", loop_source="vllm")
    with pytest.raises(SystemExit) as excinfo:
        _report(tmp_path, "vllm")
    assert "llm_source='vllm'" in str(excinfo.value)
    assert "LLM sin retroalimentación" in str(excinfo.value)


def test_without_the_requirement_any_source_passes(tmp_path) -> None:
    _write_results(tmp_path, nofeedback_source="mock", loop_source="mock")
    assert len(_report(tmp_path, None).methods) == 4


def test_loop_from_replay_feeds_the_curve() -> None:
    """El bucle de la sesión GPU 2 llega como replay congelado, no como JSON de search.loop."""
    replay = {
        "config": {"K": 180, "seed": 1, "scenario": "base", "profile": "default"},
        "run": {"total_simulations": 70000, "best_objective": 0.9},
        "fixed_metrics": {"train": {"objective": 0.2}},
        "best_policy": {"version": 1},
        "rounds": [
            {"sims_spent": 360, "objectives": [0.5, 0.4]},
            {"sims_spent": 180, "objectives": [0.9]},
        ],
    }
    adapted = loop_from_replay(replay)
    assert loop_history(adapted)[0] == {"sims_acumuladas": 180, "best_so_far": 0.2}
    assert loop_history(adapted)[-1] == {"sims_acumuladas": 720, "best_so_far": 0.9}
    assert adapted["simulations_total"] == 70000
