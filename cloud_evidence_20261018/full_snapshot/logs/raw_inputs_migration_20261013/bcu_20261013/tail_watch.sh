#!/usr/bin/env bash
# Tail auto-pipeline watcher (round 4): launches tail_<year> as soon as that
# year's M1 task records PASS (status file written by m1_task_runner after
# model_bindings validation). Idempotent; failures block only their own year.
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
cd "$B"
if [ -f tail_watch.lock ] && kill -0 "$(cat tail_watch.lock)" 2>/dev/null; then
  echo "already running"; exit 0
fi
echo $$ > tail_watch.lock
echo "[$(date -u +%FT%TZ)] tail watcher start pid=$$" >> tail_watch.log
WAIT_YEARS="2020 2021 2022"
while true; do
  pending=0
  for y in $WAIT_YEARS; do
    tdir="$B/tasks/tail_$y"
    if [ -f "$tdir/done" ] || [ -f "$tdir/started" ]; then continue; fi
    mst=$(cat "$B/tasks/m1_$y/status" 2>/dev/null || echo pending)
    case "$mst" in
      PASS)
        mkdir -p "$tdir"; touch "$tdir/started"
        nohup bash "$B/tail_task_runner_year.sh" "$y" >"$tdir/launch.out" 2>&1 &
        echo "[$(date -u +%FT%TZ)] launched tail_$y (m1 PASS)" >> tail_watch.log
        ;;
      FAILED*|BLOCKED*|UNKNOWN)
        echo "SKIPPED_M1_NOT_PASS:$mst" > "$tdir/status"
        touch "$tdir/done"
        echo "[$(date -u +%FT%TZ)] tail_$y SKIPPED ($mst)" >> tail_watch.log
        ;;
      *)
        pending=$((pending + 1))
        ;;
    esac
  done
  if [ "$pending" -eq 0 ]; then
    allset=1
    for y in $WAIT_YEARS; do
      [ -f "$B/tasks/tail_$y/done" ] || allset=0
    done
    if [ "$allset" -eq 1 ]; then
      echo "[$(date -u +%FT%TZ)] tail pipeline complete" >> tail_watch.log
      touch "$B/tail_watch_done"
      break
    fi
  fi
  sleep 45
done
