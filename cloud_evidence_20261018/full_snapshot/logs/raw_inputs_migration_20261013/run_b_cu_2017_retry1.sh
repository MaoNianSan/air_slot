#!/usr/bin/env bash
# B CU 2017 retry #1 (2026-10-13): regenerate M2 references for year 2017 under
# contract JATM_F_CONTINUITY_B_V1, after DB1B Coupon 2017 Q1/Q2 and T-100 2017
# inputs were SHA-256 verified on the server.
#
# Prior failed run (preserved, do not overwrite):
#   b_cu_2017.log / b_cu_2017.pid / b_cu_2017.exitcode (exit 1,
#   REFERENCE_DATASET_MISMATCH at passenger reference build, missing DB1B).
# This retry uses fresh records: b_cu_2017_retry1.{log,pid,exitcode}.
set -uo pipefail

LOGDIR=/data/airslot/logs
LOG="$LOGDIR/b_cu_2017_retry1.log"
PIDFILE="$LOGDIR/b_cu_2017_retry1.pid"
EXITFILE="$LOGDIR/b_cu_2017_retry1.exitcode"

cd /data/airslot/worktree
export PYTHONPATH="$PWD"

PYTHON="/data/airslot/source/.venv/bin/python"
OUTPUT="artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1"
REFS="$OUTPUT/2017/M2_REFERENCES"

trap 'rc=$?; echo "$rc" > "$EXITFILE"; echo "EXIT_CODE=$rc" >> "$LOG"' EXIT

# Guard: proceed only when M2_REFERENCES is absent or an EMPTY directory (the
# empty dir is the documented leftover of the failed run). Non-empty => stop.
if [ -d "$REFS" ] && [ -n "$(find "$REFS" -mindepth 1 -print -quit)" ]; then
    echo "EXISTING_REFERENCE_STOP (non-empty $REFS)" >> "$LOG"
    exit 2
fi

echo $$ > "$PIDFILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] B_CU_2017_RETRY1 start (contract JATM_F_CONTINUITY_B_V1)" >> "$LOG"

"$PYTHON" -m data2.scripts.build_year_references \
    --years 2017 \
    --output-root "$OUTPUT" \
    --continuity-contract JATM_F_CONTINUITY_B_V1 >> "$LOG" 2>&1
rc=$?

if [ "$rc" -eq 0 ] && [ -f "$REFS/M2_REFERENCE_BUNDLE_MANIFEST.json" ]; then
    echo "B_CU_2017_BUILD_PASS" >> "$LOG"
else
    echo "B_CU_2017_BUILD_FAIL rc=$rc" >> "$LOG"
    exit "$rc"
fi
