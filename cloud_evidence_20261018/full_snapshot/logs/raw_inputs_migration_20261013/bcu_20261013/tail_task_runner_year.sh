#!/usr/bin/env bash
# Annual tail task runner (round 4): tail_task_runner_year.sh <year>
# Guards: requires that year's M1 bindings (model_bindings) to validate first
# and that no tail manifest exists yet; refuses silently overwriting anything.
set -uo pipefail
YEAR=$1
TAG=tail_$YEAR
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
LOG=$TASKDIR/log
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHON=/data/airslot/source/.venv/bin/python
DECISION=deploy/jatm_cloud/scientific_decisions/ANNUAL_TAIL_USER_DECISION.json
TAIL="artifacts/models/m1/YEAR_$YEAR/TAIL_REFERENCE_V1/MANIFEST.json"

echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "code_snapshot=583f2c12 + patch_8cc7a1b7 (d1c72a7) + patch_1d3ba5d3 (ffa7487)" >> "$TASKDIR/meta"
echo "task=$TAG year=$YEAR" >> "$TASKDIR/meta"
sha256sum "$DECISION" \
  "data2/reports/cohort_size_stability/$YEAR/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl" \
  "artifacts/models/pre/PRE_MULTIYEAR_V1/$YEAR/DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json" \
  "artifacts/models/pre/PRE_MULTIYEAR_V1/$YEAR/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json" \
  > "$TASKDIR/input_sha256.txt"

if [ -f "$TAIL" ]; then
  echo "BLOCKED_TAIL_EXISTS $TAIL" >> "$LOG"
  echo BLOCKED_TAIL_EXISTS > "$TASKDIR/status"
  exit 2
fi

if ! "$PYTHON" -c "
import sys
sys.path.insert(0, '/data/airslot/worktree')
from exp.jatm_s34.cloud_inputs import model_bindings
model_bindings($YEAR, root='/data/airslot/worktree')
" >> "$LOG" 2>&1; then
  echo "BLOCKED_M1_MISSING_OR_INVALID year=$YEAR" >> "$LOG"
  echo BLOCKED_M1_MISSING_OR_INVALID > "$TASKDIR/status"
  exit 2
fi

echo "[$(date -u +%FT%TZ)] START $TAG (tail-only build, M1 bindings verified)" >> "$LOG"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" -m exp.jatm_s34.build_annual_tail \
  --year "$YEAR" --decision "$DECISION" >> "$LOG" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ]; then
  V=$("$PYTHON" -c "
import json
from exp.jatm_s34.annual_tail import load_annual_tail, tail_manifest_summary
load_annual_tail($YEAR)
print(json.dumps(tail_manifest_summary($YEAR), default=str, sort_keys=True))
" 2>>"$LOG")
  if [ -n "$V" ]; then
    echo "TAIL_${YEAR}_VERIFY: $V" >> "$LOG"
    sha256sum "$TAIL" > "$TASKDIR/output_sha256.txt"
    echo PASS > "$TASKDIR/status"
    echo "TAIL_${YEAR}_BUILD_PASS" >> "$LOG"
  else
    echo FAILED_VERIFY > "$TASKDIR/status"
  fi
else
  echo "TAIL_${YEAR}_BUILD_FAIL rc=$rc" >> "$LOG"
  echo "FAILED_rc=$rc" > "$TASKDIR/status"
fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
