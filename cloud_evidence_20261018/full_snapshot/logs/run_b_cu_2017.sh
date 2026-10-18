#!/usr/bin/env bash
set -euo pipefail

trap 'rc=$?; echo "$rc" > /data/airslot/logs/b_cu_2017.exitcode; echo "EXIT_CODE=$rc"' EXIT

cd /data/airslot/worktree
export PYTHONPATH="$PWD"

PYTHON="/data/airslot/source/.venv/bin/python"
OUTPUT="artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1"

# 防止意外覆盖已有参考
if [ -e "$OUTPUT/2017/M2_REFERENCES" ]; then
    echo "EXISTING_REFERENCE_STOP"
    exit 2
fi

"$PYTHON" -m data2.scripts.build_year_references \
    --years 2017 \
    --output-root "$OUTPUT" \
    --continuity-contract JATM_F_CONTINUITY_B_V1

echo "B_CU_2017_BUILD_PASS"
