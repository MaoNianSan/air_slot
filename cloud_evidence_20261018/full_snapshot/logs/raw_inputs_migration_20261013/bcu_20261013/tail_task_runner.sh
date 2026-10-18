#!/usr/bin/env bash
# 2018 Annual Tail Reference supplemental build (authorized by
# ANNUAL_TAIL_USER_DECISION.json, status USER_APPROVED, years 2017-2022).
# Tail-only: does NOT invoke cloud_worker/shared_run execution stages.
set -uo pipefail
TAG=tail_2018
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHON=/data/airslot/source/.venv/bin/python
DECISION=deploy/jatm_cloud/scientific_decisions/ANNUAL_TAIL_USER_DECISION.json
TAIL=artifacts/models/m1/YEAR_2018/TAIL_REFERENCE_V1/MANIFEST.json

echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "code_snapshot=583f2c12 + patch_8cc7a1b7 (local commit d1c72a7)" >> "$TASKDIR/meta"
sha256sum "$DECISION" \
  data2/reports/cohort_size_stability/2018/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl \
  artifacts/models/pre/PRE_MULTIYEAR_V1/2018/DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json \
  artifacts/models/pre/PRE_MULTIYEAR_V1/2018/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json \
  > "$TASKDIR/input_sha256.txt"

if [ -f "$TAIL" ]; then
  echo "BLOCKED_TAIL_EXISTS $TAIL" >> "$TASKDIR/log"
  echo BLOCKED_TAIL_EXISTS > "$TASKDIR/status"
  exit 2
fi

echo "[$(date -u +%FT%TZ)] START $TAG (tail-only build)" >> "$TASKDIR/log"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" -m exp.jatm_s34.build_annual_tail \
  --year 2018 --decision "$DECISION" >> "$TASKDIR/log" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ]; then
  V=$("$PYTHON" -c "import json; from exp.jatm_s34.annual_tail import load_annual_tail, tail_manifest_summary; load_annual_tail(2018); print(json.dumps(tail_manifest_summary(2018), default=str, sort_keys=True))" 2>>"$TASKDIR/log")
  if [ -n "$V" ]; then
    echo "TAIL_2018_VERIFY: $V" >> "$TASKDIR/log"
    sha256sum "$TAIL" > "$TASKDIR/output_sha256.txt"
    echo PASS > "$TASKDIR/status"
    echo "TAIL_2018_BUILD_PASS" >> "$TASKDIR/log"
  else
    echo FAILED_VERIFY > "$TASKDIR/status"
  fi
else
  echo "TAIL_2018_BUILD_FAIL rc=$rc" >> "$TASKDIR/log"
  echo "FAILED_rc=$rc" > "$TASKDIR/status"
fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
