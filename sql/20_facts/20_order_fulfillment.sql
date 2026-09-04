CREATE OR REPLACE TABLE fact.fact_order_fulfillment AS
WITH accepted AS (
    SELECT *
    FROM stg.waybill_attempt
    WHERE is_courier_grabbed = 1
),
attempt_rollup AS (
    SELECT
        order_id,
        min(order_push_time) AS first_order_push_time,
        min(nullif(dispatch_time, 0)) AS first_dispatch_time,
        count(*) AS attempt_count,
        count(*) FILTER (WHERE is_courier_grabbed = 0) AS rejection_count,
        greatest(count(*) - 1, 0) AS redispatch_count,
        bool_or(has_event_order_error) AS has_event_order_error,
        bool_or(has_dt_inconsistency) AS has_dt_inconsistency,
        bool_or(has_prebook_inconsistency) AS has_prebook_inconsistency,
        bool_or(has_order_time_inconsistency) AS has_order_time_inconsistency
    FROM stg.waybill_attempt
    GROUP BY order_id
)
SELECT
    a.order_id,
    a.waybill_id AS accepted_waybill_id,
    a.courier_id AS accepted_courier_id,
    a.dt,
    a.da_id,
    a.poi_id,
    a.is_weekend,
    a.is_prebook,
    r.first_order_push_time,
    r.first_dispatch_time,
    a.dispatch_time AS final_dispatch_time,
    a.grab_time AS accepted_time,
    a.fetch_time,
    a.arrive_time,
    a.platform_order_time,
    a.estimate_arrived_time,
    a.estimate_meal_prepare_time,
    to_timestamp(r.first_order_push_time) AS first_order_push_ts,
    to_timestamp(r.first_dispatch_time) AS first_dispatch_ts,
    a.dispatch_ts AS final_dispatch_ts,
    a.grab_ts AS accepted_ts,
    a.fetch_ts,
    a.arrive_ts,
    a.platform_order_ts,
    a.estimate_arrived_ts,
    a.estimate_meal_prepare_ts,
    r.attempt_count,
    r.rejection_count,
    r.redispatch_count,
    true AS is_accepted,
    (a.arrive_time > 0) AS is_completed,
    a.is_incomplete_accepted,
    (r.has_dt_inconsistency OR r.has_prebook_inconsistency OR r.has_order_time_inconsistency)
        AS has_cross_waybill_attribute_inconsistency,
    r.has_dt_inconsistency,
    r.has_prebook_inconsistency,
    r.has_order_time_inconsistency,
    r.has_event_order_error,
    CASE WHEN r.first_order_push_time >= a.platform_order_time
        THEN r.first_order_push_time - a.platform_order_time END AS order_to_push_seconds,
    CASE WHEN r.first_dispatch_time >= r.first_order_push_time
        THEN r.first_dispatch_time - r.first_order_push_time END AS push_to_first_dispatch_seconds,
    CASE WHEN a.grab_time >= r.first_dispatch_time
        THEN a.grab_time - r.first_dispatch_time END AS first_dispatch_to_accept_seconds,
    CASE WHEN a.dispatch_time > 0 AND a.grab_time >= a.dispatch_time
        THEN a.grab_time - a.dispatch_time END AS final_dispatch_to_accept_seconds,
    CASE WHEN a.fetch_time >= a.grab_time
        THEN a.fetch_time - a.grab_time END AS accept_to_fetch_seconds,
    CASE WHEN a.arrive_time > 0 AND a.arrive_time >= a.fetch_time
        THEN a.arrive_time - a.fetch_time END AS fetch_to_arrive_seconds,
    CASE WHEN a.arrive_time > 0 AND a.arrive_time >= a.platform_order_time
        THEN a.arrive_time - a.platform_order_time END AS end_to_end_seconds,
    CASE WHEN a.estimate_meal_prepare_time > 0
        THEN a.fetch_time - a.estimate_meal_prepare_time END AS pickup_delay_seconds,
    sqrt(
        pow(a.recipient_lng - a.sender_lng, 2)
        + pow(a.recipient_lat - a.sender_lat, 2)
    ) AS delivery_distance_coordinate_units
FROM accepted AS a
JOIN attempt_rollup AS r USING (order_id);
