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
