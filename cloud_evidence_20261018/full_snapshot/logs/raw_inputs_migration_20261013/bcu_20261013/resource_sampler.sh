#!/usr/bin/env bash
# Resource sampler: every 10 minutes, append utilization to resource.log
# (Task 6 requirement).  Idempotent: only one instance keeps running (lock).
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
if [ -f "$B/sampler.lock" ] && kill -0 "$(cat "$B/sampler.lock")" 2>/dev/null; then
  echo "sampler already running"; exit 0
fi
echo $$ > "$B/sampler.lock"
while :; do
  {
    echo "=== $(date -u +%FT%TZ) ==="
    echo "loadavg: $(cat /proc/loadavg)"
    free -m | awk 'NR<=2'
    df -h /data | tail -1
    total_rss=0
    n=0
    for py in $(pgrep -f "build_year_references" 2>/dev/null); do
      rss=$(awk '/VmRSS/{print $2}' "/proc/$py/status" 2>/dev/null || echo 0)
      total_rss=$((total_rss + rss))
      n=$((n + 1))
      echo "  py=$py rss_mib=$((rss / 1024)) etime=$(ps -o etime= -p "$py" 2>/dev/null | tr -d ' ')"
    done
    echo "  build_year_procs=$n total_rss_gib=$(awk "BEGIN{printf \"%.1f\", $total_rss/1048576}")"
  } >> "$B/resource.log"
  sleep 600
done
