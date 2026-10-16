"""Una semilla, dos políticas, un JSON. El bucle de búsqueda no entra aquí."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from policy.schema import Policy, fixed_rule_policy, parse_policy
from sim.config import PlantConfig
from sim.kpis import kpis_from_result
from sim.model import SimResult, run_simulation

OFFICIAL_REPLAY = (
    Path(__file__).resolve().parents[1]
    / "bench/results/replay_285d1787-5d7c-464a-9897-4c585663f088.json"
)


def proposed_from_replay(path: Path) -> Policy:
    """La política ganadora está en el replay; la tarjeta solo trae el resumen."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    best = payload.get("best_policy")
    if not isinstance(best, dict):
        raise ValueError(f"{path} no trae best_policy")
    return parse_policy(best)


def _measured(result: SimResult) -> dict[str, float]:
    kpis = kpis_from_result(result, 0.0)
    del kpis["sim_wall_s"]
    kpis["on_time"] = float(result.on_time)
    kpis["unplanned_min"] = float(result.unplanned_min)
    return kpis


def record_policy(seed: int, policy: Policy, config: PlantConfig | None = None) -> dict:
    """KPIs e intervalos de una política en una semilla. Picklable para un ProcessPool."""
    cfg = PlantConfig() if config is None else config
    intervals: list[dict[str, float | str]] = []
    result = run_simulation(policy, seed, cfg, intervals)
    return {"kpis": _measured(result), "intervals": intervals}


def record_seed(seed: int, proposed: Policy, config: PlantConfig | None = None) -> dict:
    """Corre la regla fija y la política propuesta. No llama a simulate()."""
    policies = {
        name: record_policy(seed, policy, config)
        for name, policy in (("baseline", fixed_rule_policy()), ("proposed", proposed))
    }
    return {"seed": seed, "policies": policies}


def write_seed(
    seed: int,
    proposed: Policy,
    out_dir: Path,
    config: PlantConfig | None = None,
) -> Path:
    payload = record_seed(seed, proposed, config)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"intervals_{seed}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Graba intervalos de una semilla para la regla fija y la política del replay."
    )
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--replay", type=Path, default=OFFICIAL_REPLAY)
    args = parser.parse_args(argv)
    proposed = proposed_from_replay(args.replay)
    for seed in args.seeds:
        print(write_seed(seed, proposed, args.out))


if __name__ == "__main__":
    main()
