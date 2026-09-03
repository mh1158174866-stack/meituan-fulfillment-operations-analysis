#!/usr/bin/env python3
"""Validate stage-2 structure, relationships, formulas, and aggregate metrics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.stage2_contract import CORE_OBJECTS, EXPECTED_ROWS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "processed" / "meituan_fulfillment.duckdb",
    )
    return parser.parse_args()


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> int | float:
    return connection.execute(query).fetchone()[0]


def close(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def main() -> None:
    args = parse_args()
    if not args.database.is_file():
        raise FileNotFoundError(args.database)

    with duckdb.connect(str(args.database), read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        assert set(CORE_OBJECTS) == tables, (set(CORE_OBJECTS) - tables, tables - set(CORE_OBJECTS))

        row_counts = {
            name: scalar(connection, f'SELECT count(*) FROM "{name}"')
            for name in CORE_OBJECTS
        }
        for name, expected in EXPECTED_ROWS.items():
            assert row_counts[name] == expected, (name, row_counts[name], expected)

        assert scalar(connection, "SELECT count(*) - count(DISTINCT waybill_id) FROM dwd_waybill") == 0
        assert scalar(connection, "SELECT count(*) - count(DISTINCT (dt, courier_id, wave_id)) FROM dwd_courier_wave") == 0
        assert scalar(connection, "SELECT count(*) - count(DISTINCT (dt, courier_id, wave_id, order_id)) FROM dwd_order_wave_bridge") == 0

        status_counts = dict(
            connection.execute(
                "SELECT waybill_status, count(*) FROM dwd_waybill GROUP BY 1"
            ).fetchall()
        )
        assert status_counts == {
            "rejected": 85_797,
            "accepted_unfinished": 1,
            "completed": 568_545,
        }, status_counts

        assert scalar(connection, "SELECT sum(event_order_anomaly_flag) FROM dwd_waybill") == 0
        assert scalar(connection, "SELECT sum(wave_start_mismatch_flag) FROM dwd_courier_wave") == 65_904
        assert scalar(connection, "SELECT sum(wave_end_mismatch_flag) FROM dwd_courier_wave") == 0
        assert scalar(connection, "SELECT count(*) FROM dwd_courier_wave WHERE linked_order_count <> completed_order_count") == 0
        assert scalar(connection, "SELECT count(*) FROM dwd_courier_wave WHERE wave_start_time_corrected_epoch IS NULL") == 0

        orphan_bridge = scalar(
            connection,
            """
            SELECT count(*)
            FROM dwd_order_wave_bridge b
            LEFT JOIN dwd_waybill w
              ON w.dt=b.dt AND w.courier_id=b.courier_id AND w.order_id=b.order_id
             AND w.waybill_status='completed'
            WHERE w.order_id IS NULL
            """,
        )
        assert orphan_bridge == 0

        assert scalar(connection, "SELECT sum(assigned_waybill_count) FROM ads_operations_overview") == 654_343
        assert scalar(connection, "SELECT sum(order_count) FROM ads_operations_overview") == 568_546
        assert scalar(connection, "SELECT sum(order_count) FROM ads_hourly_supply_demand") == 568_546

        system_acceptance = scalar(connection, "SELECT avg(accepted_flag) FROM dwd_waybill")
        courier_acceptance = scalar(connection, "SELECT avg(acceptance_rate) FROM dws_courier_efficiency")
        courier_delivery = scalar(connection, "SELECT avg(avg_delivery_minutes) FROM dws_courier_efficiency WHERE valid_delivery_count > 0")
        assert close(system_acceptance, 0.8689, 0.0002)
        assert close(courier_acceptance, 0.8474, 0.0002)
        assert close(courier_delivery, 27.10, 0.02)

        formula_failures = scalar(
            connection,
            """
            SELECT count(*) FROM ads_hourly_supply_demand
            WHERE capacity_orders_proxy IS NOT NULL
              AND abs(capacity_orders_proxy - online_courier_count * 60.0 / avg_delivery_minutes) > 1e-9
            """,
        )
        assert formula_failures == 0

        overview_rows = row_counts["ads_operations_overview"]
        hourly_rows = row_counts["ads_hourly_supply_demand"]
        valid_idle = scalar(connection, "SELECT count(idle_minutes_nonnegative) FROM dwd_courier_wave")
        negative_idle = scalar(connection, "SELECT count(*) FROM dwd_courier_wave WHERE idle_minutes_raw < 0")
        late_rate = scalar(connection, "SELECT avg(late_flag) FROM dwd_waybill WHERE completed_flag=1")
        avg_delivery = scalar(connection, "SELECT avg(delivery_minutes) FROM dwd_waybill WHERE completed_flag=1")
        avg_e2e = scalar(connection, "SELECT avg(end_to_end_minutes) FROM dwd_waybill WHERE completed_flag=1")

    print("Stage-2 validation passed.")
    print("Core object rows:")
    for name in CORE_OBJECTS:
        print(f"- {name}: {row_counts[name]:,}")
    print(f"Overview dates: {overview_rows:,}; hourly rows: {hourly_rows:,}")
    print(f"Valid nonnegative idle gaps: {valid_idle:,}; overlapping gaps: {negative_idle:,}")
    print(f"Waybill-weighted acceptance rate: {system_acceptance:.4%}")
    print(f"Courier-unweighted acceptance rate: {courier_acceptance:.4%}")
    print(f"Completed-waybill average delivery: {avg_delivery:.2f} minutes")
    print(f"Completed-waybill average end-to-end: {avg_e2e:.2f} minutes")
    print(f"Completed-waybill late rate: {late_rate:.4%}")


if __name__ == "__main__":
    main()
