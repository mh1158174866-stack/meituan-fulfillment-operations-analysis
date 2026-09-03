-- 粒度：一行一名骑手；是全期聚合，不用于因果解释个人能力。
CREATE OR REPLACE TABLE dws_courier_efficiency AS
WITH waybill_metrics AS (
    SELECT
        courier_id,
        count(*) AS assigned_waybill_count,
        count(*) FILTER (WHERE accepted_flag = 1) AS accepted_waybill_count,
        count(*) FILTER (WHERE completed_flag = 1) AS completed_waybill_count,
        count(DISTINCT order_id) AS unique_order_count,
        avg(accepted_flag) AS acceptance_rate,
        avg(delivery_minutes) FILTER (WHERE completed_flag = 1) AS avg_delivery_minutes,
        median(delivery_minutes) FILTER (WHERE completed_flag = 1) AS median_delivery_minutes,
        quantile_cont(delivery_minutes, 0.90) FILTER (WHERE completed_flag = 1) AS p90_delivery_minutes,
        avg(end_to_end_minutes) FILTER (WHERE completed_flag = 1) AS avg_end_to_end_minutes,
        avg(delivery_distance_km) FILTER (WHERE completed_flag = 1) AS avg_delivery_distance_km,
        avg(late_flag) FILTER (WHERE completed_flag = 1) AS late_rate,
        count(delivery_minutes) AS valid_delivery_count,
        count(delivery_distance_km) AS valid_distance_count,
        count(late_flag) AS valid_late_count
    FROM dwd_waybill
    GROUP BY courier_id
), wave_metrics AS (
    SELECT
        courier_id,
        count(*) AS wave_count,
        sum(completed_order_count) AS wave_completed_order_count,
        avg(completed_order_count) AS avg_completed_orders_per_wave,
        max(completed_order_count) AS max_completed_orders_per_wave,
        avg(corrected_wave_duration_minutes) AS avg_wave_duration_minutes,
        sum(corrected_wave_duration_minutes) / 60.0 AS total_wave_hours,
        avg(idle_minutes_nonnegative) AS avg_idle_minutes_nonnegative,
        median(idle_minutes_nonnegative) AS median_idle_minutes_nonnegative,
        count(idle_minutes_nonnegative) AS valid_idle_gap_count,
        count(*) FILTER (WHERE idle_minutes_raw < 0) AS overlapping_wave_gap_count,
        sum(wave_start_mismatch_flag) AS wave_start_mismatch_count
    FROM dwd_courier_wave
    GROUP BY courier_id
)
SELECT
    wb.*,
    w.wave_count,
    w.wave_completed_order_count,
    w.avg_completed_orders_per_wave,
    w.max_completed_orders_per_wave,
    w.avg_wave_duration_minutes,
    w.total_wave_hours,
    w.avg_idle_minutes_nonnegative,
    w.median_idle_minutes_nonnegative,
    w.valid_idle_gap_count,
    w.overlapping_wave_gap_count,
    w.wave_start_mismatch_count,
    CASE
        WHEN wb.avg_delivery_minutes > 0
        THEN (w.total_wave_hours * 60.0) / wb.avg_delivery_minutes
    END AS courier_capacity_orders_proxy,
    CASE
        WHEN wb.avg_delivery_minutes > 0 AND w.total_wave_hours > 0
        THEN wb.completed_waybill_count / ((w.total_wave_hours * 60.0) / wb.avg_delivery_minutes)
    END AS courier_load_capacity_ratio
FROM waybill_metrics AS wb
LEFT JOIN wave_metrics AS w USING (courier_id);
