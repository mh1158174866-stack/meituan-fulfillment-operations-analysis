-- 粒度：Asia/Shanghai 平台下单日。预约单按创建日归属。
CREATE OR REPLACE TABLE ads_operations_overview AS
WITH courier_day AS (
    SELECT business_date_cn, courier_id, avg(accepted_flag) AS courier_acceptance_rate
    FROM dwd_waybill
    GROUP BY 1, 2
), courier_day_mean AS (
    SELECT business_date_cn, avg(courier_acceptance_rate) AS courier_unweighted_acceptance_rate
    FROM courier_day
    GROUP BY 1
)
SELECT
    wb.business_date_cn,
    count(DISTINCT wb.order_id) AS order_count,
    count(*) AS assigned_waybill_count,
    count(*) FILTER (WHERE wb.accepted_flag = 1) AS accepted_waybill_count,
    count(*) FILTER (WHERE wb.completed_flag = 1) AS completed_waybill_count,
    count(*) FILTER (WHERE wb.waybill_status = 'rejected') AS rejected_waybill_count,
    count(*) FILTER (WHERE wb.waybill_status = 'accepted_unfinished') AS accepted_unfinished_count,
    count(DISTINCT wb.courier_id) AS courier_count,
    avg(wb.accepted_flag) AS waybill_weighted_acceptance_rate,
    c.courier_unweighted_acceptance_rate,
    count(DISTINCT wb.order_id) FILTER (WHERE wb.completed_flag = 1)
        / count(DISTINCT wb.order_id)::DOUBLE AS order_completion_rate,
    count(DISTINCT wb.order_id) FILTER (WHERE wb.is_prebook = 1)
        / count(DISTINCT wb.order_id)::DOUBLE AS prebook_order_rate,
    avg(wb.delivery_minutes) FILTER (WHERE wb.completed_flag = 1) AS avg_delivery_minutes,
    median(wb.delivery_minutes) FILTER (WHERE wb.completed_flag = 1) AS median_delivery_minutes,
    quantile_cont(wb.delivery_minutes, 0.90) FILTER (WHERE wb.completed_flag = 1) AS p90_delivery_minutes,
    avg(wb.end_to_end_minutes) FILTER (WHERE wb.completed_flag = 1) AS avg_end_to_end_minutes,
    avg(wb.delivery_distance_km) FILTER (WHERE wb.completed_flag = 1) AS avg_delivery_distance_km,
    avg(wb.late_flag) FILTER (WHERE wb.completed_flag = 1) AS late_rate,
    count(wb.delivery_minutes) AS valid_delivery_count,
    count(wb.end_to_end_minutes) AS valid_end_to_end_count,
    count(wb.delivery_distance_km) AS valid_distance_count,
    count(wb.late_flag) AS valid_late_count
FROM dwd_waybill AS wb
LEFT JOIN courier_day_mean AS c USING (business_date_cn)
GROUP BY wb.business_date_cn, c.courier_unweighted_acceptance_rate
ORDER BY wb.business_date_cn;
