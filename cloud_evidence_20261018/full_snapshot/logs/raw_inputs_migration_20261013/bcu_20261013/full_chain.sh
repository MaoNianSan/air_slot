#!/usr/bin/env bash
# Full-experiment chain (R8): Stage1 E4 (6 workers) -> Stage2 E2/E3 (3-concurrent) -> Stage3 E1 (3-concurrent).
# Single-driver; per-year isolation; failures stop only their own year; NO blind restarts.
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
cd "$B"
if [ -f full_chain.lock ] && kill -0 "$(cat full_chain.lock)" 2>/dev/null; then echo "already running"; exit 0; fi
echo $$ > full_chain.lock
LOG=$B/full_chain.log
echo "[$(date -u +%FT%TZ)] full chain start pid=$$" >> "$LOG"

launch() {
  local tag=$1 script=$2 year=$3 td="$B/tasks/$1"
  mkdir -p "$td"
  [ -f "$td/started" ] && return 0
  touch "$td/started"
  nohup bash "$B/pilot_runner.sh" "$tag" "$B/$script" "$year" >"$td/launch.out" 2>&1 &
  echo "[$(date -u +%FT%TZ)] launched $tag $script $year" >> "$LOG"
}
finalize() {
  local tag=$1 td="$B/tasks/$1"
  [ -f "$td/done" ] && { cat "$td/status" 2>/dev/null || echo UNKNOWN; return; }
  [ -f "$td/started" ] || { echo notstarted; return; }
  local st; st=$(cat "$td/status" 2>/dev/null || echo running)
  case "$st" in
    PASS|FAILED*|BLOCKED*) touch "$td/done"; echo "[$(date -u +%FT%TZ)] $tag -> $st" >> "$LOG"; echo "$st"; return ;;
  esac
  local pid; pid=$(cat "$td/pid" 2>/dev/null || true)
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    echo "FAILED_NO_STATUS" > "$td/status"; touch "$td/done"
    echo "[$(date -u +%FT%TZ)] $tag -> FAILED_NO_STATUS (process vanished)" >> "$LOG"; echo FAILED_NO_STATUS; return
  fi
  echo running
}
stage_worker() { # stage prefix script concurrency
  local prefix=$1 script=$2 conc=$3
  while :; do
    local running=0 fin=0 s y
    for y in 2017 2018 2019 2020 2021 2022; do
      s=$(finalize "${prefix}_$y")
      case "$s" in running) running=$((running+1));; notstarted) :;; *) fin=$((fin+1));; esac
    done
    [ "$fin" -ge 6 ] && break
    for y in 2017 2018 2019 2020 2021 2022; do
      [ "$running" -ge "$conc" ] && break
      [ -f "$B/tasks/${prefix}_$y/started" ] && continue
      launch "${prefix}_$y" "$script" "$y"; running=$((running+1))
    done
    sleep 60
  done
}

for y in 2017 2018 2019 2020 2021 2022; do launch "e4_full_$y" full_e4.py "$y"; done
while :; do
  running=0
  for y in 2017 2018 2019 2020 2021 2022; do [ "$(finalize e4_full_$y)" = "running" ] && running=$((running+1)); done
  [ "$running" -eq 0 ] && break
  sleep 60
done
echo "[$(date -u +%FT%TZ)] stage1 complete" >> "$LOG"

stage_worker e2e3_full full_e2e3.py 3
echo "[$(date -u +%FT%TZ)] stage2 complete" >> "$LOG"
stage_worker e1_full full_e1.py 3
echo "[$(date -u +%FT%TZ)] stage3 complete" >> "$LOG"

[ "$(cat "$B/tasks/full_smoke.marker" 2>/dev/null)" = "" ] && :
echo "[$(date -u +%FT%TZ)] full chain complete" >> "$LOG"
touch "$B/full_chain_done"
