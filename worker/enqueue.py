"""Encola un job. Uso: python -m worker.enqueue baseline."""

import sys

from db.models import Job
from db.session import session_factory

KINDS = ("search", "baseline", "eval")


def enqueue(kind: str) -> str:
    if kind not in KINDS:
        raise SystemExit(f"kind debe ser uno de {KINDS}")
    factory = session_factory()
    with factory() as session:
        job = Job(kind=kind, status="queued", params={})
        session.add(job)
        session.commit()
        return str(job.id)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m worker.enqueue baseline")
    print(enqueue(sys.argv[1]))


if __name__ == "__main__":
    main()
