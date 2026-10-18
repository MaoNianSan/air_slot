#!/usr/bin/env bash
# Controlled-parallel dispatcher for B CU year-bundle tasks (2026-10-13).
# Reads queue.txt ("<tag> <year> <output_root_rel>" per line) and starts tasks
# not yet started while running < $(cat concurrency).  Rerun-safe: started
# tasks are never re-launched; finished tasks are finalized once.
set -uo pipefail
B=$(cd "$(dirname "$0")" && pwd)
if [ -f "$B/dispatcher.lock" ] && kill -0 "$(cat "$B/dispatcher.lock")" 2>/dev/null; then
  echo "dispatcher already running"; exit 0
fi
echo $$ > "$B/dispatcher.lock"
echo "[$(date -u +%FT%TZ)] dispatcher start pid=$$" >> "$B/dispatcher.log"
while true; do
  CONC=$(cat "$B/concurrency" 2>/dev/null || echo 2)
  # finalize finished tasks
  for td in "$B"/tasks/*/; do
    [ -d "$td" ] || continue
    tag=$(basename "$td")
    [ -f "$td/started" ] || continue
    [ -f "$td/done" ] && continue
    pid=$(cat "$td/pid" 2>/dev/null || true)
    if [ -z "$pid" ]; then
      started_epoch=$(stat -c %Y "$td/started" 2>/dev/null || echo 0)
      now_epoch=$(date +%s)
      if [ $((now_epoch - started_epoch)) -lt 120 ]; then continue; fi
      echo "VANISHED_NO_PID" > "$td/final_status"
      touch "$td/done"
      echo "[$(date -u +%FT%TZ)] $tag -> VANISHED_NO_PID" >> "$B/dispatcher.log"
      continue
    fi
    if kill -0 "$pid" 2>/dev/null; then continue; fi
    if [ -f "$td/exitcode" ]; then
      st=$(cat "$td/status" 2>/dev/null || echo UNKNOWN)
    else
      st="NO_EXITCODE_RECORDED"
    fi
    echo "$st" > "$td/final_status"
    touch "$td/done"
    echo "[$(date -u +%FT%TZ)] $tag -> $st" >> "$B/dispatcher.log"
  done
  running=0
  for td in "$B"/tasks/*/; do
    [ -f "$td/started" ] && [ ! -f "$td/done" ] && running=$((running+1))
  done
  while read -r tag year output; do
    [ -z "${tag:-}" ] && continue
    td="$B/tasks/$tag"
    mkdir -p "$td"
    [ -f "$td/started" ] && continue
    [ "$running" -ge "$CONC" ] && break
    touch "$td/started"
    nohup bash "$B/bcu_task_runner.sh" "$tag" "$year" "$output" >"$td/launch.out" 2>&1 &
    echo "[$(date -u +%FT%TZ)] started $tag year=$year (conc=$CONC)" >> "$B/dispatcher.log"
    running=$((running+1))
  done < "$B/queue.txt"
  total=0
  while read -r tag _rest; do [ -n "${tag:-}" ] && total=$((total+1)); done < "$B/queue.txt"
  finished=$(ls -d "$B"/tasks/*/done 2>/dev/null | wc -l)
  if [ "$finished" -ge "$total" ]; then
    echo "[$(date -u +%FT%TZ)] ALL_DONE ($finished/$total)" >> "$B/dispatcher.log"
    touch "$B/ALL_DONE"
    break
  fi
  sleep 20
done
