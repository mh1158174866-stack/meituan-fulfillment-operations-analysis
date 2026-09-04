#!/usr/bin/env python3
"""Build phase two in dependency order and emit aggregate-only acceptance reports."""

from __future__ import annotations

import argparse
import sys

from phase2_common import (
    DATABASE_PATH,
    REPORT_DIR,
    SOURCE_EXPECTATIONS,
    assert_source_contract,
    assert_step_b_contract,
    assert_step_c_contract,
    assert_step_d_contract,
    connect,
    execute_sql_file,
)


def write_step_a_report(passed: list[str]) -> None:
    lines = [
        "# 第二阶段 A：数据层设计与质量合同验收",
        "",
        "状态：**通过**。本报告只含 schema 约定、输入规模和测试结果，不含原始标识符、坐标或明细记录。",
        "",
        "## 固定合同",
        "",
        "- 官方数据提交：`1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`。",
        "- 运营归属日：`dt`；Unix 秒统一解释为 `Asia/Shanghai`。",
        "- 事件时间为 0 表示事件不存在；预订单允许跨自然日。",
        "- 质量问题一律保留原值并增加标记，不静默删除、填补或修正。",
        "- 本地数据库：`data/local/phase2.duckdb`，位于 Git 忽略目录。",
        "",
        "## 原始层守恒",
        "",
        "| 本地表 | 行数 |",
        "|---|---:|",
    ]
    for table, rows in SOURCE_EXPECTATIONS.items():
        lines.append(f"| `{table}` | {rows:,} |")
    lines.extend(
        [
            "",
            "## 自动检查",
            "",
            f"共 {len(passed)} 项合同检查通过：" + "、".join(f"`{name}`" for name in passed) + "。",
            "",
            "## 后续边界",
            "",
            "A 仅建立 raw 层、执行顺序、血缘和质量合同。订单/运单、波次/checkpoint、指标层分别在 B、C、D 建立；异动识别与归因、Tableau、经营报告、预测模型和 Agent 不在第二阶段范围内。",
            "",
        ]
    )
    (REPORT_DIR / "PHASE2_STEP_A_ACCEPTANCE.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_step_b_report(passed: list[str], connection: object) -> None:
    attempt_distribution = connection.execute(
        "SELECT attempt_count, count(*) FROM fact.fact_order_fulfillment "
        "GROUP BY attempt_count ORDER BY attempt_count"
    ).fetchall()
    lines = [
        "# 第二阶段 B：运单尝试与订单履约事实验收",
        "",
        "状态：**通过**。以下结果由本地事实表聚合生成，不含标识符、坐标或逐单时间线。",
        "",
        "## 守恒与质量结果",
        "",
        "- `fact_waybill_attempt`：654,343 行，一行一个 waybill；接受 568,546，拒绝 85,797。",
        "- `fact_order_fulfillment`：568,546 行，一行一个 order；所有订单恰有一次最终接受。",
        "- 跨 waybill 的日期/预订/下单时间不一致订单：61；订单属性取最终已接受 waybill 并保留标记。",
        "- 已接受但未完成：1；保留 `is_incomplete_accepted`，完成时长保持 NULL。",
        "- 事件顺序异常：0；核心持续时间负值：0。",
        "",
        "## 尝试次数分布",
        "",
        "| 尝试数 | 订单数 |",
        "|---:|---:|",
    ]
    for attempts, orders in attempt_distribution:
        lines.append(f"| {attempts:,} | {orders:,} |")
    lines.extend(
        [
            "",
            "尝试顺序按非 0 `dispatch_time` 升序排列，源文件行索引仅在同一派单秒内作确定性破同值；0 时间排在末尾。原始行不删除、不填补。",
            "",
            "## 自动检查",
            "",
            f"B 新增 {len(passed)} 项事实合同检查，全部通过；覆盖唯一性、行数守恒、接受/拒绝、关联、尝试汇总、61 个冲突标记、1 个未完成标记、时间顺序与非负持续时间。",
            "",
        ]
    )
    (REPORT_DIR / "PHASE2_STEP_B_ACCEPTANCE.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_step_c_report(passed: list[str], connection: object) -> None:
    wave_min, wave_max = connection.execute(
        "SELECT min(member_count), max(member_count) FROM fact.fact_courier_wave"
    ).fetchone()
    order_min, order_max, rider_min, rider_max = connection.execute(
        "SELECT min(pending_order_count), max(pending_order_count), "
        "min(candidate_courier_count), max(candidate_courier_count) "
        "FROM fact.fact_dispatch_checkpoint"
    ).fetchone()
    lines = [
        "# 第二阶段 C：骑手波次与派单 checkpoint 事实验收",
        "",
        "状态：**通过**。以下只公开聚合规模、覆盖和质量标记，不公开骑手、订单、波次或在手任务明细。",
        "",
        "## 波次事实",
        "",
        "- `fact_courier_wave`：206,748 行，`dt + courier_id + wave_id` 复合键唯一。",
        "- 波次成员 568,545 个，解析与订单关联覆盖均为 100%。",
        "- 官方开始时间与成员最早有效接单时间不一致 65,904 波；分析用开始时间全部采用重构值。",
        "- 官方结束时间与成员最大送达时间全部一致；基于重构开始时间的负持续时间为 0。",
        f"- 每波成员数范围：{wave_min:,}–{wave_max:,}。",
        "",
        "## checkpoint 事实",
        "",
        "- 24 个 `dt + dispatch_time` checkpoint，覆盖 8 个运营归属日；订单侧与骑手侧全部对齐。",
        f"- 每 checkpoint 待派订单 {order_min:,}–{order_max:,}，候选骑手 {rider_min:,}–{rider_max:,}。",
        "- 待派订单总成员 15,921，候选骑手总成员 62,044；候选集合的复合键均唯一。",
        "- `courier_waybills` 拆分成员可同时匹配 waybill/order 标识域，物理字段名与文字定义不能消除歧义；事实层统一保留 `courier_waybills_definition_uncertain=true`。",
        "- checkpoint 仅为 24 个选定时点快照，`is_selected_checkpoint_not_event_log=true`；不得外推为全天逐事件派单日志。",
        "",
        "## 自动检查",
        "",
        f"C 新增 {len(passed)} 项合同检查，全部通过；覆盖波次复合键、成员守恒/关联、开始/结束时间、持续时间、checkpoint 对齐、成员计数和集合键唯一性。",
        "",
    ]
    (REPORT_DIR / "PHASE2_STEP_C_ACCEPTANCE.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def write_metric_dictionary(connection: object) -> None:
    rows = connection.execute(
        "SELECT * FROM metrics.metric_catalog ORDER BY metric_name"
    ).fetchall()
    lines = [
        "# 第二阶段指标字典",
        "",
        "本字典由可执行 `metrics.metric_catalog` 生成。后续 Python、报告和 Tableau 必须读取 `metrics.daily_fulfillment`、`metrics.overall_fulfillment` 或 `metrics.checkpoint_snapshot`，不得另写平行口径。",
        "",
    ]
    labels = (
        "业务问题",
        "粒度",
        "公式",
        "分子",
        "分母",
        "单位",
        "过滤条件",
        "0/NULL处理",
        "质量标记与适用边界",
    )
    for row in rows:
        lines.extend([f"## `{row[0]}`", ""])
        for label, value in zip(labels, row[1:]):
            lines.append(f"- {label}：{value}。")
        lines.append("")
    (REPORT_DIR / "METRIC_DICTIONARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_step_d_reports(passed: list[str], connection: object) -> None:
    row = connection.execute(
        "SELECT order_count, waybill_attempt_count, waybill_acceptance_rate, "
        "first_attempt_success_rate, avg_attempt_count, avg_redispatch_count, "
        "completion_rate, avg_order_to_push_seconds, avg_push_to_first_dispatch_seconds, "
        "avg_final_dispatch_to_accept_seconds, avg_accept_to_fetch_seconds, "
        "avg_fetch_to_arrive_seconds, avg_end_to_end_seconds, strict_late_rate, "
        "buffer_8m_late_rate, avg_pickup_delay_seconds, "
        "avg_delivery_distance_coordinate_units, avg_wave_duration_seconds, "
        "avg_orders_per_wave FROM metrics.overall_fulfillment"
    ).fetchone()
    checkpoint = connection.execute(
        "SELECT min(pending_order_count), max(pending_order_count), "
        "min(candidate_courier_count), max(candidate_courier_count), "
        "min(pending_orders_per_candidate_courier), "
        "max(pending_orders_per_candidate_courier), "
        "min(candidate_couriers_per_pending_order), "
        "max(candidate_couriers_per_pending_order) FROM metrics.checkpoint_snapshot"
    ).fetchone()
    lines = [
        "# 第二阶段聚合指标对账报告",
        "",
        "以下数值只从 `metrics` schema 读取；均为全量聚合，不含按订单、骑手、商户、商圈或精确时间戳的明细。时长同时换算为分钟仅用于阅读，底层统一存秒。",
        "",
        "| 指标 | 聚合值 |",
        "|---|---:|",
        f"| 订单量 | {row[0]:,.0f} |",
        f"| waybill 尝试量 | {row[1]:,.0f} |",
        f"| waybill 接单率 | {row[2]:.6%} |",
        f"| 首次尝试/首次派单成功率 | {row[3]:.6%} |",
        f"| 平均尝试数 | {row[4]:.6f} 次/单 |",
        f"| 平均重派次数 | {row[5]:.6f} 次/单 |",
        f"| 完成率 | {row[6]:.6%} |",
        f"| 下单至入池 | {row[7] / 60:.3f} 分钟 |",
        f"| 入池至首次派单 | {row[8] / 60:.3f} 分钟 |",
        f"| 最终派单至接单 | {row[9] / 60:.3f} 分钟 |",
        f"| 接单至取餐 | {row[10] / 60:.3f} 分钟 |",
        f"| 取餐至送达 | {row[11] / 60:.3f} 分钟 |",
        f"| 全链路 | {row[12] / 60:.3f} 分钟 |",
        f"| 严格超时率 | {row[13]:.6%} |",
        f"| 8分钟缓冲超时率 | {row[14]:.6%} |",
        f"| 平均取餐延迟 | {row[15] / 60:.3f} 分钟 |",
        f"| 平均配送直线距离 | {row[16]:.3f} 匿名坐标单位 |",
        f"| 平均波次时长 | {row[17] / 60:.3f} 分钟 |",
        f"| 每波平均订单量/负载 | {row[18]:.6f} 订单/波 |",
        "",
        "## checkpoint 范围对账",
        "",
        f"24 个选定 checkpoint 的待派订单数范围 {checkpoint[0]:,.0f}–{checkpoint[1]:,.0f}，候选骑手数范围 {checkpoint[2]:,.0f}–{checkpoint[3]:,.0f}；订单/候选骑手比范围 {checkpoint[4]:.6f}–{checkpoint[5]:.6f}，候选骑手/订单比范围 {checkpoint[6]:.6f}–{checkpoint[7]:.6f}。该范围不能解释为全天逐事件分布。",
        "",
        "## 可追溯性",
        "",
        "指标分子、分母和合计字段保存在 `metrics.daily_fulfillment`；整体值由 `metrics.overall_fulfillment` 对日层分子分母再次汇总，不做日率简单平均。事实来源和公式完整保存在 `sql/30_metrics/30_metric_layer.sql`，指标元数据保存在 `sql/30_metrics/31_metric_catalog.sql`。",
        "",
        f"D 新增 {len(passed)} 项指标合同检查，全部通过。",
        "",
    ]
    (REPORT_DIR / "METRIC_RECONCILIATION.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    (REPORT_DIR / "PHASE2_STEP_D_ACCEPTANCE.md").write_text(
        "\n".join(
            [
                "# 第二阶段 D：指标体系与聚合指标层验收",
                "",
                "状态：**通过**。",
                "",
                "- 25 个指标定义已写入可执行 `metrics.metric_catalog` 并生成公开指标字典。",
                "- 日层、整体层和 checkpoint 层均由事实层 SQL 生成；整体比率按汇总分子/分母计算。",
                "- 订单、waybill、完成分母、尝试恒等式、超时单调性、比率边界、时长非负和 checkpoint 比值共识已自动验证。",
                f"- D 新增 {len(passed)} 项检查，A–D 累计 59 项合同检查全部通过。",
                "- 配送距离仅使用匿名坐标欧氏单位，不解释为公里或路网距离；取餐延迟不作因果归责。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", choices=("A", "B", "C", "D", "E"), default="A")
    args = parser.parse_args()
    if args.through not in {"A", "B", "C", "D"}:
        raise SystemExit(f"step {args.through} build is added with that step")

    connection = connect(reset=True)
    execute_sql_file(connection, "00_sources/00_raw_tables.sql")
    passed = assert_source_contract(connection)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_step_a_report(passed)
    total_passed = len(passed)
    if args.through in {"B", "C", "D"}:
        execute_sql_file(connection, "10_staging/10_waybill_attempt.sql")
        execute_sql_file(connection, "20_facts/20_order_fulfillment.sql")
        step_b_passed = assert_step_b_contract(connection)
        write_step_b_report(step_b_passed, connection)
        total_passed += len(step_b_passed)
    if args.through in {"C", "D"}:
        execute_sql_file(connection, "10_staging/11_wave_checkpoint.sql")
        execute_sql_file(connection, "20_facts/21_wave_checkpoint.sql")
        step_c_passed = assert_step_c_contract(connection)
        write_step_c_report(step_c_passed, connection)
        total_passed += len(step_c_passed)
    if args.through == "D":
        execute_sql_file(connection, "30_metrics/30_metric_layer.sql")
        execute_sql_file(connection, "30_metrics/31_metric_catalog.sql")
        step_d_passed = assert_step_d_contract(connection)
        write_metric_dictionary(connection)
        write_step_d_reports(step_d_passed, connection)
        total_passed += len(step_d_passed)
    connection.close()
    print(f"built ignored local database: {DATABASE_PATH.relative_to(DATABASE_PATH.parents[2])}")
    print(f"phase 2 through step {args.through} passed: {total_passed} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
