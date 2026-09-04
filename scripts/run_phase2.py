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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", choices=("A", "B", "C", "D", "E"), default="A")
    args = parser.parse_args()
    if args.through not in {"A", "B", "C"}:
        raise SystemExit(f"step {args.through} build is added with that step")

    connection = connect(reset=True)
    execute_sql_file(connection, "00_sources/00_raw_tables.sql")
    passed = assert_source_contract(connection)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_step_a_report(passed)
    total_passed = len(passed)
    if args.through in {"B", "C"}:
        execute_sql_file(connection, "10_staging/10_waybill_attempt.sql")
        execute_sql_file(connection, "20_facts/20_order_fulfillment.sql")
        step_b_passed = assert_step_b_contract(connection)
        write_step_b_report(step_b_passed, connection)
        total_passed += len(step_b_passed)
    if args.through == "C":
        execute_sql_file(connection, "10_staging/11_wave_checkpoint.sql")
        execute_sql_file(connection, "20_facts/21_wave_checkpoint.sql")
        step_c_passed = assert_step_c_contract(connection)
        write_step_c_report(step_c_passed, connection)
        total_passed += len(step_c_passed)
    connection.close()
    print(f"built ignored local database: {DATABASE_PATH.relative_to(DATABASE_PATH.parents[2])}")
    print(f"phase 2 through step {args.through} passed: {total_passed} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
