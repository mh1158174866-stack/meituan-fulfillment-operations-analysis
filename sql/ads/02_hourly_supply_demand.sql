-- 粒度：Asia/Shanghai 平台下单小时。运力为修正波次与该小时有重叠的去重骑手数。
CREATE OR REPLACE TABLE ads_hourly_supply_demand AS
WITH order_level AS (
    SELECT * EXCLUDE (rn)
    FROM (
        SELECT
            order_id,
            courier_id,
            is_prebook,
            completed_flag,
            delivery_minutes,
            late_flag,
            date_trunc('hour', platform_order_time_cn) AS business_hour_cn,
            row_number() OVER (PARTITION BY order_id ORDER BY accepted_flag DESC, waybill_id) AS rn
        FROM dwd_waybill
    )
    WHERE rn = 1
), demand AS (
    SELECT
        business_hour_cn,
        count(*) AS order_count,
        count(*) FILTER (WHERE completed_flag = 1) AS completed_order_count,
        count(*) FILTER (WHERE is_prebook = 1) AS prebook_order_count,
        avg(delivery_minutes) FILTER (WHERE completed_flag = 1) AS avg_delivery_minutes,
        avg(late_flag) FILTER (WHERE completed_flag = 1) AS late_rate,
        count(delivery_minutes) AS valid_delivery_count,
        count(late_flag) AS valid_late_count
    FROM order_level
    GROUP BY 1
), assignment AS (
    SELECT
        date_trunc('hour', platform_order_time_cn) AS business_hour_cn,
        count(*) AS assigned_waybill_count,
        count(*) FILTER (WHERE waybill_status = 'rejected') AS rejected_waybill_count
    FROM dwd_waybill
    GROUP BY 1
), wave_hours AS (
    SELECT DISTINCT
        w.courier_id,
        hour_cn AS business_hour_cn
    FROM dwd_courier_wave AS w,
    UNNEST(generate_series(
        date_trunc('hour', w.wave_start_time_corrected_cn),
        date_trunc('hour', w.wave_end_time_cn),
        INTERVAL 1 HOUR
    )) AS expanded(hour_cn)
    WHERE w.corrected_wave_duration_seconds >= 0
), supply AS (
    SELECT business_hour_cn, count(DISTINCT courier_id) AS online_courier_count
    FROM wave_hours
    GROUP BY 1
), hours AS (
    SELECT business_hour_cn FROM demand
    UNION
    SELECT business_hour_cn FROM supply
)
SELECT
    h.business_hour_cn,
    CAST(h.business_hour_cn AS DATE) AS business_date_cn,
    extract('hour' FROM h.business_hour_cn)::INTEGER AS hour_cn,
    CASE
        WHEN extract('hour' FROM h.business_hour_cn) BETWEEN 6 AND 9 THEN 'breakfast'
        WHEN extract('hour' FROM h.business_hour_cn) BETWEEN 10 AND 13 THEN 'lunch'
        WHEN extract('hour' FROM h.business_hour_cn) BETWEEN 14 AND 16 THEN 'afternoon'
        WHEN extract('hour' FROM h.business_hour_cn) BETWEEN 17 AND 20 THEN 'dinner'
        ELSE 'late_night_other'
    END AS daypart,
    coalesce(d.order_count, 0) AS order_count,
    coalesce(d.completed_order_count, 0) AS completed_order_count,
    coalesce(a.assigned_waybill_count, 0) AS assigned_waybill_count,
    coalesce(a.rejected_waybill_count, 0) AS rejected_waybill_count,
    coalesce(d.prebook_order_count, 0) AS prebook_order_count,
    coalesce(s.online_courier_count, 0) AS online_courier_count,
    d.avg_delivery_minutes,
    d.late_rate,
    coalesce(d.valid_delivery_count, 0) AS valid_delivery_count,
    coalesce(d.valid_late_count, 0) AS valid_late_count,
    CASE
        WHEN s.online_courier_count > 0
        THEN d.order_count / s.online_courier_count::DOUBLE
    END AS orders_per_online_courier,
    CASE
        WHEN s.online_courier_count > 0 AND d.avg_delivery_minutes > 0
        THEN s.online_courier_count * 60.0 / d.avg_delivery_minutes
    END AS capacity_orders_proxy,
    CASE
        WHEN s.online_courier_count > 0 AND d.avg_delivery_minutes > 0
        THEN d.order_count / (s.online_courier_count * 60.0 / d.avg_delivery_minutes)
    END AS demand_capacity_ratio
FROM hours AS h
LEFT JOIN demand AS d USING (business_hour_cn)
LEFT JOIN assignment AS a USING (business_hour_cn)
LEFT JOIN supply AS s USING (business_hour_cn)
ORDER BY h.business_hour_cn;
