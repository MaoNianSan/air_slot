#!/usr/bin/env bash
# Calibration chain watcher (R7): auto-advances E1_c64 -> E2E3_c64 -> E4_n256
# strictly in order; stops on failure and reports which stage blocked.
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
cd "$B"
if [ -f calib_chain.lock ] && kill -0 "$(cat calib_chain.lock)" 2>/dev/null; then
  echo "already running"; exit 0
fi
echo $$ > calib_chain.lock
echo "[$(date -u +%FT%TZ)] calib chain watcher start pid=$$" >> calib_chain.log
launch() {
  local tag=$1 script=$2
  mkdir -p "$B/tasks/$tag"
  [ -f "$B/tasks/$tag/started" ] && return 0
  touch "$B/tasks/$tag/started"
  nohup bash "$B/pilot_runner.sh" "$tag" "$B/$script" >"$B/tasks/$tag/launch.out" 2>&1 &
  echo "[$(date -u +%FT%TZ)] launched $tag ($script)" >> calib_chain.log
}
wait_pass() {
  local tag=$1
  while :; do
    st=$(cat "$B/tasks/$tag/status" 2>/dev/null || echo running)
    case "$st" in
      PASS) return 0 ;;
      FAILED*|BLOCKED*) echo "[$(date -u +%FT%TZ)] $tag $st -> chain halted" >> calib_chain.log; exit 2 ;;
    esac
    sleep 30
  done
}
wait_pass calib_e1_c64
launch calib_e2e3_c64 calib_e2e3.py
wait_pass calib_e2e3_c64
launch calib_e4_n256 calib_e4.py
wait_pass calib_e4_n256
echo "[$(date -u +%FT%TZ)] calib chain complete" >> calib_chain.log
touch "$B/calib_chain_done"
