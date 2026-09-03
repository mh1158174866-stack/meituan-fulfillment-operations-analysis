#!/usr/bin/env python3
"""Run the complete phase-one acceptance workflow twice and compare outputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "reports"
ACCEPTANCE_PATH = REPORT_DIR / "PHASE1_ACCEPTANCE.md"
DETERMINISTIC_REPORTS = (
    "DOWNLOAD_MANIFEST.md",
    "DATA_DICTIONARY.md",
    "DATA_QUALITY_REPORT.md",
    "TIME_SEMANTICS_REPORT.md",
)
RAW_FILES = (
    "all_waybill_info_meituan_0322.csv",
    "courier_wave_info_meituan.csv",
    "dispatch_rider_meituan.csv",
    "dispatch_waybill_meituan.csv",
)


def run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(REPO_ROOT / "scripts" / script), *arguments]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def report_hashes() -> dict[str, str]:
    return {name: sha256(REPORT_DIR / name) for name in DETERMINISTIC_REPORTS}


def assert_raw_files_ignored() -> None:
    for filename in RAW_FILES:
        path = REPO_ROOT / "data" / "raw" / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", str(path)], cwd=REPO_ROOT, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError(f"raw file is not ignored: {path.relative_to(REPO_ROOT)}")


def line_starting(path: Path, prefix: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line
    raise RuntimeError(f"expected line starting with {prefix!r} in {path.name}")


def write_acceptance(hashes: dict[str, str]) -> None:
    quality = REPORT_DIR / "DATA_QUALITY_REPORT.md"
    time_report = REPORT_DIR / "TIME_SEMANTICS_REPORT.md"
    lines = [
        "# 第一阶段验收记录",
        "",
        "状态：**通过**。本记录由 `scripts/run_phase1.py` 在同一干净输入上连续生成两次公开报告，逐文件比较 SHA-256 一致后写入。",
        "",
        "## 环境与输入",
        "",
        f"- Python：`{sys.version.split()[0]}`",
        f"- DuckDB：`{importlib.metadata.version('duckdb')}`",
        f"- certifi：`{importlib.metadata.version('certifi')}`",
        f"- pytz：`{importlib.metadata.version('pytz')}`",
        "- 官方数据版本：`1f9b4288cee5a78d1e5da007fc306bbaa662fc6d`",
        "- 四张原始表和下载附件均存在于 Git 忽略目录，未纳入公开候选文件。",
        "",
        "## 确定性复跑",
        "",
        "| 公开报告 | 两次一致的 SHA-256 |",
        "|---|---|",
    ]
    for name in DETERMINISTIC_REPORTS:
        lines.append(f"| `{name}` | `{hashes[name]}` |")
    lines.extend(
        [
            "",
            "## 关键规模与质量事实",
            "",
            line_starting(quality, "- 运单尝试共"),
            line_starting(quality, "- 去重订单"),
            line_starting(quality, "- 有多个运单"),
            "- " + line_starting(time_report, "预订单 "),
            line_starting(time_report, "- 因而确认存在"),
            line_starting(time_report, "- 结论：`wave_start_time`"),
            line_starting(time_report, "- 两张 dispatch 表是"),
            "",
            "## 验收清单",
            "",
            "- [x] 固定官方提交，可重建四张输入表和下载哈希清单。",
            "- [x] 四表严格全量读取；字段、类型、粒度、候选键、重复、缺失和 0 时间已验收。",
            "- [x] 订单/运单粒度、波次复合键、派单 checkpoint 和表间覆盖率已验收。",
            "- [x] `dt`、Asia/Shanghai、预订单日期偏移、事件顺序和已接单未完成记录已验收。",
            "- [x] `wave_start_time` 索引/对齐问题与 checkpoint 语义已记录。",
            "- [x] 四份公开报告第二次确定性复跑哈希完全一致。",
            "- [x] 隐私扫描器自测通过，公开候选文件扫描通过。",
            "- [x] 未创建正式事实表、经营结论、异动归因、看板、预测模型或 Agent。",
            "",
            "## 未解决问题",
            "",
            "- 同一订单跨多个 waybill 的日期/预订/下单时间版本存在少量不一致；第二阶段事实表必须明确取已接受 waybill 的订单属性并保留一致性标记。",
            "- 1 条已接单记录缺少送达时间，不能静默填补；涉及完成率或时长指标时需显式排除或单列。",
            "- `wave_start_time` 不能直接计算波次持续时长，应由波次成员最早有效 `grab_time` 重构。",
            "- `courier_waybills` 的字段名与官方文字口径不完全一致，需在正式建模前固定任务标识口径。",
            "- dispatch 数据只有 24 个选定 checkpoint，不能当作全周期派单日志。",
            "",
            "## 第二阶段入口",
            "",
            "第二阶段应先形成可审计的订单、运单尝试、波次和 checkpoint 事实层，再定义履约漏斗、时长与异常监控指标。必须继承本阶段的时间、粒度、缺失和隐私口径；在事实层与指标验收前不启动归因、看板、预测或 Agent。",
            "",
        ]
    )
    ACCEPTANCE_PATH.write_text("\n".join(lines), encoding="utf-8")


def pass_once(force_download: bool = False) -> dict[str, str]:
    download_arguments = ("--force",) if force_download else ()
    run("download_data.py", *download_arguments)
    run("audit_data.py")
    run("audit_time_semantics.py")
    run("privacy_scan.py")
    return report_hashes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    run("privacy_scan.py", "--self-test")
    first = pass_once(force_download=args.force_download)
    second = pass_once(force_download=False)
    if first != second:
        differences = [name for name in DETERMINISTIC_REPORTS if first[name] != second[name]]
        raise RuntimeError(f"non-deterministic reports: {differences}")
    assert_raw_files_ignored()
    write_acceptance(second)
    run("privacy_scan.py")
    print("phase 1 acceptance passed")
    print(f"wrote {ACCEPTANCE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
