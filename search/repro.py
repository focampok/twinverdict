"""Datos para repetir una búsqueda: lo que corrió, no lo que se pensaba correr."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from config import Settings
from search.config import SearchConfig

if TYPE_CHECKING:  # evita el ciclo: search.loop importa este módulo para el payload
    from search.loop import SearchResult

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Puerto del mock local (Makefile: uvicorn llm.mock_server:app --port 8001). El túnel de
# la GPU usa otro puerto (8000, infra/gpu/gpu.sh) y también es localhost, así que la
# fuente no se puede derivar solo del host: hace falta el puerto.
MOCK_LLM_PORT = 8001
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def mock_llm_port() -> int:
    raw = os.environ.get("MOCK_LLM_PORT", "").strip()
    return int(raw) if raw else MOCK_LLM_PORT


def llm_source(base_url: str, model: str, port: int | None = None) -> str:
    """De dónde salieron las políticas: 'none' sin LLM, 'mock' o 'vllm'.

    vLLM se usa por túnel SSH en localhost (puerto 8000), así que un host de loopback
    no prueba que sea el mock. La regla es loopback + puerto del mock.
    """
    if model == "none":
        return "none"
    expected = mock_llm_port() if port is None else port
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    effective = parts.port or (443 if parts.scheme == "https" else 80)
    return "mock" if host in _LOOPBACK and effective == expected else "vllm"


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


def build_search_config(
    config: SearchConfig,
    result: SearchResult,
    model: str,
    llm_base_url: str | None = None,
) -> dict:
    """JSON de la corrida. Cabe en search_runs.config y en jobs.params, ambos JSONB.

    Guarda el endpoint y de dónde salieron las políticas, para que un JSON diga por sí
    solo si se midió contra el mock o contra vLLM: sin eso, la etiqueta de la tabla de
    eficiencia tenía que venir de una bandera escrita a mano.
    """
    base_url = Settings().LLM_BASE_URL if llm_base_url is None else llm_base_url
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
        "llm_base_url": base_url,
        "llm_source": llm_source(base_url, model),
    }
