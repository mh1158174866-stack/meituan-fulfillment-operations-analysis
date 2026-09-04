CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS meta;

CREATE OR REPLACE TABLE raw.waybill AS
SELECT
    column00 AS source_row_index,
    * EXCLUDE (column00)
FROM read_csv(
    'data/raw/all_waybill_info_meituan_0322.csv',
    header = true,
    sample_size = -1,
    strict_mode = true
);

CREATE OR REPLACE TABLE raw.courier_wave AS
SELECT *
FROM read_csv(
    'data/raw/courier_wave_info_meituan.csv',
    header = true,
    sample_size = -1,
    strict_mode = true
);

CREATE OR REPLACE TABLE raw.dispatch_rider AS
SELECT
    column0 AS source_row_index,
    * EXCLUDE (column0)
FROM read_csv(
    'data/raw/dispatch_rider_meituan.csv',
    header = true,
    sample_size = -1,
    strict_mode = true
);

CREATE OR REPLACE TABLE raw.dispatch_waybill AS
SELECT
    column0 AS source_row_index,
    * EXCLUDE (column0)
FROM read_csv(
    'data/raw/dispatch_waybill_meituan.csv',
    header = true,
    sample_size = -1,
    strict_mode = true
);

CREATE OR REPLACE TABLE meta.build_contract AS
SELECT
    '1f9b4288cee5a78d1e5da007fc306bbaa662fc6d'::VARCHAR AS source_commit,
    'Asia/Shanghai'::VARCHAR AS timezone_name,
    'dt_is_operating_date'::VARCHAR AS date_rule,
    'zero_event_time_means_absent'::VARCHAR AS zero_time_rule,
    'preserve_and_flag_never_silent_fix'::VARCHAR AS quality_rule;
