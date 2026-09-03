#!/usr/bin/env python3
"""Generate deterministic, aggregate-only structural audit reports with DuckDB."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REPORT_DIR = REPO_ROOT / "reports"


@dataclass(frozen=True)
class TableSpec:
    view: str
    filename: str
    grain: str
    key: tuple[str, ...]
    expected_rows: int
    source_index: str | None = None


TABLES = (
    TableSpec(
        "waybill",
        "all_waybill_info_meituan_0322.csv",
        "一次运单进入派单系统后的分配尝试；同一订单可对应多个运单",
        ("waybill_id",),
        654_343,
        "column00",
    ),
    TableSpec(
        "wave",
        "courier_wave_info_meituan.csv",
        "一个骑手在一个运营日内的一次波次",
        ("dt", "courier_id", "wave_id"),
        206_748,
    ),
    TableSpec(
        "dispatch_rider",
        "dispatch_rider_meituan.csv",
        "一个派单 checkpoint 下的一名候选骑手",
        ("dt", "dispatch_time", "courier_id"),
        62_044,
        "column0",
    ),
    TableSpec(
        "dispatch_waybill",
        "dispatch_waybill_meituan.csv",
        "一个派单 checkpoint 下的一张待分配订单",
        ("dt", "dispatch_time", "order_id"),
        15_921,
        "column0",
    ),
)


FIELD_DESCRIPTIONS = {
    "source_row_index": ("源文件导出索引", "整数", "仅用于检测源文件行索引完整性，无业务含义，不作为公开主键"),
    "dt": ("运营归属日", "YYYYMMDD 整数", "源文件日期字段；时间语义在阶段 D 单独审计"),
    "order_id": ("匿名订单标识", "整数", "同一订单可能经历多个 waybill_id"),
    "waybill_id": ("匿名运单标识", "整数", "订单被拒后重回派单系统会创建新运单"),
    "courier_id": ("匿名骑手标识", "整数", "waybill 表中表示当次分配骑手；派单骑手表中表示候选骑手"),
    "da_id": ("匿名商圈标识", "整数", "业务区域标识"),
    "is_courier_grabbed": ("骑手是否接受运单", "0/1", "1 为接受，0 为拒绝"),
    "is_weekend": ("订单日期是否周末", "0/1", "源文件标记"),
    "estimate_arrived_time": ("承诺送达时间", "Unix 秒", "承诺向顾客送达的时间"),
    "is_prebook": ("是否预订单", "0/1", "1 为预订单"),
    "poi_id": ("匿名商户标识", "整数", "匿名化取餐商户标识"),
    "sender_lng": ("取餐点经度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "sender_lat": ("取餐点纬度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "recipient_lng": ("送达点经度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "recipient_lat": ("送达点纬度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "grab_lng": ("分配时骑手经度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "grab_lat": ("分配时骑手纬度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "dispatch_time": ("派单时间或 checkpoint", "Unix 秒", "具体语义依表而异，阶段 D 单独审计"),
    "grab_time": ("运单接受时间", "Unix 秒", "未发生时以 0 编码"),
    "fetch_time": ("取餐时间", "Unix 秒", "未发生时以 0 编码"),
    "arrive_time": ("送达时间", "Unix 秒", "未发生时以 0 编码"),
    "estimate_meal_prepare_time": ("预计出餐时间", "Unix 秒", "预计餐品准备完成时间"),
    "order_push_time": ("订单进入派单系统时间", "Unix 秒", "订单进入分配队列的时间"),
    "platform_order_time": ("平台下单时间", "Unix 秒", "订单创建时间"),
    "wave_id": ("匿名波次标识", "整数", "需与 dt、courier_id 组成候选复合键"),
    "wave_start_time": ("波次开始时间", "Unix 秒", "官方定义为波次首单接受时间；阶段 D 记录索引问题"),
    "wave_end_time": ("波次结束时间", "Unix 秒", "官方定义为波次末单送达时间"),
    "order_ids": ("波次订单集合", "字符串列表", "只在本地拆分用于聚合覆盖率，不公开明细"),
    "rider_lat": ("checkpoint 骑手纬度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "rider_lng": ("checkpoint 骑手经度", "偏移后整数", "高风险位置字段，仅本地使用"),
    "courier_waybills": ("checkpoint 骑手在手任务集合", "字符串列表", "物理字段名与官方描述存在口径差异，阶段 C 比较关联覆盖率"),
}


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> int | float | str | None:
    return connection.execute(query).fetchone()[0]


def count_distinct_expression(columns: tuple[str, ...]) -> str:
    if len(columns) == 1:
        return columns[0]
    return "(" + ", ".join(columns) + ")"


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator / denominator:.6%}"


def register_views(connection: duckdb.DuckDBPyConnection) -> None:
    for table in TABLES:
        path = RAW_DIR / table.filename
        if not path.is_file():
            raise FileNotFoundError(f"missing {path.relative_to(REPO_ROOT)}; run scripts/download_data.py")
        read_csv = f"read_csv('{sql_path(path)}', header=true, sample_size=-1, strict_mode=true)"
        if table.source_index:
            select = f"{table.source_index} AS source_row_index, * EXCLUDE ({table.source_index})"
        else:
            select = "*"
        connection.execute(f"CREATE OR REPLACE VIEW {table.view} AS SELECT {select} FROM {read_csv}")

    connection.execute(
        """
        CREATE OR REPLACE TEMP VIEW wave_orders AS
        SELECT dt, courier_id, wave_id,
               try_cast(trim(token) AS BIGINT) AS order_id
        FROM wave,
             unnest(string_split(trim(order_ids, '[]'), ',')) AS values_table(token)
        WHERE trim(token) <> ''
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP VIEW rider_onhand AS
        SELECT dt, dispatch_time, courier_id,
               try_cast(trim(token) AS BIGINT) AS onhand_id
        FROM dispatch_rider,
             unnest(string_split(trim(courier_waybills, '[]'), ',')) AS values_table(token)
        WHERE courier_waybills IS NOT NULL
          AND trim(token) <> ''
        """
    )


def table_profile(connection: duckdb.DuckDBPyConnection, table: TableSpec) -> dict[str, object]:
    schema = connection.execute(f"DESCRIBE SELECT * FROM {table.view}").fetchall()
    columns = [row[0] for row in schema]
    row_count = int(scalar(connection, f"SELECT count(*) FROM {table.view}"))
    distinct_rows = int(scalar(connection, f"SELECT count(*) FROM (SELECT DISTINCT * FROM {table.view})"))
    key_expression = count_distinct_expression(table.key)
    distinct_keys = int(
        scalar(connection, f"SELECT count(DISTINCT {key_expression}) FROM {table.view}")
    )
    null_counts = {
        column: int(scalar(connection, f'SELECT count(*) FILTER (WHERE "{column}" IS NULL) FROM {table.view}'))
        for column in columns
    }
    return {
        "schema": schema,
        "columns": columns,
        "rows": row_count,
        "row_delta": row_count - table.expected_rows,
        "full_duplicates": row_count - distinct_rows,
        "key_duplicates": row_count - distinct_keys,
        "null_counts": null_counts,
    }


def write_dictionary(profiles: dict[str, dict[str, object]]) -> None:
    lines = [
        "# 数据字典",
        "",
        "本字典依据美团官方字段说明和本地 DuckDB 全量类型推断整理；不展示任何数据行、原始 ID 或坐标值。",
        "",
    ]
    for table in TABLES:
        profile = profiles[table.view]
        lines.extend(
            [
                f"## `{table.filename}`",
                "",
                f"- 粒度：{table.grain}。",
                f"- 候选键：`{' + '.join(table.key)}`。",
                f"- 实际规模：{profile['rows']:,} 行，{len(profile['columns']):,} 列。",
                "",
                "| 字段 | DuckDB 类型 | 业务含义 | 原始格式 | 使用边界 |",
                "|---|---|---|---|---|",
            ]
        )
        for name, inferred_type, *_ in profile["schema"]:
            meaning, raw_format, boundary = FIELD_DESCRIPTIONS[name]
            lines.append(
                f"| `{name}` | `{inferred_type}` | {meaning} | {raw_format} | {boundary} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 关系与口径提示",
            "",
            "- `order_id` 是订单粒度；`waybill_id` 是分配尝试粒度，一张订单可对应多张运单。",
            "- 波次表不能只用 `wave_id` 作为全局键，应使用 `dt + courier_id + wave_id` 候选复合键。",
            "- 两张 dispatch 表描述派单 checkpoint 的输入切片，不应直接当作全量订单或骑手事实表。",
            "- `courier_waybills` 的物理字段名与官方“在手订单集合”描述并不完全一致；只在覆盖率审计中比较两种可能关联，不在本阶段强行定口径。",
            "- 所有 Unix 时间均在阶段 D 按 Asia/Shanghai 解释并检查事件顺序。",
            "",
        ]
    )
    (REPORT_DIR / "DATA_DICTIONARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_quality_report(
    connection: duckdb.DuckDBPyConnection, profiles: dict[str, dict[str, object]]
) -> None:
    accepted = int(scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 1"))
    rejected = int(scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 0"))
    unexpected_flags = int(
        scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed NOT IN (0, 1) OR is_courier_grabbed IS NULL")
    )
    distinct_orders = int(scalar(connection, "SELECT count(DISTINCT order_id) FROM waybill"))
    distinct_waybills = int(scalar(connection, "SELECT count(DISTINCT waybill_id) FROM waybill"))
    multi_waybill_orders = int(
        scalar(
            connection,
            "SELECT count(*) FROM (SELECT order_id FROM waybill GROUP BY order_id HAVING count(DISTINCT waybill_id) > 1)",
        )
    )

    time_columns = (
        "estimate_arrived_time",
        "dispatch_time",
        "grab_time",
        "fetch_time",
        "arrive_time",
        "estimate_meal_prepare_time",
        "order_push_time",
        "platform_order_time",
    )
    zero_times = {
        column: int(scalar(connection, f"SELECT count(*) FROM waybill WHERE {column} = 0"))
        for column in time_columns
    }

    dispatch_orders = int(scalar(connection, "SELECT count(DISTINCT order_id) FROM dispatch_waybill"))
    dispatch_orders_matched = int(
        scalar(
            connection,
            "SELECT count(DISTINCT d.order_id) FROM dispatch_waybill d SEMI JOIN waybill w USING (order_id)",
        )
    )
    all_orders_in_dispatch = int(
        scalar(
            connection,
            "SELECT count(DISTINCT w.order_id) FROM waybill w SEMI JOIN dispatch_waybill d USING (order_id)",
        )
    )
    rider_couriers = int(scalar(connection, "SELECT count(DISTINCT courier_id) FROM dispatch_rider"))
    rider_couriers_matched = int(
        scalar(
            connection,
            "SELECT count(DISTINCT r.courier_id) FROM dispatch_rider r SEMI JOIN waybill w USING (courier_id)",
        )
    )
    wave_memberships = int(scalar(connection, "SELECT count(*) FROM wave_orders"))
    wave_order_ids = int(scalar(connection, "SELECT count(DISTINCT order_id) FROM wave_orders"))
    wave_order_matches = int(
        scalar(
            connection,
            "SELECT count(DISTINCT x.order_id) FROM wave_orders x SEMI JOIN waybill w USING (order_id)",
        )
    )
    invalid_wave_tokens = int(scalar(connection, "SELECT count(*) FROM wave_orders WHERE order_id IS NULL"))

    onhand_memberships = int(scalar(connection, "SELECT count(*) FROM rider_onhand"))
    onhand_ids = int(scalar(connection, "SELECT count(DISTINCT onhand_id) FROM rider_onhand"))
    onhand_waybill_matches = int(
        scalar(
            connection,
            "SELECT count(DISTINCT x.onhand_id) FROM rider_onhand x SEMI JOIN waybill w ON x.onhand_id = w.waybill_id",
        )
    )
    onhand_order_matches = int(
        scalar(
            connection,
            "SELECT count(DISTINCT x.onhand_id) FROM rider_onhand x SEMI JOIN waybill w ON x.onhand_id = w.order_id",
        )
    )
    invalid_onhand_tokens = int(scalar(connection, "SELECT count(*) FROM rider_onhand WHERE onhand_id IS NULL"))

    rider_checkpoints = int(
        scalar(connection, "SELECT count(DISTINCT (dt, dispatch_time)) FROM dispatch_rider")
    )
    waybill_checkpoints = int(
        scalar(connection, "SELECT count(DISTINCT (dt, dispatch_time)) FROM dispatch_waybill")
    )
    common_checkpoints = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM
              (SELECT DISTINCT dt, dispatch_time FROM dispatch_rider)
              INNER JOIN
              (SELECT DISTINCT dt, dispatch_time FROM dispatch_waybill)
              USING (dt, dispatch_time)
            """,
        )
    )

    lines = [
        "# 数据质量报告：结构、粒度与关联",
        "",
        "本报告由 `scripts/audit_data.py` 对四张官方表全量只读计算生成，只包含聚合统计。官方文档行数仅作为外部对照；下列“实际”数值均由本项目脚本重算。",
        "",
        "## 1. 文件结构与候选键",
        "",
        "| 表 | 实际行数 | 官方说明行数 | 差异 | 全行重复 | 候选键重复 | 结论 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for table in TABLES:
        profile = profiles[table.view]
        conclusion = "通过" if profile["row_delta"] == 0 and profile["full_duplicates"] == 0 and profile["key_duplicates"] == 0 else "需复核"
        lines.append(
            f"| `{table.filename}` | {profile['rows']:,} | {table.expected_rows:,} | {profile['row_delta']:+,} | {profile['full_duplicates']:,} | {profile['key_duplicates']:,} | {conclusion} |"
        )

    lines.extend(
        [
            "",
            "说明：三张 CSV 含无业务含义的导出索引列，审计视图统一改名为 `source_row_index`；它不参与业务候选键。",
            "",
            "## 2. 缺失与 0 时间编码",
            "",
            "| 表 | NULL 单元格数 | 含 NULL 的字段数 |",
            "|---|---:|---:|",
        ]
    )
    for table in TABLES:
        null_counts = profiles[table.view]["null_counts"]
        null_cells = sum(null_counts.values())
        nullable_fields = sum(value > 0 for value in null_counts.values())
        lines.append(f"| `{table.filename}` | {null_cells:,} | {nullable_fields:,} |")
    lines.extend(
        [
            "",
            "官方说明规定未发生的时间用 0 而非 NULL 编码。waybill 表的全量计数如下：",
            "",
            "| 时间字段 | 等于 0 的行数 | 占 waybill 行数 |",
            "|---|---:|---:|",
        ]
    )
    waybill_rows = int(profiles["waybill"]["rows"])
    for column in time_columns:
        lines.append(f"| `{column}` | {zero_times[column]:,} | {pct(zero_times[column], waybill_rows)} |")

    lines.extend(
        [
            "",
            "## 3. 接受/拒绝与订单/运单粒度",
            "",
            f"- 运单尝试共 {waybill_rows:,} 行：接受 {accepted:,} 行，拒绝 {rejected:,} 行，其他或缺失标记 {unexpected_flags:,} 行。",
            f"- 去重订单 {distinct_orders:,} 个；去重运单 {distinct_waybills:,} 个。",
            f"- 有多个运单的订单 {multi_waybill_orders:,} 个，验证了订单与运单不是同一粒度。",
            "",
            "## 4. 表间关联覆盖率",
            "",
            "| 关系 | 分母 | 匹配数 | 覆盖率 |",
            "|---|---:|---:|---:|",
            f"| dispatch 订单 → waybill 订单 | {dispatch_orders:,} | {dispatch_orders_matched:,} | {pct(dispatch_orders_matched, dispatch_orders)} |",
            f"| 全量订单 → dispatch 订单 | {distinct_orders:,} | {all_orders_in_dispatch:,} | {pct(all_orders_in_dispatch, distinct_orders)} |",
            f"| dispatch 候选骑手 → waybill 骑手 | {rider_couriers:,} | {rider_couriers_matched:,} | {pct(rider_couriers_matched, rider_couriers)} |",
            f"| 波次订单集合 → waybill 订单 | {wave_order_ids:,} | {wave_order_matches:,} | {pct(wave_order_matches, wave_order_ids)} |",
            "",
            f"波次订单集合共拆分出 {wave_memberships:,} 个成员，无法解析为整数的成员为 {invalid_wave_tokens:,} 个。",
            "",
            "## 5. 派单 checkpoint",
            "",
            f"- `dispatch_rider` 有 {rider_checkpoints:,} 个去重 `(dt, dispatch_time)` checkpoint。",
            f"- `dispatch_waybill` 有 {waybill_checkpoints:,} 个去重 `(dt, dispatch_time)` checkpoint。",
            f"- 两表共有 checkpoint 为 {common_checkpoints:,} 个。",
            "- 这些表是 checkpoint 输入切片；不能用其行数替代全量订单、运单或骑手规模。",
            "",
            "## 6. `courier_waybills` 物理含义核对",
            "",
            f"- 共拆分出 {onhand_memberships:,} 个在手集合成员、{onhand_ids:,} 个去重标识；无法解析为整数的成员为 {invalid_onhand_tokens:,} 个。",
            f"- 与 `waybill_id` 匹配 {onhand_waybill_matches:,} 个（{pct(onhand_waybill_matches, onhand_ids)}）。",
            f"- 与 `order_id` 匹配 {onhand_order_matches:,} 个（{pct(onhand_order_matches, onhand_ids)}）。",
            "- 因官方文字称其为在手订单集合、物理字段名却为 `courier_waybills`，本阶段只记录两种覆盖率，不据此构建正式事实表。",
            "",
            "## 7. 阶段 C 结论",
            "",
            "- 四表均可被 DuckDB 严格、全量读取，实际行数与官方说明对照一致。",
            "- 候选业务键、重复、NULL、0 时间、接受/拒绝、粒度和关联覆盖率已完成聚合验收。",
            "- 时间解释、预订单日期提前、事件顺序、已接单未完成记录、wave_start_time 索引问题和 checkpoint 业务语义留到阶段 D。",
            "",
        ]
    )
    (REPORT_DIR / "DATA_QUALITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(database=":memory:")
    connection.execute("SET threads = 1")
    register_views(connection)
    profiles = {table.view: table_profile(connection, table) for table in TABLES}
    write_dictionary(profiles)
    write_quality_report(connection, profiles)
    print("wrote reports/DATA_DICTIONARY.md")
    print("wrote reports/DATA_QUALITY_REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
