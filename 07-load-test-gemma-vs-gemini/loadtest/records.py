"""Write one row per request to a fresh CSV per run. report.py reads one or more of them."""

import csv
import os
import time
from pathlib import Path

FIELDS = [
    "side",
    "ttft_s",
    "output_tokens",
    "billed_output_tokens",
    "tokens_per_second",
    "started_at",
    "ended_at",
    "ok",
    "status",
]


def new_records_path() -> Path:
    """A new file for every run, so reruns never mix samples. RECORDS_CSV overrides the name."""
    override = os.environ.get("RECORDS_CSV")
    if override:
        path = Path(override)
        if path.exists():
            raise FileExistsError(f"{path} exists; use a new name so runs do not mix")
        return path
    return Path("results") / time.strftime("records-%Y%m%dT%H%M%S.csv", time.gmtime())


def append_record(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
