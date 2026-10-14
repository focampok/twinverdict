"""Encola un job. Uso: python -m worker.enqueue baseline|search."""

import sys

from db.models import Job
from db.session import session_factory
from search.config import SearchConfig

KINDS = ("search", "baseline", "eval")


def enqueue(kind: str, params: dict | None = None) -> str:
    if kind not in KINDS:
        raise SystemExit(f"kind debe ser uno de {KINDS}")
    stored = {} if params is None else dict(params)
    if kind == "search" and params is None:
        config = SearchConfig()
        stored = {
            "seed": 1,
            "scenario": "base",
            "profile": config.profile,
            "N": config.N,
            "K": config.K,
            "R": config.R,
        }
    factory = session_factory()
    with factory() as session:
        job = Job(kind=kind, status="queued", params=stored)
        session.add(job)
        session.commit()
        return str(job.id)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m worker.enqueue baseline|search")
    print(enqueue(sys.argv[1]))


if __name__ == "__main__":
    main()
