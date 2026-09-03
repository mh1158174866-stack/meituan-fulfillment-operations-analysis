#!/usr/bin/env python3
"""Stage-1 audit for the official Meituan INFORMS TSL dataset.

The generated JSON is local-only and contains aggregate statistics, never raw IDs,
coordinates, or row-level samples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CSV_NAMES = (
    "all_waybill_info_meituan_0322.csv",
    "courier_wave_info_meituan.csv",
    "dispatch_rider_meituan.csv",
    "dispatch_waybill_meituan.csv",
)

TIME_COLUMNS = {
    "all_waybill_info_meituan_0322.csv": (
        "platform_order_time",
        "order_push_time",
        "dispatch_time",
        "grab_time",
        "fetch_time",
        "arrive_time",
        "estimate_arrived_time",
        "estimate_meal_prepare_time",
    ),
    "courier_wave_info_meituan.csv": ("wave_start_time", "wave_end_time"),
    "dispatch_rider_meituan.csv": ("dispatch_time",),
    "dispatch_waybill_meituan.csv": ("dispatch_time",),
}


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    default_data = (
        project_root
        / "data"
        / "raw"
        / "Meituan-INFORMS-TSL-Research-Challenge"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "data" / "interim" / "stage1_audit.json",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def date_from_epoch(series: pd.Series, timezone: str) -> pd.Series:
    converted = pd.to_datetime(series.where(series > 0), unit="s", utc=True)
    if timezone != "UTC":
        converted = converted.dt.tz_convert(timezone)
    return converted.dt.strftime("%Y%m%d").astype("Int64")


def mismatch_summary(dt: pd.Series, timestamp: pd.Series) -> dict[str, Any]:
    valid = timestamp.gt(0) & dt.notna()
    dt_int = dt.astype("Int64")
    result: dict[str, Any] = {"valid_rows": int(valid.sum())}
    for label, timezone in (("utc", "UTC"), ("asia_shanghai", "Asia/Shanghai")):
        business_date = date_from_epoch(timestamp, timezone)
        matches = valid & dt_int.eq(business_date)
        result[f"{label}_matches"] = int(matches.sum())
        result[f"{label}_match_rate"] = safe_rate(int(matches.sum()), int(valid.sum()))
        result[f"{label}_mismatches"] = int((valid & ~dt_int.eq(business_date)).sum())
        valid_dates = business_date[valid].dropna()
        result[f"{label}_business_date_min"] = (
            int(valid_dates.min()) if not valid_dates.empty else None
        )
        result[f"{label}_business_date_max"] = (
            int(valid_dates.max()) if not valid_dates.empty else None
        )
    return result


def file_summary(path: Path, frame: pd.DataFrame) -> dict[str, Any]:
    nulls = frame.isna().sum()
    zero_counts = {
        column: int(frame[column].eq(0).sum())
        for column in frame.select_dtypes(include="number").columns
    }
    return {
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "encoding": "utf-8",
        "rows": len(frame),
        "columns": len(frame.columns),
        "column_names": list(frame.columns),
        "dtypes": frame.dtypes.astype(str).to_dict(),
        "duplicate_rows": int(frame.duplicated().sum()),
        "duplicate_rate": safe_rate(int(frame.duplicated().sum()), len(frame)),
        "null_cells": int(nulls.sum()),
        "columns_with_nulls": {
            column: int(count) for column, count in nulls.items() if count
        },
        "zero_counts_numeric": zero_counts,
        "dt_min": int(frame["dt"].min()) if "dt" in frame else None,
        "dt_max": int(frame["dt"].max()) if "dt" in frame else None,
    }


def key_summary(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    waybill = frames[CSV_NAMES[0]]
    waves = frames[CSV_NAMES[1]]
    riders = frames[CSV_NAMES[2]]
    dispatch = frames[CSV_NAMES[3]]
    return {
        "all_waybill": {
            "unique_order_ids": int(waybill["order_id"].nunique()),
            "unique_waybill_ids": int(waybill["waybill_id"].nunique()),
            "unique_courier_ids": int(waybill["courier_id"].nunique()),
            "duplicate_waybill_ids": int(waybill["waybill_id"].duplicated().sum()),
            "orders_with_multiple_waybills": int(
                waybill.groupby("order_id")["waybill_id"].nunique().gt(1).sum()
            ),
            "max_waybills_per_order": int(
                waybill.groupby("order_id")["waybill_id"].nunique().max()
            ),
        },
        "courier_wave": {
            "unique_courier_ids": int(waves["courier_id"].nunique()),
            "duplicate_composite_keys": int(
                waves.duplicated(["dt", "courier_id", "wave_id"]).sum()
            ),
            "unique_composite_keys": int(
                waves[["dt", "courier_id", "wave_id"]].drop_duplicates().shape[0]
            ),
        },
        "dispatch_waybill": {
            "unique_orders": int(dispatch["order_id"].nunique()),
            "duplicate_rows_on_checkpoint_order": int(
                dispatch.duplicated(["dt", "dispatch_time", "order_id"]).sum()
            ),
            "unique_checkpoints": int(
                dispatch[["dt", "dispatch_time"]].drop_duplicates().shape[0]
            ),
        },
        "dispatch_rider": {
            "unique_couriers": int(riders["courier_id"].nunique()),
            "duplicate_rows_on_checkpoint_courier": int(
                riders.duplicated(["dt", "dispatch_time", "courier_id"]).sum()
            ),
            "unique_checkpoints": int(
                riders[["dt", "dispatch_time"]].drop_duplicates().shape[0]
            ),
        },
    }


def time_summary(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    anchors = {
        CSV_NAMES[0]: "platform_order_time",
        CSV_NAMES[1]: "wave_start_time",
        CSV_NAMES[2]: "dispatch_time",
        CSV_NAMES[3]: "dispatch_time",
    }
    for name, frame in frames.items():
        columns: dict[str, Any] = {}
        for column in TIME_COLUMNS[name]:
            valid = frame[column][frame[column] > 0]
            columns[column] = {
                "zero_count": int(frame[column].eq(0).sum()),
                "min_epoch": int(valid.min()) if not valid.empty else None,
                "max_epoch": int(valid.max()) if not valid.empty else None,
                "min_utc": pd.to_datetime(valid.min(), unit="s", utc=True).isoformat()
                if not valid.empty
                else None,
                "max_utc": pd.to_datetime(valid.max(), unit="s", utc=True).isoformat()
                if not valid.empty
                else None,
            }
        summaries[name] = {
            "anchor": anchors[name],
            "dt_vs_anchor": mismatch_summary(frame["dt"], frame[anchors[name]]),
            "columns": columns,
        }
    return summaries


def event_order_summary(waybill: pd.DataFrame) -> dict[str, Any]:
    pairs = (
        ("platform_order_time", "order_push_time"),
        ("order_push_time", "dispatch_time"),
        ("dispatch_time", "grab_time"),
        ("grab_time", "fetch_time"),
        ("fetch_time", "arrive_time"),
    )
    results: dict[str, Any] = {}
    for left, right in pairs:
        valid = waybill[left].gt(0) & waybill[right].gt(0)
        violation = valid & waybill[left].gt(waybill[right])
        results[f"{left}_le_{right}"] = {
            "valid_rows": int(valid.sum()),
            "violations": int(violation.sum()),
            "violation_rate": safe_rate(int(violation.sum()), int(valid.sum())),
        }
    return results


def waybill_dt_detail(waybill: pd.DataFrame) -> dict[str, Any]:
    business_date = date_from_epoch(waybill["platform_order_time"], "Asia/Shanghai")
    dt_date = pd.to_datetime(waybill["dt"].astype(str), format="%Y%m%d")
    business_date_ts = pd.to_datetime(
        business_date.astype(str), format="%Y%m%d", errors="coerce"
    )
    offsets = (dt_date - business_date_ts).dt.days
    mismatch = waybill["dt"].astype("Int64").ne(business_date)
    by_prebook: dict[str, Any] = {}
    for flag in (0, 1):
        mask = waybill["is_prebook"].eq(flag)
        by_prebook[str(flag)] = {
            "rows": int(mask.sum()),
            "mismatches": int((mask & mismatch).sum()),
            "match_rate": safe_rate(int((mask & ~mismatch).sum()), int(mask.sum())),
        }
    return {
        "timezone": "Asia/Shanghai",
        "mismatches": int(mismatch.sum()),
        "by_is_prebook": by_prebook,
        "dt_minus_business_date_days": {
            str(int(key)): int(value)
            for key, value in offsets.value_counts().sort_index().items()
        },
    }


def association_summary(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    waybill = frames[CSV_NAMES[0]]
    waves = frames[CSV_NAMES[1]]
    riders = frames[CSV_NAMES[2]]
    dispatch = frames[CSV_NAMES[3]]

    dispatch_orders = dispatch[["dt", "order_id"]].drop_duplicates()
    all_orders = waybill[["dt", "order_id"]].drop_duplicates()
    order_link = dispatch_orders.merge(all_orders, on=["dt", "order_id"], how="left", indicator=True)

    dispatch_checkpoints = dispatch[["dt", "dispatch_time"]].drop_duplicates()
    rider_checkpoints = riders[["dt", "dispatch_time"]].drop_duplicates()
    checkpoint_link = dispatch_checkpoints.merge(
        rider_checkpoints, on=["dt", "dispatch_time"], how="outer", indicator=True
    )

    all_order_set = set(waybill["order_id"].astype(str))
    total_wave_refs = 0
    matched_wave_refs = 0
    rows_without_refs = 0
    for value in waves["order_ids"].fillna(""):
        refs = re.findall(r"\d+", str(value))
        if not refs:
            rows_without_refs += 1
        total_wave_refs += len(refs)
        matched_wave_refs += sum(ref in all_order_set for ref in refs)

    return {
        "dispatch_order_to_all_waybill": {
            "unique_dispatch_dt_orders": len(dispatch_orders),
            "matched": int(order_link["_merge"].eq("both").sum()),
            "coverage_rate": safe_rate(
                int(order_link["_merge"].eq("both").sum()), len(dispatch_orders)
            ),
        },
        "dispatch_checkpoint_to_candidate_rider": {
            "dispatch_checkpoints": len(dispatch_checkpoints),
            "rider_checkpoints": len(rider_checkpoints),
            "both": int(checkpoint_link["_merge"].eq("both").sum()),
            "dispatch_only": int(checkpoint_link["_merge"].eq("left_only").sum()),
            "rider_only": int(checkpoint_link["_merge"].eq("right_only").sum()),
            "dispatch_coverage_rate": safe_rate(
                int(checkpoint_link["_merge"].eq("both").sum()),
                len(dispatch_checkpoints),
            ),
            "rider_coverage_rate": safe_rate(
                int(checkpoint_link["_merge"].eq("both").sum()), len(rider_checkpoints)
            ),
        },
        "wave_order_references_to_all_waybill": {
            "wave_rows_without_parseable_order_refs": rows_without_refs,
            "total_references": total_wave_refs,
            "matched_references": matched_wave_refs,
            "coverage_rate": safe_rate(matched_wave_refs, total_wave_refs),
        },
    }


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    radius = 6371.0088
    # The thesis text says 1e7, but its before/after example and reproduced
    # 1.90 km courier mean show that the actual coordinate scale is 1e6.
    phi1 = np.radians(lat1 / 1_000_000)
    phi2 = np.radians(lat2 / 1_000_000)
    delta_phi = np.radians((lat2 - lat1) / 1_000_000)
    delta_lambda = np.radians((lon2 - lon1) / 1_000_000)
    a = np.sin(delta_phi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2) ** 2
    return pd.Series(2 * radius * np.arctan2(np.sqrt(a), np.sqrt(1 - a)), index=lat1.index)


def kpi_summary(waybill: pd.DataFrame, waves: pd.DataFrame) -> dict[str, Any]:
    accepted = waybill[waybill["is_courier_grabbed"].eq(1)].copy()
    rejected = waybill[waybill["is_courier_grabbed"].eq(0)]

    courier_acceptance = waybill.groupby("courier_id")["is_courier_grabbed"].mean()
    accepted["delivery_minutes"] = (accepted["arrive_time"] - accepted["grab_time"]) / 60
    valid_delivery = accepted[accepted["delivery_minutes"].ge(0)]
    courier_delivery = valid_delivery.groupby("courier_id")["delivery_minutes"].mean()

    accepted["distance_km"] = haversine_km(
        accepted["sender_lat"],
        accepted["sender_lng"],
        accepted["recipient_lat"],
        accepted["recipient_lng"],
    )
    courier_distance = accepted.groupby("courier_id")["distance_km"].mean()

    ordered_waves = waves.sort_values(["courier_id", "dt", "wave_start_time", "wave_end_time"]).copy()
    ordered_waves["next_start"] = ordered_waves.groupby(["courier_id", "dt"])["wave_start_time"].shift(-1)
    inactive = (ordered_waves["next_start"] - ordered_waves["wave_end_time"]) / 60
    inactive = inactive[inactive.ge(0)]

    inactive_reference = inactive[inactive.le(240)]

    return {
        "acceptance": {
            "waybill_weighted_rate": float(waybill["is_courier_grabbed"].mean()),
            "accepted_waybills": len(accepted),
            "rejected_waybills": len(rejected),
            "couriers": int(courier_acceptance.size),
            "courier_unweighted_mean": float(courier_acceptance.mean()),
            "courier_median": float(courier_acceptance.median()),
            "courier_q25": float(courier_acceptance.quantile(0.25)),
            "courier_q75": float(courier_acceptance.quantile(0.75)),
        },
        "delivery_minutes_from_grab_to_arrive": {
            "accepted_rows": len(accepted),
            "valid_nonnegative_rows": len(valid_delivery),
            "waybill_weighted_mean": float(valid_delivery["delivery_minutes"].mean()),
            "couriers": int(courier_delivery.size),
            "courier_unweighted_mean": float(courier_delivery.mean()),
            "courier_std": float(courier_delivery.std()),
            "courier_min": float(courier_delivery.min()),
            "courier_q25": float(courier_delivery.quantile(0.25)),
            "courier_median": float(courier_delivery.median()),
            "courier_q75": float(courier_delivery.quantile(0.75)),
            "courier_max": float(courier_delivery.max()),
        },
        "distance_km_sender_to_recipient": {
            "couriers": int(courier_distance.size),
            "courier_unweighted_mean": float(courier_distance.mean()),
            "courier_std": float(courier_distance.std()),
            "courier_max": float(courier_distance.max()),
        },
        "inactive_minutes_between_same_day_waves": {
            "valid_gaps": int(inactive.size),
            "mean": float(inactive.mean()),
            "median": float(inactive.median()),
            "q25": float(inactive.quantile(0.25)),
            "q75": float(inactive.quantile(0.75)),
            "max": float(inactive.max()),
        },
        "inactive_minutes_reference_cap_240": {
            "rule": "same-courier, same-dt, nonnegative consecutive-wave gaps capped at 240 minutes",
            "valid_gaps": int(inactive_reference.size),
            "excluded_above_240": int(inactive.gt(240).sum()),
            "mean": float(inactive_reference.mean()),
            "median": float(inactive_reference.median()),
            "q25": float(inactive_reference.quantile(0.25)),
            "q75": float(inactive_reference.quantile(0.75)),
            "max": float(inactive_reference.max()),
        },
        "rejected_zero_field_consistency": {
            column: int(rejected[column].eq(0).sum())
            for column in ("grab_time", "fetch_time", "arrive_time", "grab_lat", "grab_lng")
        },
    }


def peak_capacity_summary(waybill: pd.DataFrame) -> dict[str, Any]:
    completed = waybill[
        waybill["is_courier_grabbed"].eq(1) & waybill["arrive_time"].gt(0)
    ].copy()
    completed["order_datetime_utc"] = pd.to_datetime(
        completed["platform_order_time"], unit="s", utc=True
    )
    completed["business_date"] = completed["order_datetime_utc"].dt.strftime("%Y%m%d").astype(int)
    completed["window_start_hour"] = (completed["order_datetime_utc"].dt.hour // 4) * 4
    completed["delivery_minutes"] = (
        completed["arrive_time"] - completed["grab_time"]
    ) / 60
    completed["is_late"] = completed["arrive_time"].gt(
        completed["estimate_arrived_time"]
    )
    completed = completed[
        completed["business_date"].between(20221016, 20221024)
    ]
    grouped = (
        completed.groupby(["business_date", "window_start_hour"])
        .agg(
            unique_orders=("order_id", "nunique"),
            unique_couriers=("courier_id", "nunique"),
            average_delivery_minutes=("delivery_minutes", "mean"),
            late_rate=("is_late", "mean"),
        )
        .reset_index()
    )
    grouped["inferred_capacity_orders"] = (
        grouped["unique_couriers"] * 240 / grouped["average_delivery_minutes"]
    )
    grouped["demand_capacity_ratio"] = (
        grouped["unique_orders"] / grouped["inferred_capacity_orders"]
    )
    peak = grouped[grouped["window_start_hour"].eq(8)].copy()
    columns = [
        "business_date",
        "unique_orders",
        "unique_couriers",
        "average_delivery_minutes",
        "inferred_capacity_orders",
        "demand_capacity_ratio",
        "late_rate",
    ]
    return {
        "timezone": "UTC, matching the reference report's timestamp example",
        "window": "08:00-12:00",
        "formula": "unique_couriers * 240 / average_grab_to_arrive_minutes",
        "formula_status": "inferred from the report narrative; not printed as an explicit equation",
        "records": peak[columns].to_dict(orient="records"),
    }


def wave_quality_summary(waybill: pd.DataFrame, waves: pd.DataFrame) -> dict[str, Any]:
    accepted_events = waybill.loc[
        waybill["is_courier_grabbed"].eq(1),
        ["dt", "courier_id", "order_id", "grab_time", "arrive_time"],
    ]
    event_lookup = {
        (int(row.dt), str(int(row.courier_id)), str(int(row.order_id))): (
            int(row.grab_time),
            int(row.arrive_time),
        )
        for row in accepted_events.itertuples(index=False)
    }
    comparable = 0
    start_mismatched = 0
    start_total_abs_error = 0
    start_max_abs_error = 0
    end_mismatched = 0
    end_total_abs_error = 0
    end_max_abs_error = 0
    for row in waves.itertuples(index=False):
        refs = re.findall(r"\d+", str(row.order_ids))
        grabs = [
            event_lookup[(int(row.dt), str(int(row.courier_id)), ref)][0]
            for ref in refs
            if (int(row.dt), str(int(row.courier_id)), ref) in event_lookup
        ]
        arrivals = [
            event_lookup[(int(row.dt), str(int(row.courier_id)), ref)][1]
            for ref in refs
            if (int(row.dt), str(int(row.courier_id)), ref) in event_lookup
            and event_lookup[(int(row.dt), str(int(row.courier_id)), ref)][1] > 0
        ]
        if not grabs or not arrivals:
            continue
        comparable += 1
        start_error = abs(int(row.wave_start_time) - min(grabs))
        if start_error:
            start_mismatched += 1
            start_total_abs_error += start_error
            start_max_abs_error = max(start_max_abs_error, start_error)
        end_error = abs(int(row.wave_end_time) - max(arrivals))
        if end_error:
            end_mismatched += 1
            end_total_abs_error += end_error
            end_max_abs_error = max(end_max_abs_error, end_error)
    return {
        "comparable_wave_rows": comparable,
        "wave_start_mismatches": start_mismatched,
        "wave_start_mismatch_rate": safe_rate(start_mismatched, comparable),
        "wave_start_mean_abs_error_seconds_among_mismatches": safe_rate(
            start_total_abs_error, start_mismatched
        ),
        "wave_start_max_abs_error_seconds": start_max_abs_error,
        "wave_end_mismatches": end_mismatched,
        "wave_end_mismatch_rate": safe_rate(end_mismatched, comparable),
        "wave_end_mean_abs_error_seconds_among_mismatches": safe_rate(
            end_total_abs_error, end_mismatched
        ),
        "wave_end_max_abs_error_seconds": end_max_abs_error,
    }


def main() -> None:
    args = parse_args()
    missing = [name for name in CSV_NAMES if not (args.data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing official CSV files: {missing}")

    frames: dict[str, pd.DataFrame] = {}
    for name in CSV_NAMES:
        frame = pd.read_csv(args.data_dir / name, low_memory=False)
        frame = frame.drop(columns=[column for column in frame if column.startswith("Unnamed:")])
        frames[name] = frame

    repo_commit = subprocess.run(
        ["git", "-C", str(args.data_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    report = {
        "official_source": {
            "url": "https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge",
            "commit": repo_commit,
            "license": "CC BY-NC 4.0; non-commercial; no redistribution without permission",
        },
        "files": {
            name: file_summary(args.data_dir / name, frame)
            for name, frame in frames.items()
        },
        "keys": key_summary(frames),
        "times": time_summary(frames),
        "waybill_dt_detail": waybill_dt_detail(frames[CSV_NAMES[0]]),
        "event_order": event_order_summary(frames[CSV_NAMES[0]]),
        "associations": association_summary(frames),
        "wave_start_quality": wave_quality_summary(frames[CSV_NAMES[0]], frames[CSV_NAMES[1]]),
        "reference_kpi_replication": kpi_summary(frames[CSV_NAMES[0]], frames[CSV_NAMES[1]]),
        "reference_peak_capacity_replication": peak_capacity_summary(frames[CSV_NAMES[0]]),
        "notes": [
            "All timestamps are audited in both UTC and Asia/Shanghai; official/reference material treats them as Unix seconds and the thesis describes UTC.",
            "The supplementary document says wave_start_time can be mis-indexed; wave starts are compared with the earliest accepted grab_time linked through order_ids.",
            "dispatch_time in dispatch inputs is a decision checkpoint, not proof of assignment.",
            "Reference KPIs are acceptance checks only and are not portfolio claims.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote aggregate audit report: {args.output}")
    print(f"Official commit: {repo_commit}")
    print("No raw IDs, coordinates, or row-level samples were written to the report.")


if __name__ == "__main__":
    main()
