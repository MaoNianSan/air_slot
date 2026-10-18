#!/usr/bin/env bash
set -uo pipefail
TAG=$1; shift
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
LOG=$TASKDIR/log
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export GIT_DIR=/data/airslot/smoke_gitmeta/repo/.git
PYTHON=/data/airslot/source/.venv/bin/python
echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "authorization=bcu_20261013/EXPERIMENT_EXECUTION_AUTHORIZATION_PILOT_V1.json" >> "$TASKDIR/meta"
echo "[$(date -u +%FT%TZ)] START $TAG :: $*" >> "$LOG"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" "$@" >> "$LOG" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ]; then echo PASS > "$TASKDIR/status"; else echo "FAILED_rc=$rc" > "$TASKDIR/status"; fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
