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


def assert_step_c_contract(connection: duckdb.DuckDBPyConnection) -> list[str]:
    checks = {
        "wave fact row conservation": (
            "SELECT count(*) FROM fact.fact_courier_wave",
            206_748,
        ),
        "wave composite key uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, courier_id, wave_id)) "
            "FROM fact.fact_courier_wave",
            0,
        ),
        "wave membership conservation": (
            "SELECT sum(member_count) FROM fact.fact_courier_wave",
            568_545,
        ),
        "wave member parse coverage": (
            "SELECT count(*) FROM fact.fact_courier_wave WHERE has_member_parse_error",
            0,
        ),
        "wave member relationship coverage": (
            "SELECT count(*) FROM fact.fact_courier_wave WHERE has_member_coverage_error",
            0,
        ),
        "wave reconstructed start coverage": (
            "SELECT count(*) FROM fact.fact_courier_wave "
            "WHERE reconstructed_wave_start_time IS NULL",
            0,
        ),
        "wave official start mismatch flags": (
            "SELECT count(*) FROM fact.fact_courier_wave WHERE has_start_time_mismatch",
            65_904,
        ),
        "wave end alignment": (
            "SELECT count(*) FROM fact.fact_courier_wave WHERE has_end_time_mismatch",
            0,
        ),
        "wave duration nonnegative": (
            "SELECT count(*) FROM fact.fact_courier_wave WHERE wave_duration_seconds < 0",
            0,
        ),
        "checkpoint count": (
            "SELECT count(*) FROM fact.fact_dispatch_checkpoint",
            24,
        ),
        "checkpoint date count": (
            "SELECT count(DISTINCT dt) FROM fact.fact_dispatch_checkpoint",
            8,
        ),
        "checkpoint composite key uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, dispatch_time)) "
            "FROM fact.fact_dispatch_checkpoint",
            0,
        ),
        "checkpoint both sides aligned": (
            "SELECT count(*) FROM fact.fact_dispatch_checkpoint "
            "WHERE missing_order_snapshot OR missing_rider_snapshot",
            0,
        ),
        "checkpoint pending order conservation": (
            "SELECT sum(pending_order_count) FROM fact.fact_dispatch_checkpoint",
            15_921,
        ),
        "checkpoint candidate courier conservation": (
            "SELECT sum(candidate_courier_count) FROM fact.fact_dispatch_checkpoint",
            62_044,
        ),
        "checkpoint order relationship coverage": (
            "SELECT count(*) FROM fact.fact_dispatch_checkpoint_order "
            "WHERE NOT has_fulfillment_match",
            0,
        ),
        "checkpoint rider key uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, dispatch_time, courier_id)) "
            "FROM fact.fact_dispatch_checkpoint_rider",
            0,
        ),
        "checkpoint order key uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, dispatch_time, order_id)) "
            "FROM fact.fact_dispatch_checkpoint_order",
            0,
        ),
        "onhand member parse coverage": (
            "SELECT count(*) FROM stg.checkpoint_rider_onhand WHERE has_parse_error",
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


def assert_step_d_contract(connection: duckdb.DuckDBPyConnection) -> list[str]:
    checks = {
        "daily metric date rows": ("SELECT count(*) FROM metrics.daily_fulfillment", 8),
        "daily metric date uniqueness": (
            "SELECT count(*) - count(DISTINCT dt) FROM metrics.daily_fulfillment",
            0,
        ),
        "metric catalog coverage": ("SELECT count(*) FROM metrics.metric_catalog", 25),
        "metric catalog unique names": (
            "SELECT count(*) - count(DISTINCT metric_name) FROM metrics.metric_catalog",
            0,
        ),
        "order metric conservation": (
            "SELECT sum(order_count) FROM metrics.daily_fulfillment",
            568_546,
        ),
        "waybill metric conservation": (
            "SELECT sum(waybill_attempt_count) FROM metrics.daily_fulfillment",
            654_343,
        ),
        "accepted waybill metric conservation": (
            "SELECT sum(accepted_waybill_count) FROM metrics.daily_fulfillment",
            568_546,
        ),
        "first success numerator": (
            "SELECT sum(first_attempt_success_order_count) FROM metrics.daily_fulfillment",
            510_776,
        ),
        "first attempt and first dispatch identity": (
            "SELECT count(*) FROM metrics.daily_fulfillment "
            "WHERE first_attempt_success_rate <> first_dispatch_success_rate",
            0,
        ),
        "attempt identity": (
            "SELECT attempt_count_sum - order_count - redispatch_count_sum "
            "FROM metrics.overall_fulfillment",
            0,
        ),
        "completion numerator": (
            "SELECT completed_order_count FROM metrics.overall_fulfillment",
            568_545,
        ),
        "completion duration denominator": (
            "SELECT end_to_end_eligible_count FROM metrics.overall_fulfillment",
            568_545,
        ),
        "strict versus buffer late monotonicity": (
            "SELECT count(*) FROM metrics.daily_fulfillment "
            "WHERE buffer_8m_late_order_count > strict_late_order_count",
            0,
        ),
        "rate bounds": (
            "SELECT count(*) FROM metrics.daily_fulfillment WHERE "
            "waybill_acceptance_rate NOT BETWEEN 0 AND 1 OR "
            "first_attempt_success_rate NOT BETWEEN 0 AND 1 OR "
            "completion_rate NOT BETWEEN 0 AND 1 OR "
            "strict_late_rate NOT BETWEEN 0 AND 1 OR "
            "buffer_8m_late_rate NOT BETWEEN 0 AND 1",
            0,
        ),
        "duration metric nonnegative where required": (
            "SELECT count(*) FROM metrics.daily_fulfillment WHERE "
            "avg_order_to_push_seconds < 0 OR avg_push_to_first_dispatch_seconds < 0 "
            "OR avg_first_dispatch_to_accept_seconds < 0 "
            "OR avg_final_dispatch_to_accept_seconds < 0 "
            "OR avg_accept_to_fetch_seconds < 0 OR avg_fetch_to_arrive_seconds < 0 "
            "OR avg_end_to_end_seconds < 0 OR avg_wave_duration_seconds < 0",
            0,
        ),
        "checkpoint metric rows": ("SELECT count(*) FROM metrics.checkpoint_snapshot", 24),
        "checkpoint metric key uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, dispatch_time)) "
            "FROM metrics.checkpoint_snapshot",
            0,
        ),
        "checkpoint ratio identity": (
            "SELECT count(*) FROM metrics.checkpoint_snapshot WHERE "
            "abs(pending_orders_per_candidate_courier "
            "- pending_order_count::DOUBLE / candidate_courier_count) > 1e-12",
            0,
        ),
        "checkpoint rider-order ratio identity": (
            "SELECT count(*) FROM metrics.checkpoint_snapshot WHERE "
            "abs(candidate_couriers_per_pending_order "
            "- candidate_courier_count::DOUBLE / pending_order_count) > 1e-12",
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
