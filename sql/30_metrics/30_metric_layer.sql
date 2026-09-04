CREATE SCHEMA IF NOT EXISTS metrics;

CREATE OR REPLACE TABLE metrics.daily_fulfillment AS
WITH order_daily AS (
    SELECT
        dt,
        count(*) AS order_count,
        count(*) FILTER (WHERE is_completed) AS completed_order_count,
        count(*) FILTER (WHERE attempt_count = 1) AS first_attempt_success_order_count,
        sum(attempt_count) AS attempt_count_sum,
        sum(redispatch_count) AS redispatch_count_sum,
        count(*) FILTER (WHERE is_completed AND arrive_time > estimate_arrived_time)
            AS strict_late_order_count,
        count(*) FILTER (
            WHERE is_completed AND arrive_time > estimate_arrived_time + 8 * 60
        ) AS buffer_8m_late_order_count,
        sum(order_to_push_seconds) AS order_to_push_seconds_sum,
        count(order_to_push_seconds) AS order_to_push_eligible_count,
        sum(push_to_first_dispatch_seconds) AS push_to_first_dispatch_seconds_sum,
        count(push_to_first_dispatch_seconds) AS push_to_first_dispatch_eligible_count,
        sum(first_dispatch_to_accept_seconds) AS first_dispatch_to_accept_seconds_sum,
        count(first_dispatch_to_accept_seconds) AS first_dispatch_to_accept_eligible_count,
        sum(final_dispatch_to_accept_seconds) AS final_dispatch_to_accept_seconds_sum,
        count(final_dispatch_to_accept_seconds) AS final_dispatch_to_accept_eligible_count,
        sum(accept_to_fetch_seconds) AS accept_to_fetch_seconds_sum,
        count(accept_to_fetch_seconds) AS accept_to_fetch_eligible_count,
        sum(fetch_to_arrive_seconds) AS fetch_to_arrive_seconds_sum,
        count(fetch_to_arrive_seconds) AS fetch_to_arrive_eligible_count,
        sum(end_to_end_seconds) AS end_to_end_seconds_sum,
        count(end_to_end_seconds) AS end_to_end_eligible_count,
        sum(pickup_delay_seconds) FILTER (WHERE estimate_meal_prepare_time > 0)
            AS pickup_delay_seconds_sum,
        count(pickup_delay_seconds) FILTER (WHERE estimate_meal_prepare_time > 0)
            AS pickup_delay_eligible_count,
        sum(delivery_distance_coordinate_units) AS delivery_distance_sum,
        count(delivery_distance_coordinate_units) AS delivery_distance_eligible_count
    FROM fact.fact_order_fulfillment
    WHERE NOT has_event_order_error
    GROUP BY dt
),
waybill_daily AS (
    SELECT
        dt,
        count(*) AS waybill_attempt_count,
        count(*) FILTER (WHERE is_courier_grabbed = 1) AS accepted_waybill_count
    FROM fact.fact_waybill_attempt
    WHERE NOT has_event_order_error
    GROUP BY dt
),
wave_daily AS (
    SELECT
        dt,
        count(*) AS wave_count,
        sum(wave_duration_seconds) AS wave_duration_seconds_sum,
        count(wave_duration_seconds) AS wave_duration_eligible_count,
        sum(member_count) AS wave_member_count_sum,
        quantile_cont(member_count, 0.9) AS p90_wave_load_orders
    FROM fact.fact_courier_wave
    WHERE NOT has_member_parse_error
      AND NOT has_member_coverage_error
      AND wave_duration_seconds IS NOT NULL
    GROUP BY dt
)
SELECT
    o.*,
    w.waybill_attempt_count,
    w.accepted_waybill_count,
    v.wave_count,
    v.wave_duration_seconds_sum,
    v.wave_duration_eligible_count,
    v.wave_member_count_sum,
    v.p90_wave_load_orders,
    w.accepted_waybill_count::DOUBLE / nullif(w.waybill_attempt_count, 0)
        AS waybill_acceptance_rate,
    o.first_attempt_success_order_count::DOUBLE / nullif(o.order_count, 0)
        AS first_attempt_success_rate,
    o.first_attempt_success_order_count::DOUBLE / nullif(o.order_count, 0)
        AS first_dispatch_success_rate,
    o.attempt_count_sum::DOUBLE / nullif(o.order_count, 0) AS avg_attempt_count,
    o.redispatch_count_sum::DOUBLE / nullif(o.order_count, 0) AS avg_redispatch_count,
    o.completed_order_count::DOUBLE / nullif(o.order_count, 0) AS completion_rate,
    o.order_to_push_seconds_sum::DOUBLE / nullif(o.order_to_push_eligible_count, 0)
        AS avg_order_to_push_seconds,
    o.push_to_first_dispatch_seconds_sum::DOUBLE
        / nullif(o.push_to_first_dispatch_eligible_count, 0)
        AS avg_push_to_first_dispatch_seconds,
    o.first_dispatch_to_accept_seconds_sum::DOUBLE
        / nullif(o.first_dispatch_to_accept_eligible_count, 0)
        AS avg_first_dispatch_to_accept_seconds,
    o.final_dispatch_to_accept_seconds_sum::DOUBLE
        / nullif(o.final_dispatch_to_accept_eligible_count, 0)
        AS avg_final_dispatch_to_accept_seconds,
    o.accept_to_fetch_seconds_sum::DOUBLE / nullif(o.accept_to_fetch_eligible_count, 0)
        AS avg_accept_to_fetch_seconds,
    o.fetch_to_arrive_seconds_sum::DOUBLE / nullif(o.fetch_to_arrive_eligible_count, 0)
        AS avg_fetch_to_arrive_seconds,
    o.end_to_end_seconds_sum::DOUBLE / nullif(o.end_to_end_eligible_count, 0)
        AS avg_end_to_end_seconds,
    o.strict_late_order_count::DOUBLE / nullif(o.completed_order_count, 0)
        AS strict_late_rate,
    o.buffer_8m_late_order_count::DOUBLE / nullif(o.completed_order_count, 0)
        AS buffer_8m_late_rate,
    o.pickup_delay_seconds_sum::DOUBLE / nullif(o.pickup_delay_eligible_count, 0)
        AS avg_pickup_delay_seconds,
    o.delivery_distance_sum::DOUBLE / nullif(o.delivery_distance_eligible_count, 0)
        AS avg_delivery_distance_coordinate_units,
    v.wave_duration_seconds_sum::DOUBLE / nullif(v.wave_duration_eligible_count, 0)
        AS avg_wave_duration_seconds,
    v.wave_member_count_sum::DOUBLE / nullif(v.wave_count, 0) AS avg_orders_per_wave
FROM order_daily AS o
JOIN waybill_daily AS w USING (dt)
JOIN wave_daily AS v USING (dt)
ORDER BY o.dt;

CREATE OR REPLACE TABLE metrics.overall_fulfillment AS
WITH totals AS (
    SELECT
        sum(order_count) AS order_count,
        sum(completed_order_count) AS completed_order_count,
        sum(first_attempt_success_order_count) AS first_attempt_success_order_count,
        sum(attempt_count_sum) AS attempt_count_sum,
        sum(redispatch_count_sum) AS redispatch_count_sum,
        sum(strict_late_order_count) AS strict_late_order_count,
        sum(buffer_8m_late_order_count) AS buffer_8m_late_order_count,
        sum(order_to_push_seconds_sum) AS order_to_push_seconds_sum,
        sum(order_to_push_eligible_count) AS order_to_push_eligible_count,
        sum(push_to_first_dispatch_seconds_sum) AS push_to_first_dispatch_seconds_sum,
        sum(push_to_first_dispatch_eligible_count) AS push_to_first_dispatch_eligible_count,
        sum(first_dispatch_to_accept_seconds_sum) AS first_dispatch_to_accept_seconds_sum,
        sum(first_dispatch_to_accept_eligible_count) AS first_dispatch_to_accept_eligible_count,
        sum(final_dispatch_to_accept_seconds_sum) AS final_dispatch_to_accept_seconds_sum,
        sum(final_dispatch_to_accept_eligible_count) AS final_dispatch_to_accept_eligible_count,
        sum(accept_to_fetch_seconds_sum) AS accept_to_fetch_seconds_sum,
        sum(accept_to_fetch_eligible_count) AS accept_to_fetch_eligible_count,
        sum(fetch_to_arrive_seconds_sum) AS fetch_to_arrive_seconds_sum,
        sum(fetch_to_arrive_eligible_count) AS fetch_to_arrive_eligible_count,
        sum(end_to_end_seconds_sum) AS end_to_end_seconds_sum,
        sum(end_to_end_eligible_count) AS end_to_end_eligible_count,
        sum(pickup_delay_seconds_sum) AS pickup_delay_seconds_sum,
        sum(pickup_delay_eligible_count) AS pickup_delay_eligible_count,
        sum(delivery_distance_sum) AS delivery_distance_sum,
        sum(delivery_distance_eligible_count) AS delivery_distance_eligible_count,
        sum(waybill_attempt_count) AS waybill_attempt_count,
        sum(accepted_waybill_count) AS accepted_waybill_count,
        sum(wave_count) AS wave_count,
        sum(wave_duration_seconds_sum) AS wave_duration_seconds_sum,
        sum(wave_duration_eligible_count) AS wave_duration_eligible_count,
        sum(wave_member_count_sum) AS wave_member_count_sum
    FROM metrics.daily_fulfillment
)
SELECT
    *,
    accepted_waybill_count::DOUBLE / waybill_attempt_count AS waybill_acceptance_rate,
    first_attempt_success_order_count::DOUBLE / order_count AS first_attempt_success_rate,
    first_attempt_success_order_count::DOUBLE / order_count AS first_dispatch_success_rate,
    attempt_count_sum::DOUBLE / order_count AS avg_attempt_count,
    redispatch_count_sum::DOUBLE / order_count AS avg_redispatch_count,
    completed_order_count::DOUBLE / order_count AS completion_rate,
    order_to_push_seconds_sum::DOUBLE / order_to_push_eligible_count AS avg_order_to_push_seconds,
    push_to_first_dispatch_seconds_sum::DOUBLE / push_to_first_dispatch_eligible_count
        AS avg_push_to_first_dispatch_seconds,
    first_dispatch_to_accept_seconds_sum::DOUBLE / first_dispatch_to_accept_eligible_count
        AS avg_first_dispatch_to_accept_seconds,
    final_dispatch_to_accept_seconds_sum::DOUBLE / final_dispatch_to_accept_eligible_count
        AS avg_final_dispatch_to_accept_seconds,
    accept_to_fetch_seconds_sum::DOUBLE / accept_to_fetch_eligible_count
        AS avg_accept_to_fetch_seconds,
    fetch_to_arrive_seconds_sum::DOUBLE / fetch_to_arrive_eligible_count
        AS avg_fetch_to_arrive_seconds,
    end_to_end_seconds_sum::DOUBLE / end_to_end_eligible_count AS avg_end_to_end_seconds,
    strict_late_order_count::DOUBLE / completed_order_count AS strict_late_rate,
    buffer_8m_late_order_count::DOUBLE / completed_order_count AS buffer_8m_late_rate,
    pickup_delay_seconds_sum::DOUBLE / pickup_delay_eligible_count AS avg_pickup_delay_seconds,
    delivery_distance_sum::DOUBLE / delivery_distance_eligible_count
        AS avg_delivery_distance_coordinate_units,
    wave_duration_seconds_sum::DOUBLE / wave_duration_eligible_count AS avg_wave_duration_seconds,
    wave_member_count_sum::DOUBLE / wave_count AS avg_orders_per_wave
FROM totals;

CREATE OR REPLACE TABLE metrics.checkpoint_snapshot AS
SELECT
    dt,
    dispatch_time,
    checkpoint_ts,
    pending_order_count,
    candidate_courier_count,
    pending_orders_per_candidate_courier,
    candidate_couriers_per_pending_order,
    missing_order_snapshot,
    missing_rider_snapshot,
    courier_waybills_definition_uncertain,
    is_selected_checkpoint_not_event_log
FROM fact.fact_dispatch_checkpoint
ORDER BY dt, dispatch_time;
