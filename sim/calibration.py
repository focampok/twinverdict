"""Calibración de la curva desgaste → riesgo de falla con AI4I 2020.

Qué se calibra y qué no, en corto (el detalle está en docs/CALIBRATION.md):

- **Se calibra la forma**: `midpoint` y `steepness` salen de un ajuste por máxima
  verosimilitud sobre AI4I 2020.
- **No se calibra el nivel**: `base_per_min` sigue siendo un supuesto de planta. AI4I
  no trae duración por registro, así que no hay forma de convertir una probabilidad
  por registro en una tasa por minuto sin inventar esa duración. Se conserva el valor
  del simulador y se dice.

Los modos que se usan como etiqueta son TWF y OSF, los dos que en AI4I solo aparecen a
desgaste alto. HDF, PWF y RNF tienen tasa plana en todo el rango de desgaste, así que son
el fondo que no depende de la herramienta; el término `base` de la logística los absorbe.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from sim.config import PlantConfig

WEAR_COLUMN = "Tool wear [min]"
WEAR_DRIVEN_MODES = ("TWF", "OSF")
BACKGROUND_MODES = ("HDF", "PWF", "RNF")

# Cota del ajuste: sin ella el máximo verosímil se va a una escalera perfecta sobre las
# dos filas de desgaste 250-275 y el ajuste deja de describir nada.
STEEPNESS_MAX = 120.0

CALIBRATED_PATH = Path(__file__).with_name("calibrated_params.json")
SOURCE = "AI4I 2020 Predictive Maintenance (UCI 601), https://archive.ics.uci.edu/dataset/601"


@dataclass(frozen=True, slots=True)
class FailureParams:
    midpoint: float
    steepness: float
    base_per_min: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    rows: int
    wear_max_min: float
    wear_driven_events: int
    background_events: int
    sha256: str


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(path: Path | str) -> tuple[np.ndarray, np.ndarray, DatasetSummary]:
    """Desgaste normalizado a [0, 1] con su máximo observado, y la etiqueta de falla.

    Normalizar por el máximo observado es lo que alinea AI4I (0 a 253 min de
    herramienta) con el desgaste del simulador, que también vive en [0, 1].
    """
    wheel = Path(path)
    wear: list[float] = []
    labels: list[float] = []
    driven = 0
    background = 0
    with wheel.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [
            column
            for column in (WEAR_COLUMN, *WEAR_DRIVEN_MODES, *BACKGROUND_MODES)
            if column not in (reader.fieldnames or [])
        ]
        if missing:
            raise SystemExit(f"{wheel}: faltan columnas {missing}")
        for row in reader:
            wear.append(float(row[WEAR_COLUMN]))
            is_driven = any(row[mode] == "1" for mode in WEAR_DRIVEN_MODES)
            labels.append(1.0 if is_driven else 0.0)
            driven += int(is_driven)
            background += int(any(row[mode] == "1" for mode in BACKGROUND_MODES))
    if not wear:
        raise SystemExit(f"{wheel}: no trae filas")
    peak = max(wear)
    if peak <= 0.0:
        raise SystemExit(f"{wheel}: el desgaste máximo es {peak}, no se puede normalizar")
    summary = DatasetSummary(
        rows=len(wear),
        wear_max_min=peak,
        wear_driven_events=driven,
        background_events=background,
        sha256=sha256_of(wheel),
    )
    return np.asarray(wear, dtype=float) / peak, np.asarray(labels, dtype=float), summary


def probability(wear: np.ndarray, base: float, midpoint: float, steepness: float) -> np.ndarray:
    """P(falla | desgaste) = base + (1 - base) * sigmoide(steepness * (wear - midpoint))."""
    z = np.clip(steepness * (wear - midpoint), -60.0, 60.0)
    return base + (1.0 - base) / (1.0 + np.exp(-z))


def log_likelihood(
    wear: np.ndarray, labels: np.ndarray, base: float, midpoint: float, steepness: float
) -> float:
    p = np.clip(probability(wear, base, midpoint, steepness), 1e-12, 1.0 - 1e-12)
    return float(np.sum(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p)))


def _best_on_grid(
    wear: np.ndarray,
    labels: np.ndarray,
    bases: np.ndarray,
    midpoints: np.ndarray,
    steepnesses: np.ndarray,
) -> tuple[float, float, float, float]:
    best = (float("-inf"), 0.0, 0.0, 0.0)
    for base in bases:
        for midpoint in midpoints:
            for steepness in steepnesses:
                score = log_likelihood(wear, labels, float(base), float(midpoint), float(steepness))
                if score > best[0]:
                    best = (score, float(base), float(midpoint), float(steepness))
    return best


def fit_logistic(wear: np.ndarray, labels: np.ndarray) -> tuple[float, float, float, float]:
    """Máxima verosimilitud por rejilla: una pasada gruesa y otra fina alrededor.

    Sin scipy no hay optimizador; la rejilla es lenta pero auditable y determinista, y
    tres parámetros no dan para más. Devuelve (log-verosimilitud, base, midpoint, steepness).
    """
    coarse = _best_on_grid(
        wear,
        labels,
        np.arange(0.0, 0.061, 0.005),
        np.arange(0.60, 1.101, 0.01),
        np.arange(5.0, STEEPNESS_MAX + 1.0, 5.0),
    )
    _, base, midpoint, steepness = coarse
    return _best_on_grid(
        wear,
        labels,
        np.clip(np.arange(base - 0.006, base + 0.0061, 0.001), 0.0, None),
        np.arange(midpoint - 0.012, midpoint + 0.0121, 0.002),
        np.clip(np.arange(steepness - 6.0, steepness + 6.1, 0.5), 0.5, STEEPNESS_MAX),
    )


def fit_failure_curve(dataset_path: str | Path) -> FailureParams:
    """Ajusta la forma con AI4I y conserva el nivel por minuto del simulador.

    El `base` por registro del ajuste NO se usa como `base_per_min`: son unidades
    distintas (probabilidad por registro contra tasa por minuto). Ver el módulo.
    """
    wear, labels, _ = load_dataset(dataset_path)
    _, _, midpoint, steepness = fit_logistic(wear, labels)
    return FailureParams(
        midpoint=midpoint,
        steepness=steepness,
        base_per_min=PlantConfig().failure_base_per_min,
    )


def calibrated_plant_config(path: Path | None = None) -> PlantConfig:
    """PlantConfig con la forma calibrada. Los supuestos de planta no se tocan."""
    payload = json.loads((path or CALIBRATED_PATH).read_text())
    config = PlantConfig()
    return replace(
        config,
        failure_midpoint=float(payload["midpoint"]),
        failure_steepness=float(payload["steepness"]),
        failure_base_per_min=tuple(float(value) for value in payload["base_per_min"]),
    )


def write_params(
    path: Path,
    params: FailureParams,
    summary: DatasetSummary,
    base: float,
    likelihood: float,
) -> None:
    payload = {
        # Redondeado a 6 decimales: la rejilla deja ruido de coma flotante y la precisión
        # del ajuste es mucho más gruesa que eso.
        "midpoint": round(params.midpoint, 6),
        "steepness": round(params.steepness, 6),
        "base_per_min": [round(value, 6) for value in params.base_per_min],
        "fitted_base_per_record": round(base, 6),
        "log_likelihood": round(likelihood, 4),
        "source": SOURCE,
        "downloaded": datetime.now(UTC).strftime("%Y-%m-%d"),
        "csv_sha256": summary.sha256,
        "rows": summary.rows,
        "wear_max_min": summary.wear_max_min,
        "wear_driven_modes": list(WEAR_DRIVEN_MODES),
        "background_modes": list(BACKGROUND_MODES),
        "wear_driven_events": summary.wear_driven_events,
        "background_events": summary.background_events,
        "level_calibrated": False,
        "level_note": (
            "AI4I no trae duración por registro: no hay conversión de probabilidad por "
            "registro a tasa por minuto con soporte en los datos, así que base_per_min "
            "conserva el valor del simulador y queda como supuesto de planta."
        ),
        "previous": {
            "midpoint": PlantConfig().failure_midpoint,
            "steepness": PlantConfig().failure_steepness,
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/ai4i2020.csv")
    wear, labels, summary = load_dataset(dataset)
    likelihood, base, midpoint, steepness = fit_logistic(wear, labels)
    params = FailureParams(
        midpoint=midpoint,
        steepness=steepness,
        base_per_min=PlantConfig().failure_base_per_min,
    )
    write_params(CALIBRATED_PATH, params, summary, base, likelihood)
    print(f"filas: {summary.rows}  fallas por desgaste: {summary.wear_driven_events}")
    print(f"fondo sin desgaste: {summary.background_events} registros")
    print(f"base por registro: {base:.4f}")
    print(f"midpoint: {midpoint:.4f}  (antes {PlantConfig().failure_midpoint})")
    print(f"steepness: {steepness:.4f}  (antes {PlantConfig().failure_steepness})")
    print(f"log-verosimilitud: {likelihood:.2f}")
    print(f"escrito: {CALIBRATED_PATH}")


if __name__ == "__main__":
    main()
