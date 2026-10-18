#!/usr/bin/env bash
# Resource sampler v2 (round 6): 10-minute cadence; captures loadavg, memory,
# disk, and the Air Slot process tree (RSS per live worker python).
set -uo pipefail
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
if [ -f "$B/sampler2.lock" ] && kill -0 "$(cat "$B/sampler2.lock")" 2>/dev/null; then
  echo "already running"; exit 0
fi
echo $$ > "$B/sampler2.lock"
while :; do
  {
    echo "=== $(date -u +%FT%TZ) ==="
    echo "loadavg: $(cat /proc/loadavg)"
    free -m | awk 'NR<=2'
    df -h /data | tail -1
    echo "process tree:"
    ps -eo pid,ppid,rss,pcpu,etime,args --sort=-rss \
      | grep -E "python|pilot_|run_e1|run_e2|e4_run|consequence_stability" \
      | grep -v grep | head -12 \
      | awk '{printf "  pid=%s ppid=%s rss_mib=%d cpu=%s etime=%s %s %s %s\n", $1, $2, $3/1024, $4, $5, $6, $7, $8}'
  } >> "$B/resource_pilot.log"
  sleep 600
done
