"""Congela una corrida en dos JSON para que la UI del jueves solo lea datos.

Uso:
    uv run python -m search.freeze_run                # la última corrida con status done
    uv run python -m search.freeze_run <job_id>

Escribe `bench/results/replay_<job_id>.json` y `bench/results/operator_card_<job_id>.json`.
No toca la base: congelar dos veces el mismo job deja los mismos dos archivos y no añade
filas. Los JSON sí se versionan (ver .gitignore) porque son el insumo de la UI.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from db.session import session_factory
from search.replay import RESULTS_DIR, load_replay, operator_card
from search.store import latest_done


def freeze(job_id: uuid.UUID | str, directory: Path = RESULTS_DIR) -> tuple[Path, Path]:
    key = uuid.UUID(str(job_id))
    replay = load_replay(key, directory=directory)
    directory.mkdir(parents=True, exist_ok=True)
    replay_path = directory / f"replay_{key}.json"
    card_path = directory / f"operator_card_{key}.json"
    replay_path.write_text(json.dumps(replay, indent=2, ensure_ascii=False) + "\n")
    card_path.write_text(json.dumps(operator_card(replay), indent=2, ensure_ascii=False) + "\n")
    return replay_path, card_path


def _latest_job_id() -> uuid.UUID:
    factory = session_factory()
    with factory() as session:
        run = latest_done(session)
        if run is None:
            raise SystemExit("no hay ninguna corrida con status done para congelar")
        return run.job_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Congela una corrida para replay")
    parser.add_argument("job_id", nargs="?", help="por defecto, la última corrida terminada")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    job_id = uuid.UUID(args.job_id) if args.job_id else _latest_job_id()
    replay_path, card_path = freeze(job_id, args.out)
    card = json.loads(card_path.read_text())
    print(f"replay: {replay_path}")
    print(f"tarjeta: {card_path}")
    numbers = card["numbers"]
    print(
        f"% a tiempo en holdout: fija={100 * numbers.get('on_time_rate_fixed_holdout', 0):.1f}% "
        f"mejor={100 * numbers.get('on_time_rate_best_holdout', 0):.1f}% "
        f"números medidos={len(numbers)}"
    )


if __name__ == "__main__":
    main()
