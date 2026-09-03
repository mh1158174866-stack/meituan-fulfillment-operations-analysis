#!/usr/bin/env python3
"""Fail closed when public repository candidates appear to contain row-level data."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PUBLIC_SUFFIXES = {
    ".csv",
    ".zip",
    ".parquet",
    ".pdf",
    ".duckdb",
    ".db",
}
MAX_PUBLIC_FILE_BYTES = 5 * 1024 * 1024
SENSITIVE_KEYS = {
    "order_id",
    "waybill_id",
    "courier_id",
    "poi_id",
    "da_id",
    "sender_lng",
    "sender_lat",
    "recipient_lng",
    "recipient_lat",
    "grab_lng",
    "grab_lat",
    "rider_lng",
    "rider_lat",
    "order_ids",
    "courier_waybills",
}
ASSIGNED_IDENTIFIER = re.compile(
    r"\b(?:order_id|waybill_id|courier_id|poi_id|da_id)\b\s*[:=]\s*[0-9]{4,}",
    re.IGNORECASE,
)
ASSIGNED_COORDINATE = re.compile(
    r"\b(?:sender|recipient|grab|rider)_(?:lng|lat)\b\s*[:=]\s*-?[0-9]{4,}(?:\.[0-9]+)?",
    re.IGNORECASE,
)
LONG_IDENTIFIER_LIST = re.compile(r"\[\s*[0-9]{4,}\s*(?:,\s*[0-9]{4,}\s*){2,}\]")


def repository_candidates() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [REPO_ROOT / item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def sensitive_json_paths(value: object, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}"
            if key.lower() in SENSITIVE_KEYS and nested not in (None, "", [], {}):
                findings.append(child)
            findings.extend(sensitive_json_paths(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(sensitive_json_paths(nested, f"{prefix}[{index}]"))
    return findings


def scan_text(path: Path, text: str) -> list[str]:
    findings: list[str] = []
    if ASSIGNED_IDENTIFIER.search(text):
        findings.append("identifier field assigned a literal value")
    if ASSIGNED_COORDINATE.search(text):
        findings.append("coordinate field assigned a literal value")
    if LONG_IDENTIFIER_LIST.search(text):
        findings.append("list contains three or more identifier-like values")
    if path.suffix.lower() in {".md", ".txt"}:
        for line in text.splitlines():
            if line.count(",") >= 10 and len(re.findall(r"(?<!\w)-?[0-9]+(?:\.\d+)?", line)) >= 5:
                findings.append("line resembles a raw CSV record")
                break
    return findings


def scan_path(path: Path) -> list[str]:
    relative = path.relative_to(REPO_ROOT)
    findings: list[str] = []
    if path.suffix.lower() in FORBIDDEN_PUBLIC_SUFFIXES:
        findings.append(f"forbidden public file type: {path.suffix.lower()}")
        return findings
    if path.stat().st_size > MAX_PUBLIC_FILE_BYTES:
        findings.append(f"public candidate exceeds {MAX_PUBLIC_FILE_BYTES} bytes")
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            findings.append(f"invalid JSON: {error}")
        else:
            findings.extend(f"sensitive JSON path: {item}" for item in sensitive_json_paths(value))
    elif path.suffix.lower() in {".md", ".txt", ".py", ".toml", ".yml", ".yaml"} or relative.name in {
        "README.md",
        "requirements.txt",
        ".gitignore",
        ".python-version",
    }:
        try:
            findings.extend(scan_text(path, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            findings.append("text candidate is not valid UTF-8")
    return findings


def run_scan() -> list[tuple[Path, list[str]]]:
    failures: list[tuple[Path, list[str]]] = []
    for path in repository_candidates():
        if not path.is_file():
            continue
        findings = scan_path(path)
        if findings:
            failures.append((path.relative_to(REPO_ROOT), findings))
    return failures


def self_test() -> None:
    safe = "去重订单 568,546 个；字段 `order_id` 仅用于说明。"
    unsafe_id = "order_id" + " = " + str(12_345_678)
    unsafe_list = "[" + ", ".join(str(value) for value in (12_345_678, 12_345_679, 12_345_680)) + "]"
    if scan_text(Path("safe.md"), safe):
        raise AssertionError("safe aggregate text was rejected")
    if not scan_text(Path("unsafe.md"), unsafe_id):
        raise AssertionError("literal identifier was not detected")
    if not scan_text(Path("unsafe.md"), unsafe_list):
        raise AssertionError("identifier list was not detected")
    if not sensitive_json_paths({"order_id": 12345678}):
        raise AssertionError("sensitive JSON key was not detected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("privacy scanner self-test passed")
    failures = run_scan()
    if failures:
        for path, findings in failures:
            print(f"FAIL {path}: {'; '.join(findings)}", file=sys.stderr)
        return 1
    print(f"privacy scan passed: {len(repository_candidates())} public candidate files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
