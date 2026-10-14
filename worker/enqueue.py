"""Encola un job. Uso: python -m worker.enqueue baseline|search [--profile --seed --holdout]."""

import argparse

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
    parser = argparse.ArgumentParser(description="Encola un job")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--holdout", type=int, default=None, help="semillas de holdout y estrés")
    args = parser.parse_args()

    params = {
        key: value
        for key, value in (
            ("profile", args.profile),
            ("seed", args.seed),
            ("scenario", args.scenario),
            ("holdout", args.holdout),
        )
        if value is not None
    }
    # Sin banderas se mantiene el default de siempre, para no cambiar el comportamiento.
    print(enqueue(args.kind, params or None))


if __name__ == "__main__":
    main()
