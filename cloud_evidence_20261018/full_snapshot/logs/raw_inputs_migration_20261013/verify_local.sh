#!/usr/bin/env bash
# Raw-input migration 2026-10-13: local SHA-256 verification of the 18 target
# files against the frozen per-year data2 manifests. Read-only.
set -uo pipefail
ROOT=/d/research/air_slot/code/explore
WORK=/d/research/air_slot/cloud_transfer_20261013/raw_inputs_20261013
OUT="$WORK/local_verify.txt"
: > "$OUT"
pass=0; fail=0
while IFS=, read -r hash rel; do
  f="$ROOT/data2/$rel"
  if [ ! -f "$f" ]; then
    echo "LOCAL_MISSING,$rel" >> "$OUT"; fail=$((fail+1)); continue
  fi
  actual=$(sha256sum "$f" | cut -d' ' -f1 | tr 'a-f' 'A-F')
  sz=$(stat -c %s "$f")
  if [ "$actual" = "$hash" ]; then
    echo "LOCAL_OK,$rel,$sz,$actual" >> "$OUT"; pass=$((pass+1))
  else
    echo "LOCAL_MISMATCH,$rel,$sz,expected=$hash,actual=$actual" >> "$OUT"; fail=$((fail+1))
  fi
done < "$WORK/expected_hashes.txt"
echo "SUMMARY pass=$pass fail=$fail" >> "$OUT"
