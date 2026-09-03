#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_ROOT="${PROJECT_ROOT}/data/raw"
OFFICIAL_DIR="${RAW_ROOT}/Meituan-INFORMS-TSL-Research-Challenge"
OFFICIAL_URL="https://github.com/meituan/Meituan-INFORMS-TSL-Research-Challenge.git"

mkdir -p "${RAW_ROOT}"

if [[ ! -d "${OFFICIAL_DIR}/.git" ]]; then
  git clone --depth 1 "${OFFICIAL_URL}" "${OFFICIAL_DIR}"
else
  echo "Official repository already exists; leaving the local snapshot unchanged."
fi

unzip -n \
  "${OFFICIAL_DIR}/all_waybill_info_meituan_0322.csv.zip" \
  "all_waybill_info_meituan_0322.csv" \
  -d "${OFFICIAL_DIR}"

echo "Official commit: $(git -C "${OFFICIAL_DIR}" rev-parse HEAD)"
echo "Downloaded to: ${OFFICIAL_DIR}"
echo "License reminder: do not redistribute the dataset or commit raw files."
