#!/usr/bin/env python3
"""Create or compare an aggregate-only semantic fingerprint of stage-2 tables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.stage2_contract import CORE_OBJECTS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "processed" / "meituan_fulfillment.duckdb",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "interim" / "stage2_fingerprint.json",
    )
    parser.add_argument("--compare", type=Path)
    return parser.parse_args()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def build_fingerprint(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    result: dict[str, object] = {"duckdb_version": duckdb.__version__, "objects": {}}
    objects = result["objects"]
    assert isinstance(objects, dict)
    for table in CORE_OBJECTS:
        schema = connection.execute(f"DESCRIBE {quote_identifier(table)}").fetchall()
        columns = [row[0] for row in schema]
        hash_args = ", ".join(quote_identifier(column) for column in columns)
        row_count, content_hash = connection.execute(
            f"SELECT count(*), bit_xor(hash({hash_args})) FROM {quote_identifier(table)}"
        ).fetchone()
        objects[table] = {
            "row_count": row_count,
            "columns": [{"name": row[0], "type": row[1]} for row in schema],
            "content_hash": str(content_hash),
        }
    return result


def main() -> None:
    args = parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        fingerprint = build_fingerprint(connection)

    if args.compare:
        expected = json.loads(args.compare.read_text(encoding="utf-8"))
        assert fingerprint == expected, "Stage-2 semantic fingerprint changed across rebuilds."
        print(f"Deterministic rebuild check passed against {args.compare}.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote aggregate-only semantic fingerprint: {args.output}")
    print("Fingerprint contains schemas, row counts, and hashes only; no raw values or IDs.")


if __name__ == "__main__":
    main()
