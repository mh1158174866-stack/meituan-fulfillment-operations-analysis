#!/usr/bin/env python3
"""Fail if Git candidate files contain distributable raw-data artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_SUFFIXES = {".csv", ".parquet", ".zip", ".duckdb", ".wal"}
DATA_PREFIXES = ("data/raw/", "data/interim/", "data/processed/")
ALLOWED_DATA_FILES = {
    "data/raw/.gitkeep",
    "data/interim/.gitkeep",
    "data/processed/.gitkeep",
}


def main() -> None:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    candidates = [item.decode("utf-8") for item in output.split(b"\0") if item]
    violations: list[str] = []
    for relative in candidates:
        path = Path(relative)
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            violations.append(f"blocked data extension: {relative}")
        if relative.startswith(DATA_PREFIXES) and relative not in ALLOWED_DATA_FILES:
            violations.append(f"data directory content is visible to Git: {relative}")
    if violations:
        raise SystemExit("Privacy scan failed:\n- " + "\n- ".join(violations))
    print(f"Privacy scan passed for {len(candidates)} Git candidate files.")
    print("No raw CSV/ZIP/Parquet/DuckDB files are visible to Git.")


if __name__ == "__main__":
    main()
