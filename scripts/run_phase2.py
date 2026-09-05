#!/usr/bin/env python3
"""Build phase two in dependency order and emit aggregate-only acceptance reports."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys

import duckdb

from phase2_common import (
    DATABASE_PATH,
    REPORT_DIR,
    SOURCE_EXPECTATIONS,
    assert_source_contract,
    assert_step_b_contract,
    assert_step_c_contract,
    assert_step_d_contract,
    assert_step_e_contract,
    connect,
    execute_sql_file,
    logical_database_fingerprint,
    sha256,
)


DETERMINISTIC_REPORTS = (
    "PHASE2_STEP_A_ACCEPTANCE.md",
    "PHASE2_STEP_B_ACCEPTANCE.md",
    "PHASE2_STEP_C_ACCEPTANCE.md",
    "PHASE2_STEP_D_ACCEPTANCE.md",
    "METRIC_DICTIONARY.md",
    "METRIC_RECONCILIATION.md",
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
        "- 已接受但未完成：1；保留 `is_incomplete_accepted`，完成时长保持 NULL。另有 1 条已接受记录的 `dispatch_time=0`，保留 `has_missing_dispatch_time`，仅相关派单时长保持 NULL。",
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
        "本字典由可执行 `metrics.metric_catalog` 生成。每项定义须与 `docs/PHASE2_QUALITY_FLAGS.md` 的统一质量处理合同合并阅读。后续 Python、报告和 Tableau 必须读取 `metrics.daily_fulfillment`、`metrics.overall_fulfillment` 或 `metrics.checkpoint_snapshot`，不得另写平行口径。",
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


def write_step_d_reports(
    passed: list[str], connection: object, cumulative_count: int
) -> None:
    row = connection.execute(
        "SELECT order_count, waybill_attempt_count, waybill_acceptance_rate, "
        "first_attempt_success_rate, avg_attempt_count, avg_redispatch_count, "
        "completion_rate, avg_order_to_push_seconds, avg_push_to_first_dispatch_seconds, "
        "avg_first_dispatch_to_accept_seconds, avg_final_dispatch_to_accept_seconds, "
        "avg_accept_to_fetch_seconds, "
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
        f"| 首次派单至最终接单（含拒绝/重派等待） | {row[9] / 60:.3f} 分钟 |",
        f"| 最终派单至接单 | {row[10] / 60:.3f} 分钟 |",
        f"| 接单至取餐 | {row[11] / 60:.3f} 分钟 |",
        f"| 取餐至送达 | {row[12] / 60:.3f} 分钟 |",
        f"| 全链路 | {row[13] / 60:.3f} 分钟 |",
        f"| 严格超时率 | {row[14]:.6%} |",
        f"| 8分钟缓冲超时率 | {row[15]:.6%} |",
        f"| 平均取餐延迟 | {row[16] / 60:.3f} 分钟 |",
        f"| 平均配送直线距离 | {row[17]:.3f} 匿名坐标单位 |",
        f"| 平均波次时长 | {row[18] / 60:.3f} 分钟 |",
        f"| 每波平均订单量/负载 | {row[19]:.6f} 订单/波 |",
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
                f"- D 新增 {len(passed)} 项检查，A–D 累计 {cumulative_count} 项合同检查全部通过。",
                "- 配送距离仅使用匿名坐标欧氏单位，不解释为公里或路网距离；取餐延迟不作因果归责。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def report_hashes() -> dict[str, str]:
    return {name: sha256(REPORT_DIR / name) for name in DETERMINISTIC_REPORTS}


def write_step_e_reports(
    all_passed: list[str],
    step_e_passed: list[str],
    logical_digest: str,
    table_fingerprints: list[tuple[str, int, str]],
    hashes: dict[str, str],
) -> None:
    schema_counts: dict[str, int] = {}
    for qualified_name, _, _ in table_fingerprints:
        schema = qualified_name.split(".", 1)[0]
        schema_counts[schema] = schema_counts.get(schema, 0) + 1

    test_lines = [
        "# 第二阶段自动测试与确定性报告",
        "",
        "状态：**通过**。`scripts/run_phase2.py --through E` 从固定原始输入连续完整重建两次，A–D 合同、E 跟踪范围合同、逻辑数据库指纹和公开报告哈希均一致后才写入本报告。",
        "",
        "## 环境",
        "",
        f"- Python：`{sys.version.split()[0]}`",
        f"- DuckDB：`{importlib.metadata.version('duckdb')}`",
        "- 时区：`Asia/Shanghai`",
        "- 官方数据提交：`1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`",
        "",
        "## 合同检查",
        "",
        f"- A–D：{len(all_passed) - len(step_e_passed)} 项；E：{len(step_e_passed)} 项；累计：{len(all_passed)} 项，全部通过。",
        "- E 检查：" + "、".join(f"`{name}`" for name in step_e_passed) + "。",
        "- 隐私扫描器自测和最终公开候选文件扫描由同一入口在报告写入后执行；入口成功退出即表示通过。",
        "",
        "## 两次完整重建指纹",
        "",
        f"- 逻辑数据库 SHA-256：`{logical_digest}`。",
        f"- 逻辑表共 {len(table_fingerprints)} 张："
        + "、".join(f"`{schema}` {count} 张" for schema, count in sorted(schema_counts.items()))
        + "。",
        "- 逻辑指纹覆盖每张表的列名/类型/可空性、行数、全列行哈希异或及保留重复次数的行哈希和，再对规范化清单计算 SHA-256。",
        "- DuckDB 物理文件包含存储布局元数据，等价重建的字节哈希不承诺稳定，因此不把物理文件 SHA 当作数据确定性证据。",
        "",
        "| 公开报告 | 两次一致的 SHA-256 |",
        "|---|---|",
    ]
    for name in DETERMINISTIC_REPORTS:
        test_lines.append(f"| `{name}` | `{hashes[name]}` |")
    test_lines.extend(
        [
            "",
            "## 测试范围",
            "",
            "已覆盖结构、主键/复合键唯一性、行数与成员守恒、接受/拒绝、关联覆盖、0 时间、事件顺序、持续时间非负、61 个属性冲突、1 个未完成记录、65,904 个波次开始偏差、24 个 checkpoint 对齐、指标分子分母恒等式、比率边界、隐私规则和 Git 跟踪范围。",
            "",
        ]
    )
    (REPORT_DIR / "PHASE2_TEST_REPORT.md").write_text(
        "\n".join(test_lines), encoding="utf-8"
    )

    acceptance_lines = [
        "# 第二阶段总验收",
        "",
        "状态：**通过**。第二阶段已形成可审计的 SQL 数据层、四类事实对象、统一指标层与安全聚合对账；未进入异动识别与归因、Tableau、经营报告、预测模型或 Agent。",
        "",
        "## 交付与关键数字",
        "",
        "- 运单尝试事实：654,343 行；订单履约事实：568,546 行；接受 568,546，拒绝 85,797。",
        "- 跨 waybill 属性不一致订单 61；已接单未完成 1；已接受但派单时间为 0 的订单 1；均保留质量标记且未静默修正。",
        "- 波次事实 206,748 行；成员 568,545；官方开始时间不一致 65,904；分析时长使用重构开始时间。",
        "- checkpoint 24 个、覆盖 8 个 `dt`；待派订单成员 15,921、候选骑手成员 62,044；仅代表选定快照。",
        "- 指标目录 25 项；日层、整体层与 checkpoint 层均从同一 `metrics` schema 取数。",
        f"- 自动合同 {len(all_passed)} 项、逻辑数据库双重建 SHA-256 `{logical_digest}`、6 份公开报告哈希均通过确定性比较。",
        "",
        "## 已知限制",
        "",
        "- `courier_waybills` 字段名与官方文字定义仍有歧义，保留不确定标记，不据此作个体结论。",
        "- dispatch 仅 24 个 checkpoint，不能当作全天逐事件日志或用于第三阶段阈值识别。",
        "- 配送距离是匿名坐标欧氏单位，不能换算为公里或路网距离。",
        "- 所有结果是描述性事实与指标，不作因果归因；第三阶段才可另行定义 MAD 阈值、贡献分解与案例筛选。",
        "- 本地 Codex snapshot ref 的历史对象含官方原始文件，但不属于 `main`、Phase 1 或 Phase 2 远端分支祖先；本任务不删除该本地 ref，且只允许显式推送 Phase 2 分支，禁止 `git push --all` 或 `--mirror`。清理本地 ref/对象需另行授权。",
        "",
        "## 复现",
        "",
        "```bash",
        "python3 -m venv .venv",
        ".venv/bin/python -m pip install -r requirements.txt",
        ".venv/bin/python scripts/download_data.py",
        ".venv/bin/python scripts/run_phase2.py --through E",
        ".venv/bin/python scripts/validate_phase2.py --step E",
        "```",
        "",
        "原始 CSV/ZIP 和本地 DuckDB 必须留在 Git 忽略目录；发布前另以 `git diff --cached`、`scripts/privacy_scan.py` 和远端 SHA 只读核验提交范围。各步骤提交 SHA 与最终 push 结果在任务交付记录中报告。",
        "",
    ]
    (REPORT_DIR / "PHASE2_ACCEPTANCE.md").write_text(
        "\n".join(acceptance_lines), encoding="utf-8"
    )


def build_once(through: str) -> tuple[duckdb.DuckDBPyConnection, list[str]]:
    connection = connect(reset=True)
    execute_sql_file(connection, "00_sources/00_raw_tables.sql")
    passed = assert_source_contract(connection)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_step_a_report(passed)
    if through in {"B", "C", "D"}:
        execute_sql_file(connection, "10_staging/10_waybill_attempt.sql")
        execute_sql_file(connection, "20_facts/20_order_fulfillment.sql")
        step_b_passed = assert_step_b_contract(connection)
        write_step_b_report(step_b_passed, connection)
        passed.extend(step_b_passed)
    if through in {"C", "D"}:
        execute_sql_file(connection, "10_staging/11_wave_checkpoint.sql")
        execute_sql_file(connection, "20_facts/21_wave_checkpoint.sql")
        step_c_passed = assert_step_c_contract(connection)
        write_step_c_report(step_c_passed, connection)
        passed.extend(step_c_passed)
    if through == "D":
        execute_sql_file(connection, "30_metrics/30_metric_layer.sql")
        execute_sql_file(connection, "30_metrics/31_metric_catalog.sql")
        step_d_passed = assert_step_d_contract(connection)
        write_metric_dictionary(connection)
        write_step_d_reports(step_d_passed, connection, len(passed) + len(step_d_passed))
        passed.extend(step_d_passed)
    return connection, passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", choices=("A", "B", "C", "D", "E"), default="A")
    args = parser.parse_args()
    if args.through != "E":
        connection, passed = build_once(args.through)
        connection.close()
        print(f"built ignored local database: {DATABASE_PATH.relative_to(DATABASE_PATH.parents[2])}")
        print(f"phase 2 through step {args.through} passed: {len(passed)} checks")
        return 0

    first_connection, first_passed = build_once("D")
    first_logical_digest, first_table_fingerprints = logical_database_fingerprint(
        first_connection
    )
    first_hashes = report_hashes()
    first_connection.close()

    second_connection, second_passed = build_once("D")
    second_logical_digest, second_table_fingerprints = logical_database_fingerprint(
        second_connection
    )
    second_hashes = report_hashes()
    step_e_passed = assert_step_e_contract(second_connection)
    second_connection.close()

    if first_passed != second_passed:
        raise RuntimeError("contract result names changed between complete rebuilds")
    if first_logical_digest != second_logical_digest:
        raise RuntimeError("logical database fingerprint changed between complete rebuilds")
    if first_table_fingerprints != second_table_fingerprints:
        raise RuntimeError("per-table logical fingerprints changed between complete rebuilds")
    if first_hashes != second_hashes:
        changed = [name for name in DETERMINISTIC_REPORTS if first_hashes[name] != second_hashes[name]]
        raise RuntimeError(f"public report hashes changed between complete rebuilds: {changed}")

    all_passed = second_passed + step_e_passed
    write_step_e_reports(
        all_passed,
        step_e_passed,
        second_logical_digest,
        second_table_fingerprints,
        second_hashes,
    )
    subprocess.run(
        [sys.executable, str(DATABASE_PATH.parents[2] / "scripts" / "privacy_scan.py"), "--self-test"],
        cwd=DATABASE_PATH.parents[2],
        check=True,
    )
    print(f"built ignored local database: {DATABASE_PATH.relative_to(DATABASE_PATH.parents[2])}")
    print(f"phase 2 through step E passed: {len(all_passed)} checks")
    print(f"deterministic logical database SHA-256: {second_logical_digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
