#!/usr/bin/env python3
"""Build the local-only stage-2 DuckDB objects from official read-only CSVs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.stage2_contract import CORE_OBJECTS  # noqa: E402


DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "Meituan-INFORMS-TSL-Research-Challenge"
DEFAULT_DATABASE = ROOT / "data" / "processed" / "meituan_fulfillment.duckdb"
SQL_FILES = (
    ROOT / "sql" / "ods" / "00_raw_views.sql",
    ROOT / "sql" / "dwd" / "01_waybill.sql",
    ROOT / "sql" / "dwd" / "02_courier_wave.sql",
    ROOT / "sql" / "dws" / "01_courier_efficiency.sql",
    ROOT / "sql" / "ads" / "01_operations_overview.sql",
    ROOT / "sql" / "ads" / "02_hourly_supply_demand.sql",
    ROOT / "sql" / "ads" / "03_anomaly_diagnosis.sql",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def sql_literal_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    args = parse_args()
    required = (
        "all_waybill_info_meituan_0322.csv",
        "courier_wave_info_meituan.csv",
    )
    missing = [name for name in required if not (args.raw_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing official stage-2 inputs: {missing}")

    args.database.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = sql_literal_path(args.raw_dir)
    with duckdb.connect(str(args.database)) as connection:
        connection.execute("SET TimeZone='UTC'")
        # Single-threaded aggregation keeps floating-point reduction order stable,
        # so identical inputs produce identical semantic table fingerprints.
        connection.execute("SET threads=1")
        connection.execute("BEGIN TRANSACTION")
        try:
            for table in (*CORE_OBJECTS, "ads_courier_efficiency"):
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
            for path in SQL_FILES:
                statement = path.read_text(encoding="utf-8").replace(
                    "{{RAW_DIR}}", raw_dir
                )
                connection.execute(statement)
                print(f"Executed {path.relative_to(ROOT)}")
            connection.execute("COMMIT")
            connection.execute("CHECKPOINT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    print(f"Built local stage-2 database: {args.database}")
    print("The database contains row-level IDs and remains excluded from Git.")


if __name__ == "__main__":
    main()
