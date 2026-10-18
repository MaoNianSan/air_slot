#!/usr/bin/env bash
# M1 training dispatcher (round 4). Queue: m1_queue.txt ("<tag> <year>").
# Starts queued years while running < $(cat m1_concurrency); idempotent via
# per-task started/done markers; never restarts finished tasks.
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
cd "$B"
if [ -f m1_dispatcher.lock ] && kill -0 "$(cat m1_dispatcher.lock)" 2>/dev/null; then
  echo "already running"; exit 0
fi
echo $$ > m1_dispatcher.lock
echo "[$(date -u +%FT%TZ)] m1 dispatcher start pid=$$" >> m1_dispatcher.log
while true; do
  CONC=$(cat "$B/m1_concurrency" 2>/dev/null || echo 2)
  # finalize finished queued tasks
  while read -r tag _year; do
    [ -z "${tag:-}" ] && continue
    td="$B/tasks/$tag"
    [ -f "$td/started" ] || continue
    [ -f "$td/done" ] && continue
    pid=$(cat "$td/pid" 2>/dev/null || true)
    if [ -z "$pid" ]; then
      se=$(stat -c %Y "$td/started" 2>/dev/null || echo 0); ne=$(date +%s)
      if [ $((ne - se)) -lt 120 ]; then continue; fi
      echo "VANISHED_NO_PID" > "$td/final_status"; touch "$td/done"
      echo "[$(date -u +%FT%TZ)] $tag -> VANISHED_NO_PID" >> m1_dispatcher.log
      continue
    fi
    if kill -0 "$pid" 2>/dev/null; then continue; fi
    if [ -f "$td/exitcode" ]; then
      st=$(cat "$td/status" 2>/dev/null || echo UNKNOWN)
    else
      st="NO_EXITCODE_RECORDED"
    fi
    echo "$st" > "$td/final_status"; touch "$td/done"
    echo "[$(date -u +%FT%TZ)] $tag -> $st" >> m1_dispatcher.log
  done < "$B/m1_queue.txt"
  running=0
  while read -r tag _year; do
    [ -z "${tag:-}" ] && continue
    td="$B/tasks/$tag"
    [ -f "$td/started" ] && [ ! -f "$td/done" ] && running=$((running + 1))
  done < "$B/m1_queue.txt"
  while read -r tag year; do
    [ -z "${tag:-}" ] && continue
    td="$B/tasks/$tag"
    mkdir -p "$td"
    [ -f "$td/started" ] && continue
    [ "$running" -ge "$CONC" ] && break
    touch "$td/started"
    nohup bash "$B/m1_task_runner.sh" "$tag" "$year" >"$td/launch.out" 2>&1 &
    echo "[$(date -u +%FT%TZ)] started $tag year=$year (conc=$CONC)" >> m1_dispatcher.log
    running=$((running + 1))
  done < "$B/m1_queue.txt"
  total=0; fin=0
  while read -r tag _year; do
    [ -z "${tag:-}" ] && continue
    total=$((total + 1))
    [ -f "$B/tasks/$tag/done" ] && fin=$((fin + 1))
  done < "$B/m1_queue.txt"
  if [ "$total" -gt 0 ] && [ "$fin" -ge "$total" ]; then
    echo "[$(date -u +%FT%TZ)] ALL_DONE ($fin/$total)" >> m1_dispatcher.log
    touch "$B/m1_all_done"
    break
  fi
  sleep 20
done
