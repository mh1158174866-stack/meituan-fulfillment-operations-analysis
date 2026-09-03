#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PROJECT_ROOT}/scripts/download_official_data.sh"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/audit_stage1.py"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/validate_stage1.py"
"${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/privacy_scan.py"
