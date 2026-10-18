#!/usr/bin/env bash
# Raw-input migration 2026-10-13: upload driver (temp path -> verify -> atomic rename).
# Contract:
#   - existing file: verify SHA-256; identical => skip; mismatch => STOP and report.
#   - new file: upload to <targetdir>/.upload_tmp_<name>; verify byte size + SHA-256;
#     atomic mv within the same directory; up to 3 attempts; then STOP and report.
# Never touches: cloud_upload_package_20261013_v3/, incoming/, the 439-file manifest,
# existing verified files, or anything outside data2/raw/bts + the migration log dir.
set -uo pipefail
ROOT=/d/research/air_slot/code/explore
WORK=/d/research/air_slot/cloud_transfer_20261013/raw_inputs_20261013
KEY=$HOME/.ssh/airslot.pem
HOST=ubuntu@134.175.205.112
SROOT=/data/airslot/worktree/data2
SLOG=/data/airslot/logs/raw_inputs_migration_20261013
LOG="$WORK/upload_log.txt"
: > "$LOG"

SSH() { ssh -n -o BatchMode=yes -i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=6 "$HOST" "$@"; }
SCP() { scp -o BatchMode=yes -i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ServerAliveCountMax=6 "$@"; }

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] migration driver start" >> "$LOG"
SSH "mkdir -p $SLOG" || { echo "FATAL cannot create server log dir" >> "$LOG"; exit 9; }

stop_marker() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STOP: $*" >> "$LOG"
  echo "$*" > "$WORK/MIGRATION_STOPPED.txt"
  exit 8
}

while IFS=, read -r exp rel; do
  lf="$ROOT/data2/$rel"
  rdir="$SROOT/$(dirname "$rel")"
  rfinal="$SROOT/$rel"
  tmp="$rdir/.upload_tmp_$(basename "$rel")"
  lexp=$(echo "$exp" | tr 'A-F' 'a-f')

  if [ ! -f "$lf" ]; then stop_marker "LOCAL_FILE_MISSING: $rel"; fi

  SSH "mkdir -p '$rdir'" || stop_marker "REMOTE_MKDIR_FAILED: $rdir"

  if SSH "[ -e '$rfinal' ]"; then
    rh=$(SSH "sha256sum '$rfinal'" | cut -d' ' -f1)
    if [ "$rh" = "$lexp" ]; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SKIP_IDENTICAL $rel sha256=$rh" >> "$LOG"
      continue
    else
      stop_marker "EXISTING_FILE_HASH_CONFLICT: $rel expected=$lexp server=$rh"
    fi
  fi

  lsize=$(stat -c %s "$lf")
  ok=0
  for try in 1 2 3; do
    SSH "rm -f '$tmp'" || true
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] UPLOAD_TRY $rel attempt=$try bytes=$lsize" >> "$LOG"
    if SCP "$lf" "$HOST:$tmp" >> "$LOG" 2>&1; then
      rsize=$(SSH "stat -c %s '$tmp'" 2>/dev/null || echo ERR)
      rh=$(SSH "sha256sum '$tmp'" 2>/dev/null | cut -d' ' -f1)
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] VERIFY $rel local_bytes=$lsize server_bytes=$rsize server_sha256=$rh" >> "$LOG"
      if [ "$rsize" = "$lsize" ] && [ "$rh" = "$lexp" ]; then
        if SSH "mv '$tmp' '$rfinal'"; then
          echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] COMMIT $rel atomic_rename=ok" >> "$LOG"
          ok=1; break
        else
          echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] RENAME_FAIL $rel" >> "$LOG"
        fi
      fi
      SSH "rm -f '$tmp'" || true
    else
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SCP_FAIL $rel attempt=$try" >> "$LOG"
      SSH "rm -f '$tmp'" || true
    fi
    sleep 5
  done
  [ "$ok" = "1" ] || stop_marker "UPLOAD_UNVERIFIED_AFTER_3_ATTEMPTS: $rel"
done < "$WORK/expected_hashes.txt"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DRIVER_DONE all files committed or skipped" >> "$LOG"
