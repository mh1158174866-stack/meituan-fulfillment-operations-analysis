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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", choices=("A", "B", "C", "D", "E"), default="A")
    args = parser.parse_args()
    if args.through != "A":
        raise SystemExit(f"step {args.through} build is added with that step")

    connection = connect(reset=True)
    execute_sql_file(connection, "00_sources/00_raw_tables.sql")
    passed = assert_source_contract(connection)
    connection.close()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_step_a_report(passed)
    print(f"built ignored local database: {DATABASE_PATH.relative_to(DATABASE_PATH.parents[2])}")
    print(f"phase 2 step A passed: {len(passed)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
