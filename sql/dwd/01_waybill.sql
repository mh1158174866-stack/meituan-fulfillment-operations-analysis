-- 粒度：一行一个 waybill_id。一个 order_id 可因拒单对应多个运单。
CREATE OR REPLACE TABLE dwd_waybill AS
SELECT
    CAST(dt AS INTEGER) AS dt,
    CAST(order_id AS BIGINT) AS order_id,
    CAST(waybill_id AS BIGINT) AS waybill_id,
    CAST(courier_id AS BIGINT) AS courier_id,
    CAST(da_id AS BIGINT) AS da_id,
    CAST(is_courier_grabbed AS UTINYINT) AS is_courier_grabbed,
    CAST(is_weekend AS UTINYINT) AS is_weekend,
    CAST(is_prebook AS UTINYINT) AS is_prebook,
    CAST(poi_id AS BIGINT) AS poi_id,
    CAST(platform_order_time AS BIGINT) AS platform_order_time_epoch,
    CAST(order_push_time AS BIGINT) AS order_push_time_epoch,
    CAST(dispatch_time AS BIGINT) AS dispatch_time_epoch,
    CAST(grab_time AS BIGINT) AS grab_time_epoch,
    CAST(fetch_time AS BIGINT) AS fetch_time_epoch,
    CAST(arrive_time AS BIGINT) AS arrive_time_epoch,
    CAST(estimate_arrived_time AS BIGINT) AS estimate_arrived_time_epoch,
    CAST(estimate_meal_prepare_time AS BIGINT) AS estimate_meal_prepare_time_epoch,
    to_timestamp(platform_order_time) AT TIME ZONE 'UTC' AS platform_order_time_utc,
    to_timestamp(platform_order_time) AT TIME ZONE 'Asia/Shanghai' AS platform_order_time_cn,
    to_timestamp(order_push_time) AT TIME ZONE 'UTC' AS order_push_time_utc,
    to_timestamp(order_push_time) AT TIME ZONE 'Asia/Shanghai' AS order_push_time_cn,
    CASE WHEN dispatch_time > 0 THEN to_timestamp(dispatch_time) AT TIME ZONE 'UTC' END AS dispatch_time_utc,
    CASE WHEN dispatch_time > 0 THEN to_timestamp(dispatch_time) AT TIME ZONE 'Asia/Shanghai' END AS dispatch_time_cn,
    CASE WHEN grab_time > 0 THEN to_timestamp(grab_time) AT TIME ZONE 'UTC' END AS grab_time_utc,
    CASE WHEN grab_time > 0 THEN to_timestamp(grab_time) AT TIME ZONE 'Asia/Shanghai' END AS grab_time_cn,
    CASE WHEN fetch_time > 0 THEN to_timestamp(fetch_time) AT TIME ZONE 'UTC' END AS fetch_time_utc,
    CASE WHEN fetch_time > 0 THEN to_timestamp(fetch_time) AT TIME ZONE 'Asia/Shanghai' END AS fetch_time_cn,
    CASE WHEN arrive_time > 0 THEN to_timestamp(arrive_time) AT TIME ZONE 'UTC' END AS arrive_time_utc,
    CASE WHEN arrive_time > 0 THEN to_timestamp(arrive_time) AT TIME ZONE 'Asia/Shanghai' END AS arrive_time_cn,
    CAST(to_timestamp(platform_order_time) AT TIME ZONE 'Asia/Shanghai' AS DATE) AS business_date_cn,
    CAST(to_timestamp(order_push_time) AT TIME ZONE 'Asia/Shanghai' AS DATE) AS service_request_date_cn,
    CASE
        WHEN is_courier_grabbed = 0 THEN 'rejected'
        WHEN is_courier_grabbed = 1 AND arrive_time = 0 THEN 'accepted_unfinished'
        WHEN is_courier_grabbed = 1 AND arrive_time > 0 THEN 'completed'
        ELSE 'invalid_status'
    END AS waybill_status,
    CASE WHEN is_courier_grabbed = 1 THEN 1 ELSE 0 END AS accepted_flag,
    CASE WHEN is_courier_grabbed = 1 AND arrive_time > 0 THEN 1 ELSE 0 END AS completed_flag,
    CASE
        WHEN is_courier_grabbed = 1 AND arrive_time > 0
        THEN (arrive_time - grab_time) / 60.0
    END AS delivery_minutes,
    CASE
        WHEN is_courier_grabbed = 1 AND arrive_time > 0
        THEN (arrive_time - platform_order_time) / 60.0
    END AS end_to_end_minutes,
    CASE
        WHEN is_courier_grabbed = 1 AND arrive_time > 0
        THEN 2 * 6371.0088 * asin(sqrt(
            pow(sin(radians((recipient_lat - sender_lat) / 1000000.0) / 2), 2)
            + cos(radians(sender_lat / 1000000.0))
            * cos(radians(recipient_lat / 1000000.0))
            * pow(sin(radians((recipient_lng - sender_lng) / 1000000.0) / 2), 2)
        ))
    END AS delivery_distance_km,
    CASE
        WHEN is_courier_grabbed = 1 AND arrive_time > 0
        THEN CAST(arrive_time > estimate_arrived_time AS UTINYINT)
    END AS late_flag,
    CAST(
        (platform_order_time > 0 AND order_push_time > 0 AND platform_order_time > order_push_time)
        OR (order_push_time > 0 AND dispatch_time > 0 AND order_push_time > dispatch_time)
        OR (dispatch_time > 0 AND grab_time > 0 AND dispatch_time > grab_time)
        OR (grab_time > 0 AND fetch_time > 0 AND grab_time > fetch_time)
        OR (fetch_time > 0 AND arrive_time > 0 AND fetch_time > arrive_time)
        AS UTINYINT
    ) AS event_order_anomaly_flag
FROM ods_waybill;
