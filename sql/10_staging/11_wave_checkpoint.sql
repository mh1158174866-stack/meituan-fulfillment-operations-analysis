CREATE OR REPLACE TABLE stg.wave_order_membership AS
SELECT
    w.dt,
    w.courier_id,
    w.wave_id,
    member_sequence,
    try_cast(trim(token) AS BIGINT) AS order_id,
    (try_cast(trim(token) AS BIGINT) IS NULL) AS has_parse_error
FROM raw.courier_wave AS w,
unnest(string_split(trim(w.order_ids, '[]'), ','))
    WITH ORDINALITY AS members(token, member_sequence)
WHERE trim(token) <> '';

CREATE OR REPLACE TABLE stg.checkpoint_order AS
SELECT
    dt,
    dispatch_time,
    to_timestamp(dispatch_time) AS checkpoint_ts,
    order_id
FROM raw.dispatch_waybill;

CREATE OR REPLACE TABLE stg.checkpoint_rider AS
SELECT
    dt,
    dispatch_time,
    to_timestamp(dispatch_time) AS checkpoint_ts,
    courier_id,
    courier_waybills,
    true AS courier_waybills_definition_uncertain
FROM raw.dispatch_rider;

CREATE OR REPLACE TABLE stg.checkpoint_rider_onhand AS
SELECT
    r.dt,
    r.dispatch_time,
    r.courier_id,
    member_sequence,
    try_cast(trim(token) AS BIGINT) AS onhand_id,
    (try_cast(trim(token) AS BIGINT) IS NULL) AS has_parse_error,
    true AS courier_waybills_definition_uncertain
FROM raw.dispatch_rider AS r,
unnest(string_split(trim(r.courier_waybills, '[]'), ','))
    WITH ORDINALITY AS members(token, member_sequence)
WHERE r.courier_waybills IS NOT NULL
  AND trim(token) <> '';
