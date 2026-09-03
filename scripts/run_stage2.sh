#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_ROOT}/.venv/bin/python}"
DATABASE="${PROJECT_ROOT}/data/processed/meituan_fulfillment.duckdb"
FINGERPRINT="${PROJECT_ROOT}/data/interim/stage2_fingerprint.json"

"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/build_stage2.py" --database "${DATABASE}"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/validate_stage2.py" --database "${DATABASE}"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/fingerprint_stage2.py" --database "${DATABASE}" --output "${FINGERPRINT}"

# 同一输入就地重建第二次，用表结构、行数和全表语义哈希比较确定性。
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/build_stage2.py" --database "${DATABASE}"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/validate_stage2.py" --database "${DATABASE}"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/fingerprint_stage2.py" --database "${DATABASE}" --compare "${FINGERPRINT}"

"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/privacy_scan.py"
echo "Stage-2 one-command rebuild, validation, determinism, and privacy checks passed."
