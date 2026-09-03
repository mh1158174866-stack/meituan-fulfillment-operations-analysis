-- 粒度：一行一种异常类型；只保留聚合计数、分母、比例与阈值。
CREATE OR REPLACE TABLE ads_anomaly_diagnosis AS
WITH delivery_threshold AS (
    SELECT quantile_cont(delivery_minutes, 0.99) AS threshold
    FROM dwd_waybill WHERE delivery_minutes IS NOT NULL
), distance_threshold AS (
    SELECT quantile_cont(delivery_distance_km, 0.99) AS threshold
    FROM dwd_waybill WHERE delivery_distance_km IS NOT NULL
), anomaly_rows AS (
    SELECT 'rejected_waybill' AS anomaly_type,
           count(*) FILTER (WHERE waybill_status = 'rejected')::BIGINT AS anomaly_count,
           count(*)::BIGINT AS denominator_count,
           NULL::DOUBLE AS threshold_value, 'waybill' AS threshold_unit
    FROM dwd_waybill
    UNION ALL
    SELECT 'accepted_unfinished',
           count(*) FILTER (WHERE waybill_status = 'accepted_unfinished')::BIGINT,
           count(*) FILTER (WHERE accepted_flag = 1)::BIGINT,
           NULL::DOUBLE, 'waybill'
    FROM dwd_waybill
    UNION ALL
    SELECT 'late_completed',
           count(*) FILTER (WHERE late_flag = 1)::BIGINT,
           count(late_flag)::BIGINT,
           NULL::DOUBLE, 'completed_waybill'
    FROM dwd_waybill
    UNION ALL
    SELECT 'event_order_anomaly',
           sum(event_order_anomaly_flag)::BIGINT,
           count(*)::BIGINT,
           NULL::DOUBLE, 'waybill'
    FROM dwd_waybill
    UNION ALL
    SELECT 'delivery_above_p99',
           count(*) FILTER (WHERE delivery_minutes > t.threshold)::BIGINT,
           count(delivery_minutes)::BIGINT,
           t.threshold, 'minute'
    FROM dwd_waybill, delivery_threshold AS t
    GROUP BY t.threshold
    UNION ALL
    SELECT 'distance_above_p99',
           count(*) FILTER (WHERE delivery_distance_km > t.threshold)::BIGINT,
           count(delivery_distance_km)::BIGINT,
           t.threshold, 'kilometer'
    FROM dwd_waybill, distance_threshold AS t
    GROUP BY t.threshold
    UNION ALL
    SELECT 'wave_start_mismatch',
           sum(wave_start_mismatch_flag)::BIGINT,
           count(*)::BIGINT,
           0::DOUBLE, 'second'
    FROM dwd_courier_wave
    UNION ALL
    SELECT 'wave_end_mismatch',
           sum(wave_end_mismatch_flag)::BIGINT,
           count(*)::BIGINT,
           0::DOUBLE, 'second'
    FROM dwd_courier_wave
    UNION ALL
    SELECT 'negative_wave_duration',
           count(*) FILTER (WHERE corrected_wave_duration_minutes < 0)::BIGINT,
           count(*)::BIGINT,
           0::DOUBLE, 'minute'
    FROM dwd_courier_wave
    UNION ALL
    SELECT 'overlapping_consecutive_wave',
           count(*) FILTER (WHERE idle_minutes_raw < 0)::BIGINT,
           count(idle_minutes_raw)::BIGINT,
           0::DOUBLE, 'minute'
    FROM dwd_courier_wave
    UNION ALL
    SELECT 'idle_gap_above_240_minutes',
           count(*) FILTER (WHERE idle_minutes_nonnegative > 240)::BIGINT,
           count(idle_minutes_nonnegative)::BIGINT,
           240::DOUBLE, 'minute'
    FROM dwd_courier_wave
)
SELECT
    anomaly_type,
    anomaly_count,
    denominator_count,
    anomaly_count / denominator_count::DOUBLE AS anomaly_rate,
    threshold_value,
    threshold_unit
FROM anomaly_rows
ORDER BY anomaly_type;
