#!/usr/bin/env python3
"""Validate the aggregate stage-1 audit against official structural facts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "interim" / "stage1_audit.json"


def close(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def main() -> None:
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    files = data["files"]
    expected_rows = {
        "all_waybill_info_meituan_0322.csv": 654_343,
        "courier_wave_info_meituan.csv": 206_748,
        "dispatch_rider_meituan.csv": 62_044,
        "dispatch_waybill_meituan.csv": 15_921,
    }
    for name, rows in expected_rows.items():
        assert files[name]["rows"] == rows, (name, files[name]["rows"], rows)
        assert files[name]["duplicate_rows"] == 0, name
        assert files[name]["null_cells"] == 0, name

    keys = data["keys"]
    assert keys["all_waybill"]["duplicate_waybill_ids"] == 0
    assert keys["courier_wave"]["duplicate_composite_keys"] == 0
    assert keys["dispatch_waybill"]["duplicate_rows_on_checkpoint_order"] == 0
    assert keys["dispatch_rider"]["duplicate_rows_on_checkpoint_courier"] == 0

    for result in data["event_order"].values():
        assert result["violations"] == 0, result

    associations = data["associations"]
    assert associations["dispatch_order_to_all_waybill"]["coverage_rate"] == 1.0
    checkpoints = associations["dispatch_checkpoint_to_candidate_rider"]
    assert checkpoints["dispatch_coverage_rate"] == 1.0
    assert checkpoints["rider_coverage_rate"] == 1.0
    assert associations["wave_order_references_to_all_waybill"]["coverage_rate"] == 1.0

    wave_quality = data["wave_start_quality"]
    assert wave_quality["wave_start_mismatches"] > 0
    assert wave_quality["wave_end_mismatches"] == 0

    kpi = data["reference_kpi_replication"]
    acceptance = kpi["acceptance"]
    assert close(acceptance["courier_unweighted_mean"], 0.84, 0.02)
    delivery = kpi["delivery_minutes_from_grab_to_arrive"]
    assert close(delivery["courier_unweighted_mean"], 27.0, 0.2)
    distance = kpi["distance_km_sender_to_recipient"]
    assert close(distance["courier_unweighted_mean"], 1.86, 0.05)
    inactive = kpi["inactive_minutes_reference_cap_240"]
    assert close(inactive["mean"], 27.5, 0.2)

    peak = {
        row["business_date"]: row["demand_capacity_ratio"]
        for row in data["reference_peak_capacity_replication"]["records"]
    }
    assert all(peak[date] >= 1 for date in (20221021, 20221022, 20221023))
    assert all(peak[date] < 1 for date in (20221017, 20221018, 20221019, 20221020, 20221024))

    print("Stage-1 validation passed.")
    print("Area-focus KPIs are intentionally not asserted: recipient-area construction is undocumented.")


if __name__ == "__main__":
    main()
