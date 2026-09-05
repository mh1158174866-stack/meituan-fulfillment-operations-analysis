CREATE OR REPLACE TABLE fact.fact_courier_wave AS
WITH wave_rollup AS (
    SELECT
        m.dt,
        m.courier_id,
        m.wave_id,
        count(*) AS member_count,
        count(*) FILTER (WHERE NOT m.has_parse_error) AS parsed_member_count,
        count(o.order_id) AS matched_order_count,
        min(o.accepted_time) AS reconstructed_wave_start_time,
        max(o.arrive_time) AS reconstructed_wave_end_time
    FROM stg.wave_order_membership AS m
    LEFT JOIN fact.fact_order_fulfillment AS o
      ON m.order_id = o.order_id
     AND m.courier_id = o.accepted_courier_id
     AND m.dt = o.dt
    GROUP BY m.dt, m.courier_id, m.wave_id
)
SELECT
    w.dt,
    w.courier_id,
    w.wave_id,
    w.wave_start_time AS official_wave_start_time,
    r.reconstructed_wave_start_time,
    w.wave_end_time AS official_wave_end_time,
    r.reconstructed_wave_end_time,
    to_timestamp(w.wave_start_time) AS official_wave_start_ts,
    to_timestamp(r.reconstructed_wave_start_time) AS reconstructed_wave_start_ts,
    to_timestamp(w.wave_end_time) AS official_wave_end_ts,
    r.member_count,
    r.parsed_member_count,
    r.matched_order_count,
    w.wave_start_time - r.reconstructed_wave_start_time AS start_time_delta_seconds,
    (w.wave_start_time <> r.reconstructed_wave_start_time) AS has_start_time_mismatch,
    (w.wave_end_time <> r.reconstructed_wave_end_time) AS has_end_time_mismatch,
    (r.parsed_member_count <> r.member_count) AS has_member_parse_error,
    (r.matched_order_count <> r.member_count) AS has_member_coverage_error,
    CASE WHEN w.wave_end_time >= r.reconstructed_wave_start_time
        THEN w.wave_end_time - r.reconstructed_wave_start_time END AS wave_duration_seconds
FROM raw.courier_wave AS w
JOIN wave_rollup AS r USING (dt, courier_id, wave_id);

CREATE OR REPLACE TABLE fact.fact_dispatch_checkpoint_order AS
SELECT
    c.dt,
    c.dispatch_time,
    c.checkpoint_ts,
    c.order_id,
    (o.order_id IS NOT NULL) AS has_fulfillment_match
FROM stg.checkpoint_order AS c
LEFT JOIN fact.fact_order_fulfillment AS o
  ON c.order_id = o.order_id
 AND c.dt = o.dt;

CREATE OR REPLACE TABLE fact.fact_dispatch_checkpoint_rider AS
SELECT
    r.dt,
    r.dispatch_time,
    r.checkpoint_ts,
    r.courier_id,
    count(m.onhand_id) AS parsed_onhand_count,
    count(m.onhand_id) FILTER (WHERE w.waybill_id IS NOT NULL) AS onhand_waybill_match_count,
    count(m.onhand_id) FILTER (WHERE o.order_id IS NOT NULL) AS onhand_order_match_count,
    bool_or(coalesce(m.has_parse_error, false)) AS has_onhand_parse_error,
    true AS courier_waybills_definition_uncertain
FROM stg.checkpoint_rider AS r
LEFT JOIN stg.checkpoint_rider_onhand AS m
  USING (dt, dispatch_time, courier_id)
LEFT JOIN fact.fact_waybill_attempt AS w
  ON m.onhand_id = w.waybill_id
LEFT JOIN fact.fact_order_fulfillment AS o
  ON m.onhand_id = o.order_id
GROUP BY r.dt, r.dispatch_time, r.checkpoint_ts, r.courier_id;

CREATE OR REPLACE TABLE fact.fact_dispatch_checkpoint AS
WITH checkpoint_keys AS (
    SELECT dt, dispatch_time FROM stg.checkpoint_order
    UNION
    SELECT dt, dispatch_time FROM stg.checkpoint_rider
),
orders AS (
    SELECT
        dt,
        dispatch_time,
        count(*) AS pending_order_count,
        count(*) FILTER (WHERE has_fulfillment_match) AS matched_order_count
    FROM fact.fact_dispatch_checkpoint_order
    GROUP BY dt, dispatch_time
),
riders AS (
    SELECT
        dt,
        dispatch_time,
        count(*) AS candidate_courier_count,
        sum(parsed_onhand_count) AS parsed_onhand_count,
        bool_or(has_onhand_parse_error) AS has_onhand_parse_error
    FROM fact.fact_dispatch_checkpoint_rider
    GROUP BY dt, dispatch_time
)
SELECT
    k.dt,
    k.dispatch_time,
    to_timestamp(k.dispatch_time) AS checkpoint_ts,
    o.pending_order_count,
    r.candidate_courier_count,
    o.matched_order_count,
    r.parsed_onhand_count,
    o.pending_order_count::DOUBLE / nullif(r.candidate_courier_count, 0)
        AS pending_orders_per_candidate_courier,
    r.candidate_courier_count::DOUBLE / nullif(o.pending_order_count, 0)
        AS candidate_couriers_per_pending_order,
    (o.pending_order_count IS NULL) AS missing_order_snapshot,
    (r.candidate_courier_count IS NULL) AS missing_rider_snapshot,
    coalesce(r.has_onhand_parse_error, false) AS has_onhand_parse_error,
    true AS courier_waybills_definition_uncertain,
    true AS is_selected_checkpoint_not_event_log
FROM checkpoint_keys AS k
LEFT JOIN orders AS o USING (dt, dispatch_time)
LEFT JOIN riders AS r USING (dt, dispatch_time);
