import baselines.optuna_search as optuna_search
from baselines.budget import total_train_sims
from baselines.optuna_search import run_optuna
from policy.schema import fixed_rule_policy, parse_policy
from search.config import SearchConfig
from search.loop import evaluate_policy


def _smoke() -> SearchConfig:
    return SearchConfig.from_profile("smoke")


def test_smoke_run_spends_the_whole_budget_and_respects_the_schema() -> None:
    config = _smoke()
    result = run_optuna(config, "base", 1, workers=1)
    assert result.simulations_total == total_train_sims(config)
    assert result.trials == total_train_sims(config) // config.K
    assert result.failed_trials == 0
    policy = parse_policy(result.best_policy.model_dump(mode="json", by_alias=True))
    assert policy.rules == []  # Optuna no escribe reglas condicionales
    if policy.dispatch.rule == "WEIGHTED":
        assert policy.dispatch.weights is not None
        assert abs(policy.dispatch.weights.total - 1.0) < 1e-9


def test_first_trial_is_the_fixed_rule() -> None:
    config = _smoke()
    result = run_optuna(config, "base", 1, workers=1)
    expected = evaluate_policy(fixed_rule_policy(), result.train_seeds, 1, "base", "test", 0)
    assert result.fixed_objective == expected.objective
    assert result.history[0]["objetivo"] == expected.objective
    assert result.history[0]["sims_acumuladas"] == config.K


def test_same_seed_gives_the_same_best() -> None:
    config = _smoke()
    first = run_optuna(config, "base", 5, workers=1)
    second = run_optuna(config, "base", 5, workers=1)
    assert first.best_objective == second.best_objective
    assert first.simulations_total == second.simulations_total


def test_invalid_trial_spends_nothing_and_does_not_stop_the_study(monkeypatch) -> None:
    config = _smoke()
    calls = {"n": 0}
    real_suggest = optuna_search.suggest_params

    def flaky_suggest(trial):
        params = real_suggest(trial)
        calls["n"] += 1
        if calls["n"] == 2:
            params["pm_M1"] = 2.0  # fuera del rango válido 0.30..0.95
        return params

    monkeypatch.setattr(optuna_search, "suggest_params", flaky_suggest)
    result = run_optuna(config, "base", 3, workers=1)
    assert result.failed_trials == 1
    # Si el trial inválido hubiera simulado, el total pasaría del presupuesto.
    assert result.simulations_total == total_train_sims(config)
    assert result.best_objective >= result.fixed_objective
