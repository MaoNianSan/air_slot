#!/usr/bin/env bash
# Unified B CU year-bundle task runner (2026-10-13 authorized round).
# Usage: bcu_task_runner.sh <tag> <year> <output_root_rel>
# Records (per task): started_at, code identity, input SHA-256, PID, exit code,
# /usr/bin/time -v (wall, CPU%, peak RSS), output SHA-256, PASS/FAILED/BLOCKED.
set -uo pipefail
TAG=$1; YEAR=$2; OUTPUT=$3
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
LOG=$TASKDIR/log
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHON=/data/airslot/source/.venv/bin/python
REFS="$OUTPUT/$YEAR/M2_REFERENCES"

echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "code_snapshot=583f2c12 + patch_8cc7a1b7 (local commit d1c72a7)" >> "$TASKDIR/meta"
echo "task=$TAG year=$YEAR output_root=$OUTPUT" >> "$TASKDIR/meta"
sha256sum "data2/raw/bts/t100/$YEAR/T_T100_SEGMENT_ALL_CARRIER.csv" \
  "data2/raw/bts/db1b/$YEAR/coupon/Origin_and_Destination_Survey_DB1BCoupon_${YEAR}_1.csv" \
  "data2/raw/bts/db1b/$YEAR/coupon/Origin_and_Destination_Survey_DB1BCoupon_${YEAR}_2.csv" \
  > "$TASKDIR/input_sha256.txt"

if [ -d "$REFS" ] && [ -n "$(find "$REFS" -mindepth 1 -print -quit)" ]; then
  echo "BLOCKED_REFERENCE_EXISTS $REFS" >> "$LOG"
  echo BLOCKED_REFERENCE_EXISTS > "$TASKDIR/status"
  exit 2
fi

echo "[$(date -u +%FT%TZ)] START $TAG year=$YEAR output=$OUTPUT" >> "$LOG"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" -m data2.scripts.build_year_references \
  --years "$YEAR" --output-root "$OUTPUT" \
  --continuity-contract JATM_F_CONTINUITY_B_V1 >> "$LOG" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ] && [ -f "$REFS/M2_REFERENCE_BUNDLE_MANIFEST.json" ]; then
  echo "B_CU_${YEAR}_BUILD_PASS" >> "$LOG"
  (cd "$REFS" && sha256sum *.json) > "$TASKDIR/output_sha256.txt"
  echo PASS > "$TASKDIR/status"
else
  echo "B_CU_${YEAR}_BUILD_FAIL rc=$rc" >> "$LOG"
  echo "FAILED_rc=$rc" > "$TASKDIR/status"
fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
