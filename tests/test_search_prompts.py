"""El top-k que ve el modelo es el que el simulador distingue."""

import json

from policy.schema import Policy, parse_policy
from search.prompts import build_search_prompt, dedupe_top, simulator_key


class _Scored:
    def __init__(self, policy: Policy, objective: float) -> None:
        self.policy = policy
        self.objective = objective
        self.kpis = {
            "orders_completed": 10.0,
            "on_time_rate": 0.5,
            "unplanned_downtime_h": 1.0,
            "failures_total": 2.0,
        }

    def policy_json(self) -> dict:
        return self.policy.model_dump(mode="json", by_alias=True)


def _policy(
    rule: str = "SPT",
    *,
    version: int = 1,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
    max_pm: int = 2,
    rules: list[dict] | None = None,
) -> Policy:
    dispatch: dict = {"rule": rule}
    if weights is not None:
        dispatch["weights"] = weights
    return parse_policy(
        {
            "version": version,
            "maintenance": {
                "pm_wear_threshold": {} if thresholds is None else thresholds,
                "max_pm_per_shift": max_pm,
            },
            "dispatch": dispatch,
            "rules": [] if rules is None else rules,
        }
    )


_RULE = {
    "if": {"machine": "M1", "wear_gt": 0.6},
    "then": {"action": "PRIORITIZE_PRODUCT", "product": "P1"},
}


def test_dedupe_ignores_version_and_unused_weights() -> None:
    best = _policy("SPT", version=2, weights={"due_date": 0.5, "wear_risk": 0.5, "setup": 0.0})
    clone = _policy("SPT", version=3, weights={"due_date": 0.3, "wear_risk": 0.5, "setup": 0.2})
    other = _policy("EDD", max_pm=1)
    assert simulator_key(best) == simulator_key(clone)
    ranked = [_Scored(best, 0.87), _Scored(clone, 0.87), _Scored(other, 0.2)]
    chosen = dedupe_top(ranked, 5)
    assert len(chosen) == 2
    assert chosen[0].policy is best
    assert chosen[1].policy.dispatch.rule == "EDD"


def test_missing_threshold_matches_the_default() -> None:
    implicit = _policy("EDD", max_pm=1, thresholds={})
    explicit = _policy(
        "EDD",
        max_pm=1,
        thresholds={"M1": 0.75, "M2": 0.75, "M3": 0.75, "M4": 0.75, "M5": 0.75},
    )
    assert simulator_key(implicit) == simulator_key(explicit)


def test_weights_count_only_when_dispatch_reads_them() -> None:
    low = {"due_date": 0.2, "wear_risk": 0.2, "setup": 0.6}
    high = {"due_date": 0.6, "wear_risk": 0.2, "setup": 0.2}
    assert simulator_key(_policy("WEIGHTED", weights=low)) != simulator_key(
        _policy("WEIGHTED", weights=high)
    )
    assert simulator_key(_policy("CRITICAL_RATIO", weights=low)) != simulator_key(
        _policy("CRITICAL_RATIO", weights=high)
    )
    assert simulator_key(_policy("EDD", weights=low)) == simulator_key(_policy("EDD", weights=high))


def test_rules_and_pm_limit_are_part_of_the_key() -> None:
    base = _policy(rules=[_RULE])
    swapped = _policy(
        rules=[
            {
                "if": {"machine": "M2", "wear_gt": 0.6},
                "then": {"action": "PRIORITIZE_PRODUCT", "product": "P2"},
            },
            _RULE,
        ]
    )
    assert simulator_key(base) != simulator_key(_policy(max_pm=3, rules=[_RULE]))
    assert simulator_key(base) != simulator_key(swapped)


def test_prompt_asks_for_local_edits_and_shows_the_effective_threshold() -> None:
    policy = _policy(version=4, rules=[_RULE])
    prompt = build_search_prompt("base", [_Scored(policy, 0.871211)])
    assert "Sobre politica_1, haz de 2 a 4 cambios locales." in prompt
    assert "Puedes cambiar la regla de despacho, max_pm_per_shift y rules" in prompt
    assert "entre 0.30 y 0.95" in prompt
    assert "El ausente vale 0.75." in prompt
    assert "cerca de 0.95" in prompt
    assert "según la calibración" in prompt
    assert "Fija version=1." in prompt
    assert "kpis=" in prompt
    assert "fallas=" in prompt
    assert "Mantén el resto" not in prompt
    body = json.loads(prompt.split(" json=", 1)[1].split("\n", 1)[0])
    assert body["version"] == 1
    assert body["maintenance"]["pm_wear_threshold"] == {
        "M1": 0.75,
        "M2": 0.75,
        "M3": 0.75,
        "M4": 0.75,
        "M5": 0.75,
    }
    assert policy.version == 4
    assert policy.maintenance.pm_wear_threshold == {}


def test_free_prompt_asks_for_a_policy_distinct_from_the_top() -> None:
    prompt = build_search_prompt("base", [_Scored(_policy(), 0.5)], kind="free")
    assert "política libre y distinta al top-k" in prompt
    assert "max_pm_per_shift" in prompt
    assert "rules" in prompt
    assert "cerca de 0.95" in prompt
    assert "cambios locales" not in prompt
