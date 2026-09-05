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
    ".7z",
    ".arrow",
    ".csv",
    ".db",
    ".feather",
    ".gz",
    ".jsonl",
    ".ndjson",
    ".npy",
    ".npz",
    ".parquet",
    ".pdf",
    ".pkl",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tsv",
    ".duckdb",
    ".xls",
    ".xlsx",
    ".zip",
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
    "wave_id",
    "rider_id",
    "onhand_id",
}
ASSIGNED_IDENTIFIER = re.compile(
    r"\b[A-Za-z0-9_]*(?:order|waybill|courier|rider|poi|da|wave|onhand)_"
    r"(?:id|hash)[A-Za-z0-9_]*\b\s*['\"]?\s*[:=]\s*"
    r"(?:[0-9]+|['\"][A-Za-z0-9_-]+['\"])",
    re.IGNORECASE,
)
ASSIGNED_COORDINATE = re.compile(
    r"\b[A-Za-z0-9_]*(?:sender|recipient|grab|rider)_(?:lng|lat)[A-Za-z0-9_]*\b"
    r"\s*['\"]?\s*[:=]\s*-?[0-9]+(?:\.[0-9]+)?",
    re.IGNORECASE,
)
SENSITIVE_LIST_ASSIGNMENT = re.compile(
    r"\b[A-Za-z0-9_]*(?:order|waybill|courier|rider|poi|da|wave|onhand)_"
    r"(?:ids?|hash(?:es)?)[A-Za-z0-9_]*\b\s*['\"]?\s*[:=]\s*\[[^\]]+\]",
    re.IGNORECASE,
)
SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:hashed?_)?(?:order|waybill|courier|rider|poi|da|wave|onhand)_"
    r"(?:id|hash)(?:$|_)",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".md", ".txt", ".py", ".toml", ".yml", ".yaml", ".sql", ".sh"}


def repository_candidates() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [REPO_ROOT / item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def staged_candidates() -> list[tuple[Path, bytes]]:
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    candidates: list[tuple[Path, bytes]] = []
    for raw_name in completed.stdout.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8")
        blob = subprocess.run(
            ["git", "show", f":{name}"], cwd=REPO_ROOT, check=True, capture_output=True
        ).stdout
        candidates.append((Path(name), blob))
    return candidates


def sensitive_json_paths(value: object, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}"
            if (
                key.lower() in SENSITIVE_KEYS or SENSITIVE_KEY.search(key)
            ) and nested not in (None, "", [], {}):
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
    if SENSITIVE_LIST_ASSIGNMENT.search(text):
        findings.append("identifier-list field assigned literal members")
    if path.suffix.lower() in {".md", ".txt"}:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.count(",") >= 10 and len(re.findall(r"(?<!\w)-?[0-9]+(?:\.\d+)?", line)) >= 5:
                findings.append("line resembles a raw CSV record")
                break
            if not ("," in line or "|" in line):
                continue
            header_tokens = [token.strip(" `\t") for token in re.split(r"[,|]", line)]
            sensitive_headers = sum(
                token.lower() in SENSITIVE_KEYS or bool(SENSITIVE_KEY.search(token))
                for token in header_tokens
                if token
            )
            if sensitive_headers == 0:
                continue
            for candidate in lines[index + 1 : index + 4]:
                stripped = candidate.strip()
                if not stripped or re.fullmatch(r"[|:\-\s]+", stripped):
                    continue
                literal_cells = re.findall(
                    r"(?:^|[,|])\s*['\"]?-?[A-Za-z0-9_.-]+['\"]?\s*(?=[,|]|$)",
                    stripped,
                )
                if len(literal_cells) >= sensitive_headers:
                    findings.append("table resembles identifier-level records")
                break
    return findings


def scan_bytes(path: Path, data: bytes) -> list[str]:
    findings: list[str] = []
    if path.suffix.lower() in FORBIDDEN_PUBLIC_SUFFIXES:
        findings.append(f"forbidden public file type: {path.suffix.lower()}")
        return findings
    if len(data) > MAX_PUBLIC_FILE_BYTES:
        findings.append(f"public candidate exceeds {MAX_PUBLIC_FILE_BYTES} bytes")
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            findings.append(f"invalid JSON: {error}")
        else:
            findings.extend(f"sensitive JSON path: {item}" for item in sensitive_json_paths(value))
    elif path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        "README.md",
        "requirements.txt",
        ".gitignore",
        ".python-version",
    }:
        try:
            findings.extend(scan_text(path, data.decode("utf-8")))
        except UnicodeDecodeError:
            findings.append("text candidate is not valid UTF-8")
    return findings


def scan_path(path: Path) -> list[str]:
    return scan_bytes(path.relative_to(REPO_ROOT), path.read_bytes())


def run_scan() -> list[tuple[str, list[str]]]:
    failures: list[tuple[str, list[str]]] = []
    for path in repository_candidates():
        if not path.is_file():
            continue
        findings = scan_path(path)
        if findings:
            failures.append((str(path.relative_to(REPO_ROOT)), findings))
    for path, data in staged_candidates():
        findings = scan_bytes(path, data)
        if findings:
            failures.append((f"{path} (staged)", findings))
    return failures


def self_test() -> None:
    safe = "去重订单 568,546 个；字段 `order_id` 仅用于说明。"
    unsafe_id = "order_" + "id = " + str(7)
    unsafe_list = "order_" + "ids = [" + ", ".join(str(value) for value in (7, 8)) + "]"
    if scan_text(Path("safe.md"), safe):
        raise AssertionError("safe aggregate text was rejected")
    if not scan_text(Path("unsafe.md"), unsafe_id):
        raise AssertionError("literal identifier was not detected")
    if not scan_text(Path("unsafe.md"), unsafe_list):
        raise AssertionError("identifier list was not detected")
    sensitive_key = "order_" + "id"
    if not sensitive_json_paths({sensitive_key: 7}):
        raise AssertionError("sensitive JSON key was not detected")
    unsafe_hashed_id = "hashed_order_" + 'id = "abc123def456"'
    unsafe_coordinate = "rider_" + "lat = " + "31.2304"
    two_identifiers = "order_" + "ids = [7, 8]"
    if not scan_text(Path("unsafe.sql"), unsafe_hashed_id):
        raise AssertionError("hashed identifier literal was not detected")
    if not scan_text(Path("unsafe.sql"), unsafe_coordinate):
        raise AssertionError("decimal coordinate literal was not detected")
    if not scan_text(Path("unsafe.md"), two_identifiers):
        raise AssertionError("two-identifier list was not detected")
    narrow_table = "order_" + "id,dt\n7,20221017"
    if not scan_text(Path("unsafe.md"), narrow_table):
        raise AssertionError("narrow identifier table was not detected")


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
    candidate_versions = len(repository_candidates()) + len(staged_candidates())
    print(f"privacy scan passed: {candidate_versions} public candidate versions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
