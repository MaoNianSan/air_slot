#!/usr/bin/env bash
# Annual M1 training task runner (round 4, 2026-10-13).
# Usage: m1_task_runner.sh <tag> <year>
# Records per task: started_at, code/input identity, PID, exit code, wall/CPU/
# peak RSS (/usr/bin/time -v), checkpoint+manifest hashes, model_bindings
# validation, PASS/FAILED/BLOCKED status. Refuses non-empty YEAR output dirs.
set -uo pipefail
TAG=$1; YEAR=$2
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
LOG=$TASKDIR/log
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHON=/data/airslot/source/.venv/bin/python
APPROVAL=/data/airslot/logs/raw_inputs_migration_20261013/M1_TRAINING_AUTHORIZATION_USER_APPROVED_20261013.json
YDIR="artifacts/models/m1/YEAR_$YEAR"

echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "code_snapshot=583f2c12 + patch_8cc7a1b7 (d1c72a7) + patch_1d3ba5d3 (ffa7487)" >> "$TASKDIR/meta"
echo "task=$TAG year=$YEAR approval=$APPROVAL" >> "$TASKDIR/meta"
sha256sum "$APPROVAL" \
  "data2/reports/cohort_size_stability/$YEAR/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl" \
  "artifacts/models/pre/PRE_MULTIYEAR_V1/$YEAR/DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json" \
  "artifacts/models/pre/PRE_MULTIYEAR_V1/$YEAR/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json" \
  exp/jatm_s34/annual_models.py exp/jatm_s34/cloud_train_models.py \
  > "$TASKDIR/input_sha256.txt"

if [ -d "$YDIR" ] && [ -n "$(find "$YDIR" -mindepth 1 -print -quit)" ]; then
  echo "BLOCKED_OUTPUT_EXISTS $YDIR" >> "$LOG"
  echo BLOCKED_OUTPUT_EXISTS > "$TASKDIR/status"
  exit 2
fi

echo "[$(date -u +%FT%TZ)] START $TAG year=$YEAR (M1 training, both roles)" >> "$LOG"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" -m exp.jatm_s34.cloud_train_models \
  --year "$YEAR" --approval "$APPROVAL" >> "$LOG" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ]; then
  V=$("$PYTHON" -c "
import json, sys
sys.path.insert(0, '/data/airslot/worktree')
from exp.jatm_s34.cloud_inputs import model_bindings
b = model_bindings($YEAR, root='/data/airslot/worktree')
print(json.dumps({k: {'checkpoint_hash': v['checkpoint_hash'], 'manifest_sha256': v['manifest_sha256']} for k, v in sorted(b.items())}, sort_keys=True))
" 2>>"$LOG")
  if [ -n "$V" ]; then
    echo "BINDINGS_OK $V" >> "$LOG"
    (cd "$YDIR" && sha256sum *.pt *_MANIFEST.json *RECEIPT.json 2>/dev/null) > "$TASKDIR/output_sha256.txt"
    echo PASS > "$TASKDIR/status"
    echo "M1_${YEAR}_TRAIN_PASS" >> "$LOG"
  else
    echo "M1_${YEAR}_BINDINGS_FAILED" >> "$LOG"
    echo FAILED_BINDINGS > "$TASKDIR/status"
  fi
else
  echo "M1_${YEAR}_TRAIN_FAIL rc=$rc" >> "$LOG"
  echo "FAILED_rc=$rc" > "$TASKDIR/status"
fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
