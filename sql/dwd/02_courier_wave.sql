-- 桥表粒度：一行一个波次中的订单引用。只保存于 Git 忽略的本地分析库。
CREATE OR REPLACE TABLE dwd_order_wave_bridge AS
SELECT
    CAST(w.dt AS INTEGER) AS dt,
    CAST(w.courier_id AS BIGINT) AS courier_id,
    CAST(w.wave_id AS BIGINT) AS wave_id,
    CAST(token AS BIGINT) AS order_id
FROM ods_courier_wave AS w,
UNNEST(regexp_extract_all(CAST(w.order_ids AS VARCHAR), '[0-9]+')) AS parsed(token);

-- 波次粒度：(dt, courier_id, wave_id)。修正起点来自波次内完成订单的最早 grab_time。
CREATE OR REPLACE TABLE dwd_courier_wave AS
WITH linked_events AS (
    SELECT
        b.dt,
        b.courier_id,
        b.wave_id,
        count(*) AS linked_order_count,
        count(*) FILTER (WHERE wb.waybill_status = 'completed') AS completed_order_count,
        min(wb.grab_time_epoch) FILTER (WHERE wb.waybill_status = 'completed') AS corrected_start_epoch,
        max(wb.arrive_time_epoch) FILTER (WHERE wb.waybill_status = 'completed') AS derived_end_epoch,
        avg(wb.delivery_minutes) FILTER (WHERE wb.waybill_status = 'completed') AS avg_delivery_minutes
    FROM dwd_order_wave_bridge AS b
    LEFT JOIN dwd_waybill AS wb
      ON wb.dt = b.dt
     AND wb.courier_id = b.courier_id
     AND wb.order_id = b.order_id
     AND wb.waybill_status = 'completed'
    GROUP BY 1, 2, 3
), base AS (
    SELECT
        CAST(w.dt AS INTEGER) AS dt,
        CAST(w.courier_id AS BIGINT) AS courier_id,
        CAST(w.wave_id AS BIGINT) AS wave_id,
        CAST(w.wave_start_time AS BIGINT) AS wave_start_time_original_epoch,
        CAST(w.wave_end_time AS BIGINT) AS wave_end_time_epoch,
        e.corrected_start_epoch AS wave_start_time_corrected_epoch,
        e.derived_end_epoch AS wave_end_time_derived_epoch,
        e.linked_order_count,
        e.completed_order_count,
        e.avg_delivery_minutes,
        CAST(w.wave_start_time <> e.corrected_start_epoch AS UTINYINT) AS wave_start_mismatch_flag,
        CAST(w.wave_end_time <> e.derived_end_epoch AS UTINYINT) AS wave_end_mismatch_flag,
        abs(w.wave_start_time - e.corrected_start_epoch) AS wave_start_abs_error_seconds,
        w.wave_end_time - e.corrected_start_epoch AS corrected_wave_duration_seconds
    FROM ods_courier_wave AS w
    LEFT JOIN linked_events AS e
      ON CAST(w.dt AS INTEGER) = e.dt
     AND CAST(w.courier_id AS BIGINT) = e.courier_id
     AND CAST(w.wave_id AS BIGINT) = e.wave_id
), sequenced AS (
    SELECT
        *,
        lead(wave_start_time_corrected_epoch) OVER (
            PARTITION BY dt, courier_id
            ORDER BY wave_start_time_corrected_epoch, wave_end_time_epoch, wave_id
        ) AS next_wave_start_time_corrected_epoch
    FROM base
)
SELECT
    *,
    to_timestamp(wave_start_time_original_epoch) AT TIME ZONE 'UTC' AS wave_start_time_original_utc,
    to_timestamp(wave_start_time_original_epoch) AT TIME ZONE 'Asia/Shanghai' AS wave_start_time_original_cn,
    to_timestamp(wave_start_time_corrected_epoch) AT TIME ZONE 'UTC' AS wave_start_time_corrected_utc,
    to_timestamp(wave_start_time_corrected_epoch) AT TIME ZONE 'Asia/Shanghai' AS wave_start_time_corrected_cn,
    to_timestamp(wave_end_time_epoch) AT TIME ZONE 'UTC' AS wave_end_time_utc,
    to_timestamp(wave_end_time_epoch) AT TIME ZONE 'Asia/Shanghai' AS wave_end_time_cn,
    corrected_wave_duration_seconds / 60.0 AS corrected_wave_duration_minutes,
    CASE
        WHEN next_wave_start_time_corrected_epoch IS NOT NULL
        THEN (next_wave_start_time_corrected_epoch - wave_end_time_epoch) / 60.0
    END AS idle_minutes_raw,
    CASE
        WHEN next_wave_start_time_corrected_epoch >= wave_end_time_epoch
        THEN (next_wave_start_time_corrected_epoch - wave_end_time_epoch) / 60.0
    END AS idle_minutes_nonnegative,
    CASE
        WHEN next_wave_start_time_corrected_epoch >= wave_end_time_epoch
         AND next_wave_start_time_corrected_epoch - wave_end_time_epoch <= 14400
        THEN (next_wave_start_time_corrected_epoch - wave_end_time_epoch) / 60.0
    END AS idle_minutes_reference_cap_240,
    CASE
        WHEN avg_delivery_minutes > 0
        THEN (corrected_wave_duration_seconds / 60.0) / avg_delivery_minutes
    END AS wave_capacity_orders_proxy,
    CASE
        WHEN avg_delivery_minutes > 0 AND corrected_wave_duration_seconds > 0
        THEN completed_order_count / ((corrected_wave_duration_seconds / 60.0) / avg_delivery_minutes)
    END AS wave_load_capacity_ratio
FROM sequenced;
