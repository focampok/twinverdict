import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from policy.schema import fixed_rule_policy, parse_policy, policy_json_schema

EXAMPLES = Path(__file__).resolve().parents[1] / "policy" / "examples"
EXAMPLE = json.loads((EXAMPLES / "example_v2.json").read_text())
FIXED = json.loads((EXAMPLES / "fixed_rule.json").read_text())


def test_example_validates_and_round_trips() -> None:
    policy = parse_policy(EXAMPLE)
    dumped = policy.model_dump(by_alias=True)
    assert parse_policy(dumped) == policy
    json.dumps(dumped)


def test_fixed_rule_file_matches_factory() -> None:
    assert parse_policy(FIXED) == fixed_rule_policy()
    fixed = fixed_rule_policy()
    assert fixed.dispatch.rule == "EDD"
    assert fixed.maintenance.max_pm_per_shift == 1
    assert fixed.rules == []
    assert all(fixed.maintenance.threshold_for(m) == 0.75 for m in ("M1", "M2", "M3", "M4", "M5"))


def test_weights_normalize_to_one() -> None:
    raw = json.loads(json.dumps(EXAMPLE))
    raw["dispatch"]["weights"] = {"due_date": 0.2, "wear_risk": 0.2, "setup": 0.2}
    policy = parse_policy(raw)
    weights = policy.dispatch.weights
    assert weights is not None
    assert weights.due_date == pytest.approx(1 / 3)
    assert weights.total == pytest.approx(1)


def test_schema_is_json_and_lists_dispatch_rules() -> None:
    schema = policy_json_schema()
    encoded = json.dumps(schema)
    for rule in ("EDD", "SPT", "WEIGHTED", "CRITICAL_RATIO"):
        assert rule in encoded
    assert "propertyNames" not in encoded
    threshold = schema["$defs"]["Maintenance"]["properties"]["pm_wear_threshold"]
    assert set(threshold["properties"]) == {"M1", "M2", "M3", "M4", "M5"}


@pytest.mark.parametrize(
    "mutate",
    [
        "six_rules",
        "threshold_too_high",
        "unknown_machine",
        "unknown_product",
        "unknown_action",
        "extra_field",
        "postpone_without_minutes",
        "empty_condition",
        "zero_weights",
    ],
)
def test_rejections(mutate: str) -> None:
    raw = json.loads(json.dumps(EXAMPLE))
    if mutate == "six_rules":
        raw["rules"] = raw["rules"] * 3
    elif mutate == "threshold_too_high":
        raw["maintenance"]["pm_wear_threshold"]["M1"] = 0.99
    elif mutate == "unknown_machine":
        raw["maintenance"]["pm_wear_threshold"]["M9"] = 0.7
    elif mutate == "unknown_product":
        raw["rules"].append(
            {"if": {"product_waiting": "P4"}, "then": {"action": "BATCH_SAME_PRODUCT"}}
        )
    elif mutate == "unknown_action":
        raw["rules"][0]["then"] = {"action": "SCRAP", "max_minutes": 30}
    elif mutate == "extra_field":
        raw["unexpected"] = 1
    elif mutate == "postpone_without_minutes":
        raw["rules"][0]["then"] = {"action": "POSTPONE_PM"}
    elif mutate == "empty_condition":
        raw["rules"][0]["if"] = {}
    elif mutate == "zero_weights":
        raw["dispatch"]["weights"] = {"due_date": 0, "wear_risk": 0, "setup": 0}
    with pytest.raises(ValidationError):
        parse_policy(raw)
