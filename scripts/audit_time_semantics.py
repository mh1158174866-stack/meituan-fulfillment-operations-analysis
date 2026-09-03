#!/usr/bin/env python3
"""Audit date attribution, event order, wave times, and dispatch checkpoints."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REPORT_PATH = REPO_ROOT / "reports" / "TIME_SEMANTICS_REPORT.md"


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> int | str:
    return connection.execute(query).fetchone()[0]


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{numerator / denominator:.6%}"


def register_views(connection: duckdb.DuckDBPyConnection) -> None:
    files = {
        "waybill": "all_waybill_info_meituan_0322.csv",
        "wave": "courier_wave_info_meituan.csv",
        "dispatch_rider": "dispatch_rider_meituan.csv",
        "dispatch_waybill": "dispatch_waybill_meituan.csv",
    }
    for view, filename in files.items():
        path = RAW_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing {path.relative_to(REPO_ROOT)}; run scripts/download_data.py")
        connection.execute(
            f"CREATE OR REPLACE VIEW {view} AS "
            f"SELECT * FROM read_csv('{sql_path(path)}', header=true, sample_size=-1, strict_mode=true)"
        )
    connection.execute(
        """
        CREATE OR REPLACE TEMP VIEW orders AS
        SELECT order_id, dt, is_prebook, platform_order_time, order_push_time
        FROM waybill
        WHERE is_courier_grabbed = 1
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP VIEW order_versions AS
        SELECT order_id,
               count(DISTINCT dt) AS dt_versions,
               count(DISTINCT is_prebook) AS prebook_versions,
               count(DISTINCT platform_order_time) AS order_time_versions
        FROM waybill
        GROUP BY order_id
        """
    )
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
        CREATE OR REPLACE TEMP VIEW wave_first_orders AS
        SELECT dt, courier_id, wave_id,
               try_cast(trim(list_extract(string_split(trim(order_ids, '[]'), ','), 1)) AS BIGINT)
                   AS first_listed_order_id
        FROM wave
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP VIEW reconstructed_wave_times AS
        SELECT x.dt, x.courier_id, x.wave_id,
               min(w.grab_time) AS reconstructed_start_time,
               min(w.dispatch_time) AS reconstructed_dispatch_time,
               max(w.arrive_time) AS reconstructed_end_time
        FROM wave_orders x
        JOIN waybill w
          ON x.order_id = w.order_id
         AND x.courier_id = w.courier_id
         AND w.is_courier_grabbed = 1
        GROUP BY x.dt, x.courier_id, x.wave_id
        """
    )


def main() -> int:
    connection = duckdb.connect(database=":memory:")
    connection.execute("SET threads = 1")
    connection.execute("SET TimeZone = 'Asia/Shanghai'")
    register_views(connection)

    dt_min, dt_max, order_date_min, order_date_max = connection.execute(
        """
        SELECT min(strptime(dt::VARCHAR, '%Y%m%d')::DATE),
               max(strptime(dt::VARCHAR, '%Y%m%d')::DATE),
               min(CAST(to_timestamp(platform_order_time) AS DATE)),
               max(CAST(to_timestamp(platform_order_time) AS DATE))
        FROM waybill
        """
    ).fetchone()
    invariant_violations = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM order_versions
            WHERE dt_versions <> 1 OR prebook_versions <> 1 OR order_time_versions <> 1
            """,
        )
    )
    offsets = connection.execute(
        """
        SELECT is_prebook,
               date_diff(
                   'day',
                   CAST(to_timestamp(platform_order_time) AS DATE),
                   strptime(dt::VARCHAR, '%Y%m%d')::DATE
               ) AS day_offset,
               count(*) AS orders
        FROM orders
        GROUP BY is_prebook, day_offset
        ORDER BY is_prebook, day_offset
        """
    ).fetchall()
    prebook_total = int(scalar(connection, "SELECT count(*) FROM orders WHERE is_prebook = 1"))
    regular_total = int(scalar(connection, "SELECT count(*) FROM orders WHERE is_prebook = 0"))
    prebook_early = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM orders
            WHERE is_prebook = 1
              AND CAST(to_timestamp(platform_order_time) AS DATE)
                  < strptime(dt::VARCHAR, '%Y%m%d')::DATE
            """,
        )
    )
    regular_early = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM orders
            WHERE is_prebook = 0
              AND CAST(to_timestamp(platform_order_time) AS DATE)
                  < strptime(dt::VARCHAR, '%Y%m%d')::DATE
            """,
        )
    )

    event_checks = connection.execute(
        """
        SELECT
          count(*) FILTER (WHERE platform_order_time > order_push_time),
          count(*) FILTER (WHERE dispatch_time > 0 AND order_push_time > dispatch_time),
          count(*) FILTER (
              WHERE is_courier_grabbed = 1 AND dispatch_time > 0 AND grab_time > 0
                AND dispatch_time > grab_time
          ),
          count(*) FILTER (
              WHERE is_courier_grabbed = 1 AND grab_time > 0 AND fetch_time > 0
                AND grab_time > fetch_time
          ),
          count(*) FILTER (
              WHERE is_courier_grabbed = 1 AND fetch_time > 0 AND arrive_time > 0
                AND fetch_time > arrive_time
          ),
          count(*) FILTER (
              WHERE platform_order_time > order_push_time
                 OR (dispatch_time > 0 AND order_push_time > dispatch_time)
                 OR (is_courier_grabbed = 1 AND dispatch_time > 0 AND grab_time > 0 AND dispatch_time > grab_time)
                 OR (is_courier_grabbed = 1 AND grab_time > 0 AND fetch_time > 0 AND grab_time > fetch_time)
                 OR (is_courier_grabbed = 1 AND fetch_time > 0 AND arrive_time > 0 AND fetch_time > arrive_time)
          )
        FROM waybill
        """
    ).fetchone()
    accepted_rows = int(scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 1"))
    rejected_rows = int(scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 0"))
    accepted_incomplete = int(
        scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 1 AND arrive_time = 0")
    )
    accepted_zero_grab = int(
        scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 1 AND grab_time = 0")
    )
    accepted_zero_fetch = int(
        scalar(connection, "SELECT count(*) FROM waybill WHERE is_courier_grabbed = 1 AND fetch_time = 0")
    )
    rejected_nonzero_events = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM waybill
            WHERE is_courier_grabbed = 0
              AND (grab_time <> 0 OR fetch_time <> 0 OR arrive_time <> 0)
            """,
        )
    )
    zero_dispatch_by_flag = connection.execute(
        "SELECT is_courier_grabbed, count(*) FROM waybill WHERE dispatch_time = 0 GROUP BY 1 ORDER BY 1"
    ).fetchall()

    wave_rows = int(scalar(connection, "SELECT count(*) FROM wave"))
    wave_start_min, wave_start_max, wave_start_unique, plausible_wave_starts = connection.execute(
        """
        SELECT min(wave_start_time), max(wave_start_time), count(DISTINCT wave_start_time),
               count(*) FILTER (WHERE wave_start_time BETWEEN 1000000000 AND 2000000000)
        FROM wave
        """
    ).fetchone()
    sequential_wave_index = int(
        scalar(
            connection,
            f"SELECT count(*) FROM wave WHERE wave_start_time BETWEEN 0 AND {wave_rows - 1}",
        )
    )
    reconstructed_waves = int(scalar(connection, "SELECT count(*) FROM reconstructed_wave_times"))
    wave_start_matches = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM wave w
            JOIN reconstructed_wave_times r USING (dt, courier_id, wave_id)
            WHERE w.wave_start_time = r.reconstructed_start_time
            """,
        )
    )
    wave_start_mismatches = reconstructed_waves - wave_start_matches
    wave_start_delta = connection.execute(
        """
        SELECT
          count(*) FILTER (WHERE w.wave_start_time < r.reconstructed_start_time),
          count(*) FILTER (WHERE w.wave_start_time > r.reconstructed_start_time),
          min(w.wave_start_time - r.reconstructed_start_time),
          max(w.wave_start_time - r.reconstructed_start_time)
        FROM wave w
        JOIN reconstructed_wave_times r USING (dt, courier_id, wave_id)
        """
    ).fetchone()
    wave_start_dispatch_matches = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM wave w
            JOIN reconstructed_wave_times r USING (dt, courier_id, wave_id)
            WHERE w.wave_start_time = r.reconstructed_dispatch_time
            """,
        )
    )
    wave_start_first_listed_matches = int(
        scalar(
            connection,
            """
            SELECT count(*)
            FROM wave w
            JOIN wave_first_orders f USING (dt, courier_id, wave_id)
            JOIN waybill b
              ON f.first_listed_order_id = b.order_id
             AND f.courier_id = b.courier_id
             AND b.is_courier_grabbed = 1
            WHERE w.wave_start_time = b.grab_time
            """,
        )
    )
    wave_start_any_member_matches = int(
        scalar(
            connection,
            """
            SELECT count(DISTINCT (w.dt, w.courier_id, w.wave_id))
            FROM wave w
            JOIN wave_orders x USING (dt, courier_id, wave_id)
            JOIN waybill b
              ON x.order_id = b.order_id
             AND x.courier_id = b.courier_id
             AND b.is_courier_grabbed = 1
            WHERE w.wave_start_time = b.grab_time
            """,
        )
    )
    wave_end_matches = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM wave w
            JOIN reconstructed_wave_times r USING (dt, courier_id, wave_id)
            WHERE w.wave_end_time = r.reconstructed_end_time
            """,
        )
    )
    plausible_wave_ends = int(
        scalar(connection, "SELECT count(*) FROM wave WHERE wave_end_time BETWEEN 1000000000 AND 2000000000")
    )

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
            SELECT count(*)
            FROM (SELECT DISTINCT dt, dispatch_time FROM dispatch_rider)
            JOIN (SELECT DISTINCT dt, dispatch_time FROM dispatch_waybill)
            USING (dt, dispatch_time)
            """,
        )
    )
    checkpoint_dates = int(
        scalar(connection, "SELECT count(DISTINCT dt) FROM dispatch_waybill")
    )
    checkpoint_local_min, checkpoint_local_max = connection.execute(
        """
        SELECT min(to_timestamp(dispatch_time)), max(to_timestamp(dispatch_time))
        FROM dispatch_waybill
        """
    ).fetchone()
    order_checkpoint_min, order_checkpoint_max = connection.execute(
        """
        SELECT min(rows_per_checkpoint), max(rows_per_checkpoint)
        FROM (
          SELECT dt, dispatch_time, count(*) AS rows_per_checkpoint
          FROM dispatch_waybill GROUP BY dt, dispatch_time
        )
        """
    ).fetchone()
    rider_checkpoint_min, rider_checkpoint_max = connection.execute(
        """
        SELECT min(rows_per_checkpoint), max(rows_per_checkpoint)
        FROM (
          SELECT dt, dispatch_time, count(*) AS rows_per_checkpoint
          FROM dispatch_rider GROUP BY dt, dispatch_time
        )
        """
    ).fetchone()
    dispatch_orders = int(scalar(connection, "SELECT count(*) FROM dispatch_waybill"))
    accepted_dispatch_equal = int(
        scalar(
            connection,
            """
            SELECT count(*) FROM dispatch_waybill d
            JOIN waybill w USING (order_id)
            WHERE w.is_courier_grabbed = 1
              AND d.dispatch_time = w.dispatch_time
            """,
        )
    )

    lines = [
        "# 时间与业务语义审计",
        "",
        "本报告由 `scripts/audit_time_semantics.py` 全量只读生成。Unix 秒统一在 DuckDB 会话中按 `Asia/Shanghai` 解释；不展示单条记录、原始 ID、坐标或行为序列。",
        "",
        "## 1. `dt` 是运营归属日",
        "",
        f"- `dt` 覆盖 {dt_min} 至 {dt_max}；按 Asia/Shanghai 解释的平台下单本地日覆盖 {order_date_min} 至 {order_date_max}。",
        f"- 同一订单跨多个 waybill 时，`dt`、`is_prebook`、`platform_order_time` 不一致的订单为 {invariant_violations:,} 个。",
        "- 因预订单可提前下单，`dt` 不应机械地替换为 `platform_order_time` 的自然日；后续经营统计应以 `dt` 作为运营归属日。",
        "",
        "### 订单级日期偏移",
        "",
        "`日期偏移 = dt - 平台下单本地日`，正值表示在运营归属日前提前下单。",
        "",
        "| 是否预订单 | 日期偏移（天） | 订单数 |",
        "|---:|---:|---:|",
    ]
    for is_prebook, day_offset, count in offsets:
        lines.append(f"| {is_prebook} | {day_offset:+d} | {count:,} |")
    lines.extend(
        [
            "",
            f"预订单 {prebook_total:,} 个，其中提前下单 {prebook_early:,} 个（{pct(prebook_early, prebook_total)}）；非预订单 {regular_total:,} 个，其中跨自然日提前下单 {regular_early:,} 个（{pct(regular_early, regular_total)}）。",
            "",
            "## 2. 事件顺序与 0 时间",
            "",
            "相邻事件仅在对应时间非 0 时比较；已接单未完成单独列示，不混入顺序倒置。",
            "",
            "| 检查 | 异常行数 |",
            "|---|---:|",
            f"| 平台下单时间 > 进入派单系统时间 | {event_checks[0]:,} |",
            f"| 进入派单系统时间 > 非 0 派单时间 | {event_checks[1]:,} |",
            f"| 已接单：派单时间 > 接受时间 | {event_checks[2]:,} |",
            f"| 已接单：接受时间 > 取餐时间 | {event_checks[3]:,} |",
            f"| 已接单且已完成：取餐时间 > 送达时间 | {event_checks[4]:,} |",
            f"| 任一上述顺序倒置 | {event_checks[5]:,} |",
            "",
            f"- 已接单 {accepted_rows:,} 行中，`grab_time=0` 为 {accepted_zero_grab:,} 行，`fetch_time=0` 为 {accepted_zero_fetch:,} 行，`arrive_time=0` 为 {accepted_incomplete:,} 行。",
            f"- 因而确认存在 {accepted_incomplete:,} 条已接单未完成记录；本阶段仅记录质量事实，不删除、不填补。",
            f"- 已拒绝 {rejected_rows:,} 行中，接受/取餐/送达任一时间非 0 的记录为 {rejected_nonzero_events:,} 行。",
            "- `dispatch_time=0` 按接受标记的聚合分布："
            + "；".join(f"标记 {flag} 为 {count:,} 行" for flag, count in zero_dispatch_by_flag)
            + "。",
            "",
            "## 3. `wave_start_time` 索引问题",
            "",
            f"- wave 表共 {wave_rows:,} 行；`wave_start_time` 最小值 {wave_start_min:,}、最大值 {wave_start_max:,}、去重值 {wave_start_unique:,} 个。",
            f"- 其中落在 0 至 {wave_rows - 1:,} 的值有 {sequential_wave_index:,} 行，落在常见 Unix 秒范围的值有 {plausible_wave_starts:,} 行，因此它不是行号型索引。",
            f"- 通过波次订单集合连接已接受 waybill，可重构 {reconstructed_waves:,} 个波次的最早接受时间；原 `wave_start_time` 与重构值相等 {wave_start_matches:,} 行，不相等 {wave_start_mismatches:,} 行。",
            f"- 在不相等及全部波次中，原值早于最早接受时间 {wave_start_delta[0]:,} 行、晚于最早接受时间 {wave_start_delta[1]:,} 行；差值范围为 {wave_start_delta[2]:,} 至 {wave_start_delta[3]:,} 秒。",
            f"- 原值与波次最早派单时间相等 {wave_start_dispatch_matches:,} 行，与 `order_ids` 首个列表成员的接受时间相等 {wave_start_first_listed_matches:,} 行，与波次内任一成员接受时间相等 {wave_start_any_member_matches:,} 行。",
            f"- `wave_end_time` 落在常见 Unix 秒范围的有 {plausible_wave_ends:,} 行，与波次内最大送达时间相等 {wave_end_matches:,} 行。",
            "- 结论：`wave_start_time` 是合法 Unix 秒，但与官方“波次首单接受时间”定义存在索引/对齐问题，不能直接用于持续时长。若第二阶段需要波次开始时间，应以波次成员中已接受订单的最早 `grab_time` 重构并保留审计来源。",
            "",
            "## 4. `dispatch_time` 是 checkpoint 语义",
            "",
            f"- 两张 dispatch 表各包含 {rider_checkpoints:,} 和 {waybill_checkpoints:,} 个 `(dt, dispatch_time)` checkpoint，共有 checkpoint 为 {common_checkpoints:,} 个，覆盖 {checkpoint_dates:,} 个 `dt`。",
            f"- 按 Asia/Shanghai 解释，checkpoint 时间范围为 {checkpoint_local_min} 至 {checkpoint_local_max}。",
            f"- 每个 checkpoint 的待分配订单行数范围为 {order_checkpoint_min:,}–{order_checkpoint_max:,}；候选骑手行数范围为 {rider_checkpoint_min:,}–{rider_checkpoint_max:,}。",
            f"- dispatch_waybill 共 {dispatch_orders:,} 行，其中 checkpoint 时间与该订单最终已接受 waybill 的 `dispatch_time` 相等 {accepted_dispatch_equal:,} 行（{pct(accepted_dispatch_equal, dispatch_orders)}）。",
            "- 两张 dispatch 表是 24 个选定派单时点的输入快照，用于还原当时订单集合和候选骑手集合；不是覆盖全周期的逐事件派单日志。",
            "",
            "## 5. 阶段 D 结论",
            "",
            "- 后续按 `dt` 归属运营日，Unix 秒按 Asia/Shanghai 转换。",
            "- 预订单提前下单和跨自然日现象已在订单粒度量化，不应被误判为日期脏数据。",
            "- 顺序异常与已接单未完成记录已单独量化，原始记录不做静默修正。",
            "- `wave_start_time` 和 dispatch checkpoint 的语义限制已明确；本阶段不构建正式事实表。",
            "",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
