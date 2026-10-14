import json
from pathlib import Path

import pytest

from policy.schema import fixed_rule_policy
from sim.calibration import (
    CALIBRATED_PATH,
    calibrated_plant_config,
    fit_failure_curve,
    load_dataset,
)
from sim.config import PlantConfig
from sim.runner import simulate

FIXTURE = Path(__file__).parent / "fixtures" / "ai4i_sample.csv"


def test_fixture_loads_with_normalized_wear() -> None:
    wear, labels, summary = load_dataset(FIXTURE)
    assert summary.rows == 200
    assert summary.wear_driven_events == int(labels.sum())
    assert 0.0 <= wear.min() and wear.max() == pytest.approx(1.0)
    assert set(labels) == {0.0, 1.0}


def test_labels_use_the_wear_driven_modes(tmp_path) -> None:
    """TWF y OSF cuentan; HDF, PWF y RNF son el fondo que no depende de la herramienta."""
    path = tmp_path / "mini.csv"
    path.write_text(
        "Tool wear [min],TWF,HDF,PWF,OSF,RNF\n"
        "10,0,0,0,0,0\n"
        "10,1,0,0,0,0\n"
        "10,0,0,0,1,0\n"
        "10,0,1,0,0,0\n"
        "10,0,0,1,0,1\n"
    )
    _, labels, summary = load_dataset(path)
    assert list(labels) == [0.0, 1.0, 1.0, 0.0, 0.0]
    assert summary.wear_driven_events == 2
    assert summary.background_events == 2


def test_missing_columns_are_rejected(tmp_path) -> None:
    path = tmp_path / "sin_columnas.csv"
    path.write_text("Tool wear [min],TWF\n10,0\n")
    with pytest.raises(SystemExit):
        load_dataset(path)


def test_fit_recovers_the_generator_parameters() -> None:
    """El fixture sale de midpoint=0.70 y steepness=20 sobre desgaste uniforme."""
    params = fit_failure_curve(FIXTURE)
    assert 0.0 < params.midpoint < 1.0
    assert params.steepness > 0.0
    assert params.midpoint == pytest.approx(0.70, abs=0.10)


def test_the_per_minute_level_is_not_calibrated() -> None:
    """AI4I no trae duraciones: el nivel sigue siendo un supuesto de planta."""
    assert fit_failure_curve(FIXTURE).base_per_min == PlantConfig().failure_base_per_min


def test_default_plant_is_the_calibrated_shape() -> None:
    """Corte del 14 oct 2026: PlantConfig ya nace con la forma de AI4I."""
    payload = json.loads(CALIBRATED_PATH.read_text())
    config = PlantConfig()
    calibrated = calibrated_plant_config()
    assert config.failure_midpoint == pytest.approx(payload["midpoint"])
    assert config.failure_steepness == pytest.approx(payload["steepness"])
    assert calibrated.failure_midpoint == pytest.approx(config.failure_midpoint)
    assert calibrated.failure_steepness == pytest.approx(config.failure_steepness)
    assert config.failure_base_per_min == tuple(payload["base_per_min"])
    assert calibrated.failure_base_per_min == config.failure_base_per_min
    assert calibrated.horizon_min == config.horizon_min
    assert calibrated.repair_cost == config.repair_cost
    assert payload["level_calibrated"] is False
    assert payload["previous"]["midpoint"] == pytest.approx(0.72)
    assert payload["previous"]["steepness"] == pytest.approx(14.0)


def _result(metrics: dict) -> dict:
    """Sin sim_wall_s: es tiempo de reloj, no un resultado de la simulación."""
    return {key: value for key, value in metrics.items() if key != "sim_wall_s"}


def test_calibrated_params_stay_deterministic_per_seed() -> None:
    config = calibrated_plant_config()
    policy = fixed_rule_policy()
    assert _result(simulate(policy, 7, config)) == _result(simulate(policy, 7, config))


def test_order_conservation_holds_with_calibrated_params() -> None:
    metrics = simulate(fixed_rule_policy(), 7, calibrated_plant_config())
    assert metrics["orders_created"] == metrics["orders_completed"] + metrics["orders_wip"]
