"""Descarga AI4I 2020 Predictive Maintenance a data/raw/ai4i2020.csv.

Fuente: UCI Machine Learning Repository, dataset 601 (S. Matzka, 2020).
https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset

El CSV queda en data/raw/, que está en .gitignore: no se versiona. Se imprime el
sha256 para poder anotarlo en docs/CALIBRATION.md junto con la fecha de descarga.
"""

from __future__ import annotations

import hashlib
import io
import sys
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
MEMBER = "ai4i2020.csv"
DESTINATION = Path("data/raw/ai4i2020.csv")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path = DESTINATION) -> Path:
    with urllib.request.urlopen(URL, timeout=60) as response:  # noqa: S310 (URL fija)
        archive = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = [name for name in bundle.namelist() if name.endswith(MEMBER)]
        if len(names) != 1:
            raise SystemExit(f"el zip no trae {MEMBER}: {bundle.namelist()}")
        destination.write_bytes(bundle.read(names[0]))
    return destination


def main() -> None:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINATION
    path = download(destination)
    rows = sum(1 for _ in path.open("rb")) - 1
    print(f"url: {URL}")
    print(f"fecha: {datetime.now(UTC).strftime('%Y-%m-%d')}")
    print(f"archivo: {path}")
    print(f"filas: {rows}")
    print(f"sha256: {sha256(path)}")


if __name__ == "__main__":
    main()
