"""Curva de eficiencia: mejor objetivo contra simulaciones gastadas, por método.

Cuatro métodos con el mismo presupuesto de entrenamiento: regla fija, Optuna, LLM sin
retroalimentación y el bucle con retroalimentación. Para cada uno se reporta cuántas
simulaciones necesita para llegar al umbral de mejora, fijado como

    target = fixed + 0.9 * (best_global - fixed)

donde fixed es el objetivo de la regla fija y best_global el máximo de los cuatro. El
umbral se define sobre la mejora y no sobre el objetivo, que no está acotado a 0–1.

El holdout de los ganadores (300 semillas desde 1_000_001, las de run_search) con IC 95%
por bootstrap queda FUERA del presupuesto de búsqueda: son 4 x 300 = 1_200 simulaciones
extra. El % a tiempo de cada método sale de ahí, recalculado desde su best_policy.

Cada curva usa la granularidad con la que ese método puede actuar sobre la información:
por trial en Optuna (cada trial ve los anteriores), por ronda o lote en el bucle y en el
LLM sin retroalimentación (las N candidatas se proponen juntas y después se simulan) y un
punto único en la regla fija.

Contra el mock, el bucle y el LLM sin retroalimentación NO son una medida del LLM: el mock
deriva cada política de la semilla y no lee el prompt. Optuna y la regla fija no pasan por
el LLM, así que sí son definitivos.

De dónde salieron las políticas se lee de `config.llm_source` en el JSON de cada corrida,
que `search/repro.py` deriva del endpoint (`LLM_BASE_URL`) y del puerto del mock. La bandera
`--llm-source` es solo un override para JSON viejos; contra vLLM no hace falta: basta con
correr sobre los JSON de esa sesión.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from config import Settings
from policy.schema import Policy, fixed_rule_policy, parse_policy
from search.config import SearchConfig
from sim.objective import composite_objective, load_objective_weights
from sim.runner import simulate_many

HOLDOUT_BASE = 1_000_000
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0
DEFAULT_FRACTION = 0.9

MOCK_NOTE = "mock, no es medida del LLM"
DEFINITIVE_NOTE = "definitivo"
UNKNOWN_NOTE = "origen sin declarar"


def llm_note(source: str | None) -> str:
    """Etiqueta de la tabla para un método que depende del LLM.

    La fuente sale del JSON de la corrida (`config.llm_source`, ver search/repro.py).
    Un JSON viejo, sin ese campo, se marca como sin declarar en vez de adivinar.
    """
    if source == "mock":
        return MOCK_NOTE
    if source == "vllm":
        return "vLLM real"
    return UNKNOWN_NOTE


def curve(history: list[dict]) -> list[tuple[int, float]]:
    """[(simulaciones, mejor hasta ahí)] ordenada por simulaciones y no decreciente.

    Acepta el historial de los tres formatos: `best_so_far` (Optuna, LLM sin
    retroalimentación) u `objetivo` (por candidata). Recalcula el máximo corrido, así
    que una entrada mal formada no puede producir una curva que baje.
    """
    points: list[tuple[int, float]] = []
    best = float("-inf")
    for row in sorted(history, key=lambda item: int(item["sims_acumuladas"])):
        sims = int(row["sims_acumuladas"])
        value = float(row["best_so_far"] if "best_so_far" in row else row["objetivo"])
        best = max(best, value)
        if points and points[-1][0] == sims:
            points[-1] = (sims, best)
        else:
            points.append((sims, best))
    return points


def sims_to_fraction(points: list[tuple[int, float]], target: float) -> int | None:
    """Primer cruce del umbral. None si el método nunca llega."""
    for sims, best in points:
        if best >= target:
            return sims
    return None


def improvement_target(
    fixed: float, best_global: float, fraction: float = DEFAULT_FRACTION
) -> float:
    """Umbral sobre la mejora, fijado antes de mirar quién gana."""
    return fixed + fraction * (best_global - fixed)


def bootstrap_ci(
    values: list[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """IC 95% de la media por remuestreo con reemplazo, como la validación del martes."""
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        mean = float(array.mean()) if array.size else 0.0
        return mean, mean
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.integers(0, array.size, size=(resamples, array.size))
    means = array[draws].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def loop_history(payload: dict) -> list[dict]:
    """Curva del bucle desde las rondas persistidas. No re-ejecuta el LLM.

    Una ronda propone las N candidatas juntas y después las simula, así que el bucle
    no puede usar el resultado de una candidata para decidir la siguiente: la
    granularidad con la que puede actuar es la ronda, igual que un lote del LLM sin
    retroalimentación. Poner un punto por candidata inflaría su eficiencia.
    """
    k = int(payload["policies"][0]["n_seeds"])
    rows = [{"sims_acumuladas": k, "best_so_far": float(payload["fixed_objective"])}]
    sims = k
    best = float(payload["fixed_objective"])
    for round_payload in payload["rounds"]:
        for item in round_payload["evaluated"]:
            best = max(best, float(item["objective"]))
        sims += int(round_payload["sims_spent"])
        rows.append({"sims_acumuladas": sims, "best_so_far": best})
    return rows


def holdout_seeds(config: SearchConfig, rng_seed: int) -> list[int]:
    """Las mismas que usa run_search: 1_000_000 + rng_seed en adelante."""
    return list(range(HOLDOUT_BASE + rng_seed, HOLDOUT_BASE + rng_seed + config.HOLDOUT_SEEDS))


@dataclass(slots=True)
class Holdout:
    n_seeds: int
    objective: float
    ci_low: float
    ci_high: float
    on_time_rate: float


@dataclass(slots=True)
class Method:
    name: str
    simulations: int
    best_train: float
    points: list[tuple[int, float]]
    llm_dependent: bool
    source: str
    note: str
    sims_at_target: int | None = None
    holdout: Holdout | None = None


def check_llm_source(methods: list[Method], required: str | None) -> None:
    """Aborta si un método que depende del LLM no declara la fuente esperada.

    Es el guardarraíl de la sesión GPU 2: con el túnel caído las corridas saldrían contra
    el mock, la tabla se vería igual y el error pasaría desapercibido.
    """
    if required is None:
        return
    wrong = {
        item.name: item.source for item in methods if item.llm_dependent and item.source != required
    }
    if wrong:
        raise SystemExit(
            f"se esperaba llm_source={required!r} en los métodos que dependen del LLM y "
            f"estos declaran otra cosa: {wrong}"
        )


@dataclass(slots=True)
class Report:
    profile: str
    seed: int
    scenario: str
    llm_source: str
    k: int
    target: float
    best_global: float
    fixed: float
    methods: list[Method] = field(default_factory=list)


def _latest(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise SystemExit(f"no hay archivos {pattern} en {directory}")
    return matches[-1]


def loop_from_replay(replay: dict) -> dict:
    """Adapta un replay congelado al formato del JSON de `search.loop`.

    Hace falta porque en la sesión GPU 2 el bucle corre por el worker (que persiste
    holdout y estrés en Postgres) y no escribe el JSON de `search.loop`. La adaptación
    vive aquí para que `eval/` no tenga que importar la capa de base de datos.
    """
    config = replay.get("config") or {}
    rounds = [
        {
            "sims_spent": int(item.get("sims_spent") or 0),
            "evaluated": [{"objective": float(value)} for value in item.get("objectives") or []],
        }
        for item in replay.get("rounds") or []
    ]
    return {
        "config": config,
        "seed": config.get("seed"),
        "scenario": config.get("scenario"),
        "simulations_total": replay["run"]["total_simulations"],
        "best_objective": replay["run"]["best_objective"],
        "fixed_objective": (replay.get("fixed_metrics", {}).get("train") or {}).get("objective"),
        "best_policy": replay.get("best_policy"),
        "policies": [{"n_seeds": config.get("K")}],
        "rounds": rounds,
    }


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _check_same_budget(configs: dict[str, dict], profile: str, seed: int) -> int:
    """Los cuatro métodos tienen que compartir K, perfil y semilla, o no se comparan."""
    ks = {name: int(cfg["K"]) for name, cfg in configs.items()}
    if len(set(ks.values())) != 1:
        detail = ", ".join(f"{name}: K={value}" for name, value in sorted(ks.items()))
        raise SystemExit(f"presupuestos distintos, no son comparables ({detail})")
    for name, cfg in configs.items():
        if cfg.get("profile") != profile or int(cfg.get("seed", -1)) != seed:
            raise SystemExit(
                f"{name} es de perfil {cfg.get('profile')!r} y seed {cfg.get('seed')!r}, "
                f"se pidió {profile!r} y {seed!r}"
            )
    return next(iter(ks.values()))


def _holdout(policy: Policy, seeds: list[int], workers: int, scenario: str) -> Holdout:
    rows = simulate_many(policy, seeds, workers, scenario=scenario)
    weights = load_objective_weights()
    scores = [composite_objective(row, weights) for row in rows]
    low, high = bootstrap_ci(scores)
    return Holdout(
        n_seeds=len(seeds),
        objective=float(np.mean(scores)),
        ci_low=low,
        ci_high=high,
        on_time_rate=float(np.mean([row["on_time_rate"] for row in rows])),
    )


def build_report(
    directory: Path,
    config: SearchConfig,
    seed: int,
    scenario: str,
    llm_source: str | None,
    workers: int,
    loop_json: Path | None = None,
    require_llm_source: str | None = None,
) -> Report:
    stamp = f"{config.profile}_seed{seed}"
    optuna_path = _latest(directory, f"optuna_{stamp}_*.json")
    nofeedback_path = _latest(directory, f"llm_nofeedback_{stamp}_*.json")
    loop_path = loop_json or _latest(directory, "search_*.json")
    optuna = _load(optuna_path)
    nofeedback = _load(nofeedback_path)
    loop = _load(loop_path)
    if "job" in loop and "run" in loop:  # es un replay congelado, no el JSON de search.loop
        loop = loop_from_replay(loop)

    configs = {"optuna": optuna["config"], "llm_nofeedback": nofeedback["config"]}
    if "config" in loop:
        configs["bucle"] = loop["config"]
    k = _check_same_budget(configs, config.profile, seed)
    # Los JSON del bucle escritos antes de que el payload llevara su bloque de
    # configuración no traen N/K/R: se derivan de lo persistido y se comparan.
    loop_k = k if "config" in loop else int(loop["policies"][0]["n_seeds"])
    if loop_k != k:
        raise SystemExit(
            f"el JSON del bucle ({loop_path.name}) usó K={loop_k} y las líneas base K={k}; "
            "no son comparables. Corre el bucle con el mismo perfil o pásalo con --loop-json"
        )
    if int(loop.get("seed", -1)) != seed:
        raise SystemExit(f"el JSON del bucle es de seed {loop.get('seed')!r}, se pidió {seed!r}")
    scenarios = {
        "optuna": optuna["config"].get("scenario"),
        "llm_nofeedback": nofeedback["config"].get("scenario"),
        "bucle": loop.get("config", {}).get("scenario", loop.get("scenario")),
    }
    wrong = {name: value for name, value in scenarios.items() if value != scenario}
    if wrong:
        raise SystemExit(f"escenarios distintos, no son comparables: {wrong}")

    fixed_values = {float(payload["fixed_objective"]) for payload in (optuna, nofeedback, loop)}
    fixed = sorted(fixed_values)[0]
    if len(fixed_values) != 1:
        print(f"aviso: fixed_objective distinto entre corridas: {sorted(fixed_values)}")
    fixed_policy = fixed_rule_policy()

    # La fuente sale del JSON. La bandera solo pisa ese valor.
    sources = {
        "llm_nofeedback": llm_source or nofeedback["config"].get("llm_source"),
        "bucle": llm_source or loop.get("config", {}).get("llm_source"),
    }
    if llm_source is None and any(llm_note(value) == UNKNOWN_NOTE for value in sources.values()):
        print(
            "aviso: algún JSON no declara config.llm_source (corrida anterior a ese campo). "
            "Pásalo a mano con --llm-source mock|vllm si lo sabes."
        )
    methods = [
        Method(
            name="regla fija",
            simulations=k,
            best_train=fixed,
            points=[(k, fixed)],  # punto único; se extiende horizontal al presupuesto
            llm_dependent=False,
            source="none",
            note=DEFINITIVE_NOTE,
        ),
        Method(
            name="Optuna TPE",
            simulations=int(optuna["simulations_total"]),
            best_train=float(optuna["best_objective"]),
            points=curve(optuna["history"]),
            llm_dependent=False,
            source=str(optuna["config"].get("llm_source", "none")),
            note=DEFINITIVE_NOTE,
        ),
        Method(
            name="LLM sin retroalimentación",
            simulations=int(nofeedback["simulations_total"]),
            best_train=float(nofeedback["best_objective"]),
            points=curve(nofeedback["history"]),
            llm_dependent=True,
            source=str(sources["llm_nofeedback"]),
            note=llm_note(sources["llm_nofeedback"]),
        ),
        Method(
            name="bucle con retroalimentación",
            simulations=int(loop["simulations_total"]),
            best_train=float(loop["best_objective"]),
            points=curve(loop_history(loop)),
            llm_dependent=True,
            source=str(sources["bucle"]),
            note=llm_note(sources["bucle"]),
        ),
    ]

    check_llm_source(methods, require_llm_source)
    best_global = max(method.best_train for method in methods)
    target = improvement_target(fixed, best_global)
    for method in methods:
        method.sims_at_target = sims_to_fraction(method.points, target)

    policies = {
        "regla fija": fixed_policy,
        "Optuna TPE": parse_policy(optuna["best_policy"]),
        "LLM sin retroalimentación": parse_policy(nofeedback["best_policy"]),
        "bucle con retroalimentación": parse_policy(loop["best_policy"]),
    }
    seeds = holdout_seeds(config, seed)
    if seeds:
        for method in methods:
            method.holdout = _holdout(policies[method.name], seeds, workers, scenario)

    return Report(
        profile=config.profile,
        seed=seed,
        scenario=scenario,
        llm_source=llm_source or "derivado del JSON",
        k=k,
        target=target,
        best_global=best_global,
        fixed=fixed,
        methods=methods,
    )


def render(report: Report) -> str:
    lines = [
        f"perfil={report.profile} seed={report.seed} escenario={report.scenario} K={report.k} "
        f"llm={report.llm_source}",
        f"umbral = fixed + 0.9*(best_global - fixed) = {report.fixed:.4f} + "
        f"0.9*({report.best_global:.4f} - {report.fixed:.4f}) = {report.target:.4f}",
        "",
        f"{'método':<30}{'train':>9}{'holdout':>9}{'IC 95%':>19}{'% a tiempo':>12}"
        f"{'sims':>8}{'sims al 90%':>13}  notas",
    ]
    for method in report.methods:
        if method.holdout is None:
            hold, interval, on_time = "—", "—", "—"
        else:
            hold = f"{method.holdout.objective:.4f}"
            interval = f"[{method.holdout.ci_low:.4f}, {method.holdout.ci_high:.4f}]"
            on_time = f"{100 * method.holdout.on_time_rate:.1f}%"
        reached = "no alcanza" if method.sims_at_target is None else str(method.sims_at_target)
        lines.append(
            f"{method.name:<30}{method.best_train:>9.4f}{hold:>9}{interval:>19}{on_time:>12}"
            f"{method.simulations:>8}{reached:>13}  {method.note}"
        )
    return "\n".join(lines)


def payload(report: Report) -> dict:
    return {
        "date": datetime.now(UTC).strftime("%Y%m%d"),
        "profile": report.profile,
        "seed": report.seed,
        "scenario": report.scenario,
        "llm_source": report.llm_source,
        "k": report.k,
        "target": report.target,
        "best_global": report.best_global,
        "fixed": report.fixed,
        "methods": [
            {
                **asdict(method),
                "points": [list(point) for point in method.points],
            }
            for method in report.methods
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Curva de eficiencia por método")
    parser.add_argument("--results-dir", type=Path, default=Path("bench/results"))
    parser.add_argument("--profile", default="default")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", default="base", choices=("base", "stress"))
    parser.add_argument(
        "--llm-source",
        default=None,
        choices=("mock", "vllm"),
        help="override; por defecto la fuente se lee de config.llm_source de cada JSON",
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--loop-json", type=Path, default=None, help="JSON de la búsqueda con bucle"
    )
    parser.add_argument(
        "--require-llm-source",
        default=None,
        choices=("mock", "vllm"),
        help="aborta si un método que depende del LLM no declara esta fuente",
    )
    args = parser.parse_args()

    config = SearchConfig.from_profile(args.profile)
    report = build_report(
        args.results_dir,
        config,
        args.seed,
        args.scenario,
        args.llm_source,
        Settings().SIM_WORKERS if args.workers is None else args.workers,
        loop_json=args.loop_json,
        require_llm_source=args.require_llm_source,
    )
    path = args.results_dir / f"efficiency_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload(report), indent=2) + "\n")
    print(render(report))
    print(f"\njson={path}  (la figura queda para el jueves en Chart.js)")


if __name__ == "__main__":
    main()
