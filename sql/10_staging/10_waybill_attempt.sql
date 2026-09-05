CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS fact;

CREATE OR REPLACE TABLE stg.waybill_attempt AS
WITH attribute_versions AS (
    SELECT
        order_id,
        count(DISTINCT dt) AS dt_versions,
        count(DISTINCT is_prebook) AS prebook_versions,
        count(DISTINCT platform_order_time) AS order_time_versions
    FROM raw.waybill
    GROUP BY order_id
),
sequenced AS (
    SELECT
        w.*,
        row_number() OVER (
            PARTITION BY order_id
            ORDER BY nullif(dispatch_time, 0) NULLS LAST, source_row_index
        ) AS attempt_sequence,
        count(*) OVER (PARTITION BY order_id) AS attempt_count
    FROM raw.waybill AS w
)
SELECT
    s.*,
    to_timestamp(platform_order_time) AS platform_order_ts,
    to_timestamp(order_push_time) AS order_push_ts,
    to_timestamp(nullif(dispatch_time, 0)) AS dispatch_ts,
    to_timestamp(nullif(grab_time, 0)) AS grab_ts,
    to_timestamp(nullif(fetch_time, 0)) AS fetch_ts,
    to_timestamp(nullif(arrive_time, 0)) AS arrive_ts,
    to_timestamp(estimate_arrived_time) AS estimate_arrived_ts,
    to_timestamp(nullif(estimate_meal_prepare_time, 0)) AS estimate_meal_prepare_ts,
    (dispatch_time = 0) AS has_missing_dispatch_time,
    (is_courier_grabbed = 1 AND arrive_time = 0) AS is_incomplete_accepted,
    (is_courier_grabbed = 1 AND attempt_sequence = attempt_count)
        AS is_final_accepted_attempt,
    (
        platform_order_time > order_push_time
        OR (dispatch_time > 0 AND order_push_time > dispatch_time)
        OR (is_courier_grabbed = 1 AND dispatch_time > 0 AND dispatch_time > grab_time)
        OR (is_courier_grabbed = 1 AND grab_time > fetch_time)
        OR (is_courier_grabbed = 1 AND arrive_time > 0 AND fetch_time > arrive_time)
    ) AS has_event_order_error,
    (v.dt_versions > 1) AS has_dt_inconsistency,
    (v.prebook_versions > 1) AS has_prebook_inconsistency,
    (v.order_time_versions > 1) AS has_order_time_inconsistency
FROM sequenced AS s
JOIN attribute_versions AS v USING (order_id);

CREATE OR REPLACE TABLE fact.fact_waybill_attempt AS
SELECT
    waybill_id,
    order_id,
    courier_id,
    dt,
    da_id,
    poi_id,
    attempt_sequence,
    attempt_count,
    is_courier_grabbed,
    is_final_accepted_attempt,
    is_weekend,
    is_prebook,
    platform_order_time,
    order_push_time,
    dispatch_time,
    grab_time,
    fetch_time,
    arrive_time,
    estimate_arrived_time,
    estimate_meal_prepare_time,
    platform_order_ts,
    order_push_ts,
    dispatch_ts,
    grab_ts,
    fetch_ts,
    arrive_ts,
    estimate_arrived_ts,
    estimate_meal_prepare_ts,
    has_missing_dispatch_time,
    is_incomplete_accepted,
    has_event_order_error,
    has_dt_inconsistency,
    has_prebook_inconsistency,
    has_order_time_inconsistency
FROM stg.waybill_attempt;
