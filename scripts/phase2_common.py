"""Shared paths and deterministic DuckDB helpers for phase two."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_ROOT = REPO_ROOT / "sql"
REPORT_DIR = REPO_ROOT / "reports"
LOCAL_DIR = REPO_ROOT / "data" / "local"
DATABASE_PATH = LOCAL_DIR / "phase2.duckdb"
SOURCE_COMMIT = "1f9b4288cee5a78d1e5da007fc306bbaa662fc6d"

SOURCE_EXPECTATIONS = {
    "raw.waybill": 654_343,
    "raw.courier_wave": 206_748,
    "raw.dispatch_rider": 62_044,
    "raw.dispatch_waybill": 15_921,
}


def connect(*, reset: bool = False) -> duckdb.DuckDBPyConnection:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    if reset and DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    connection = duckdb.connect(str(DATABASE_PATH))
    connection.execute("SET threads = 1")
    connection.execute("SET TimeZone = 'Asia/Shanghai'")
    return connection


def execute_sql_file(connection: duckdb.DuckDBPyConnection, relative_path: str) -> None:
    path = SQL_ROOT / relative_path
    connection.execute(path.read_text(encoding="utf-8"))


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> object:
    return connection.execute(query).fetchone()[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_source_contract(connection: duckdb.DuckDBPyConnection) -> list[str]:
    passed: list[str] = []
    for table, expected_rows in SOURCE_EXPECTATIONS.items():
        actual_rows = int(scalar(connection, f"SELECT count(*) FROM {table}"))
        if actual_rows != expected_rows:
            raise AssertionError(f"{table}: expected {expected_rows}, got {actual_rows}")
        passed.append(f"{table} row count")

    if scalar(connection, "SELECT source_commit FROM meta.build_contract") != SOURCE_COMMIT:
        raise AssertionError("source commit contract changed")
    passed.append("fixed source commit")

    if scalar(connection, "SELECT timezone_name FROM meta.build_contract") != "Asia/Shanghai":
        raise AssertionError("timezone contract changed")
    passed.append("Asia/Shanghai timezone")
    return passed


def assert_step_b_contract(connection: duckdb.DuckDBPyConnection) -> list[str]:
    checks = {
        "waybill fact row conservation": (
            "SELECT count(*) FROM fact.fact_waybill_attempt",
            654_343,
        ),
        "order fact row conservation": (
            "SELECT count(*) FROM fact.fact_order_fulfillment",
            568_546,
        ),
        "waybill key uniqueness": (
            "SELECT count(*) - count(DISTINCT waybill_id) FROM fact.fact_waybill_attempt",
            0,
        ),
        "order key uniqueness": (
            "SELECT count(*) - count(DISTINCT order_id) FROM fact.fact_order_fulfillment",
            0,
        ),
        "accepted attempt count": (
            "SELECT count(*) FROM fact.fact_waybill_attempt WHERE is_courier_grabbed = 1",
            568_546,
        ),
        "rejected attempt count": (
            "SELECT count(*) FROM fact.fact_waybill_attempt WHERE is_courier_grabbed = 0",
            85_797,
        ),
        "one accepted attempt per order": (
            "SELECT count(*) FROM (SELECT order_id FROM fact.fact_waybill_attempt "
            "GROUP BY order_id HAVING count(*) FILTER (WHERE is_courier_grabbed = 1) <> 1)",
            0,
        ),
        "accepted attempt is final sequence": (
            "SELECT count(*) FROM fact.fact_waybill_attempt "
            "WHERE is_courier_grabbed = 1 AND NOT is_final_accepted_attempt",
            0,
        ),
        "attempt rollup conservation": (
            "SELECT sum(attempt_count) FROM fact.fact_order_fulfillment",
            654_343,
        ),
        "rejection rollup conservation": (
            "SELECT sum(rejection_count) FROM fact.fact_order_fulfillment",
            85_797,
        ),
        "cross-waybill inconsistency flags": (
            "SELECT count(*) FROM fact.fact_order_fulfillment "
            "WHERE has_cross_waybill_attribute_inconsistency",
            61,
        ),
        "incomplete accepted flag": (
            "SELECT count(*) FROM fact.fact_order_fulfillment WHERE is_incomplete_accepted",
            1,
        ),
        "event order violations": (
            "SELECT count(*) FROM fact.fact_order_fulfillment WHERE has_event_order_error",
            0,
        ),
        "negative core durations": (
            "SELECT count(*) FROM fact.fact_order_fulfillment WHERE "
            "order_to_push_seconds < 0 OR push_to_first_dispatch_seconds < 0 "
            "OR first_dispatch_to_accept_seconds < 0 OR accept_to_fetch_seconds < 0 "
            "OR fetch_to_arrive_seconds < 0 OR end_to_end_seconds < 0",
            0,
        ),
        "completed-duration denominator excludes incomplete": (
            "SELECT count(*) FROM fact.fact_order_fulfillment "
            "WHERE NOT is_completed AND (fetch_to_arrive_seconds IS NOT NULL OR end_to_end_seconds IS NOT NULL)",
            0,
        ),
    }
    passed: list[str] = []
    for name, (query, expected) in checks.items():
        actual = scalar(connection, query)
        if actual != expected:
            raise AssertionError(f"{name}: expected {expected}, got {actual}")
        passed.append(name)
    return passed
