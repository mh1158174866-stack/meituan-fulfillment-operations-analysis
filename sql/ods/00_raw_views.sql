-- ODS 只读映射：不改写官方 CSV，不持久化到分析库。
CREATE OR REPLACE TEMP VIEW ods_waybill AS
SELECT * EXCLUDE (column00)
FROM read_csv_auto(
    '{{RAW_DIR}}/all_waybill_info_meituan_0322.csv',
    header = true,
    sample_size = -1
);

CREATE OR REPLACE TEMP VIEW ods_courier_wave AS
SELECT *
FROM read_csv_auto(
    '{{RAW_DIR}}/courier_wave_info_meituan.csv',
    header = true,
    sample_size = -1
);
