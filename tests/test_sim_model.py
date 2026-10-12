from policy.schema import fixed_rule_policy
from sim.config import PlantConfig
from sim.model import run_simulation


def test_day_long_run_finishes_and_keeps_wear_in_range() -> None:
    result = run_simulation(fixed_rule_policy(), seed=1, config=PlantConfig(horizon_min=24 * 60))
    assert result.orders_created > 0
    assert result.orders_completed > 0
    assert 0.0 <= result.wear_min <= result.wear_max <= 1.0
