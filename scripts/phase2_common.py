"""Shared paths and deterministic DuckDB helpers for phase two."""

from __future__ import annotations

import hashlib
import json
import subprocess
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
SOURCE_FILE_HASHES = {
    "all_waybill_info_meituan_0322.csv": "1d31aac21e17c11aec6ab0033d4040c03aea5bab1dfd60aa11e74d766bbd2c04",
    "courier_wave_info_meituan.csv": "8f8a4c2f3761f7fcb5c645c926e6ae4272650200c36028480ad6f223cced5b5a",
    "dispatch_rider_meituan.csv": "71007a5c72198e31b907eaa1685633d2de910d8f9fbe276e8e5200bc2a9a6d3a",
    "dispatch_waybill_meituan.csv": "90a395115b707fa720a44a1cfb54b71bd5669c180d684a2c54e211650ad9e1a8",
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


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def logical_database_fingerprint(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[str, list[tuple[str, int, str]]]:
    """Hash schemas plus order-independent full-row hash aggregates for every table.

    DuckDB physical files contain storage metadata whose bytes need not be stable across
    equivalent rebuilds. This fingerprint instead covers every logical table column,
    row count, XOR of row hashes, and duplicate-sensitive sum of row hashes, then wraps
    the canonical manifest in SHA-256.
    """

    tables = connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
        "AND table_type = 'BASE TABLE' ORDER BY table_schema, table_name"
    ).fetchall()
    manifest: list[dict[str, object]] = []
    table_fingerprints: list[tuple[str, int, str]] = []
    for schema, table in tables:
        columns = connection.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            [schema, table],
        ).fetchall()
        quoted_columns = ", ".join(_quote_identifier(row[0]) for row in columns)
        qualified = f"{_quote_identifier(schema)}.{_quote_identifier(table)}"
        row_count, row_hash_xor, row_hash_sum = connection.execute(
            f"SELECT count(*), bit_xor(hash({quoted_columns})), "
            f"sum(hash({quoted_columns}))::HUGEINT FROM {qualified}"
        ).fetchone()
        entry = {
            "table": f"{schema}.{table}",
            "columns": columns,
            "row_count": row_count,
            "row_hash_xor": row_hash_xor,
            "row_hash_sum": str(row_hash_sum),
        }
        canonical_entry = json.dumps(
            entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        table_digest = hashlib.sha256(canonical_entry).hexdigest()
        table_fingerprints.append((f"{schema}.{table}", int(row_count), table_digest))
        manifest.append(entry)
    canonical_manifest = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical_manifest).hexdigest(), table_fingerprints


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

    mismatched_hashes = []
    for filename, expected_digest in SOURCE_FILE_HASHES.items():
        path = REPO_ROOT / "data" / "raw" / filename
        actual_digest = sha256(path)
        if actual_digest != expected_digest:
            mismatched_hashes.append(filename)
    if mismatched_hashes:
        raise AssertionError(f"fixed raw input hash mismatch: {mismatched_hashes}")
    passed.append("fixed raw input SHA-256")
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
        "accepted missing dispatch flag": (
            "SELECT count(*) FROM fact.fact_order_fulfillment WHERE has_missing_dispatch_time",
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
        "wave member unique order ownership": (
            "SELECT count(*) - count(DISTINCT order_id) FROM stg.wave_order_membership",
            0,
        ),
        "wave membership composite uniqueness": (
            "SELECT count(*) - count(DISTINCT (dt, courier_id, wave_id, order_id)) "
            "FROM stg.wave_order_membership",
            0,
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
        "onhand member conservation": (
            "SELECT sum(parsed_onhand_count) FROM fact.fact_dispatch_checkpoint_rider",
            125_715,
        ),
        "onhand dual-domain relationship coverage": (
            "SELECT sum(onhand_waybill_match_count) - sum(onhand_order_match_count) "
            "FROM fact.fact_dispatch_checkpoint_rider",
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
        "missing dispatch duration denominators": (
            "SELECT least(push_to_first_dispatch_eligible_count, "
            "first_dispatch_to_accept_eligible_count, final_dispatch_to_accept_eligible_count) "
            "FROM metrics.overall_fulfillment",
            568_545,
        ),
        "no silent quality exclusion in fixed input": (
            "SELECT quality_excluded_order_count + quality_excluded_waybill_count "
            "FROM metrics.overall_fulfillment",
            0,
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


def assert_step_e_contract(connection: duckdb.DuckDBPyConnection) -> list[str]:
    expected_tables = {
        "fact.fact_courier_wave",
        "fact.fact_dispatch_checkpoint",
        "fact.fact_dispatch_checkpoint_order",
        "fact.fact_dispatch_checkpoint_rider",
        "fact.fact_order_fulfillment",
        "fact.fact_waybill_attempt",
        "meta.build_contract",
        "metrics.checkpoint_snapshot",
        "metrics.daily_fulfillment",
        "metrics.metric_catalog",
        "metrics.overall_fulfillment",
        "raw.courier_wave",
        "raw.dispatch_rider",
        "raw.dispatch_waybill",
        "raw.waybill",
        "stg.checkpoint_order",
        "stg.checkpoint_rider",
        "stg.checkpoint_rider_onhand",
        "stg.wave_order_membership",
        "stg.waybill_attempt",
    }
    actual_tables = {
        f"{schema}.{table}"
        for schema, table in connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
            "AND table_type = 'BASE TABLE'"
        ).fetchall()
    }
    if actual_tables != expected_tables:
        raise AssertionError(
            f"table inventory mismatch: missing={sorted(expected_tables - actual_tables)}, "
            f"extra={sorted(actual_tables - expected_tables)}"
        )
    passed = ["complete 20-table inventory"]

    ignored_paths = [
        DATABASE_PATH,
        REPO_ROOT / "data" / "raw" / "all_waybill_info_meituan_0322.csv",
        REPO_ROOT / "data" / "raw" / "courier_wave_info_meituan.csv",
        REPO_ROOT / "data" / "raw" / "dispatch_rider_meituan.csv",
        REPO_ROOT / "data" / "raw" / "dispatch_waybill_meituan.csv",
    ]
    for path in ignored_paths:
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", str(path)], cwd=REPO_ROOT, check=False
        )
        if completed.returncode != 0:
            raise AssertionError(f"local sensitive path is not ignored: {path}")
    passed.append("database and raw inputs ignored")

    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, check=True, capture_output=True
    ).stdout.split(b"\0")
    forbidden_suffixes = (
        b".7z",
        b".arrow",
        b".csv",
        b".db",
        b".duckdb",
        b".feather",
        b".gz",
        b".jsonl",
        b".ndjson",
        b".npy",
        b".npz",
        b".parquet",
        b".pdf",
        b".pkl",
        b".sqlite",
        b".sqlite3",
        b".tar",
        b".tsv",
        b".xls",
        b".xlsx",
        b".zip",
    )
    forbidden = [item.decode("utf-8") for item in tracked if item.lower().endswith(forbidden_suffixes)]
    if forbidden:
        raise AssertionError(f"forbidden tracked data artifacts: {forbidden}")
    passed.append("no forbidden data artifacts tracked")

    required_sql = (
        "00_sources/00_raw_tables.sql",
        "10_staging/10_waybill_attempt.sql",
        "10_staging/11_wave_checkpoint.sql",
        "20_facts/20_order_fulfillment.sql",
        "20_facts/21_wave_checkpoint.sql",
        "30_metrics/30_metric_layer.sql",
        "30_metrics/31_metric_catalog.sql",
    )
    missing_sql = [name for name in required_sql if not (SQL_ROOT / name).is_file()]
    if missing_sql:
        raise AssertionError(f"missing SQL files: {missing_sql}")
    passed.append("complete ordered SQL inventory")
    return passed
