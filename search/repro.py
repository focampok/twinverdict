"""Datos para repetir una búsqueda: lo que corrió, no lo que se pensaba correr."""

from __future__ import annotations

import subprocess
from pathlib import Path

from search.config import SearchConfig
from search.loop import SearchResult

_REPO_ROOT = Path(__file__).resolve().parents[1]


def git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    sha = completed.stdout.strip()
    return sha or "unknown"


def build_search_config(config: SearchConfig, result: SearchResult, model: str) -> dict:
    """JSON de la corrida. Cabe en search_runs.config y en jobs.params, ambos JSONB."""
    return {
        "N": config.N,
        "K": config.K,
        "R": config.R,
        "sim_workers": result.sim_workers,
        "model": model,
        "profile": config.profile,
        "train_seeds": list(result.train_seeds),
        "holdout_seeds": list(result.holdout_seeds),
        "git_commit": git_head(),
        "seconds_per_sim": result.seconds_per_sim,
        "seed": result.seed,
        "scenario": result.scenario,
    }
