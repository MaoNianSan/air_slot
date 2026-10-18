#!/usr/bin/env bash
# Development smoke runner (round 4): bounded annual Development for 2019.
# Development-only; writes DEVELOPMENT_SMOKE_VERIFICATION.json; refuses to
# overwrite a completed smoke manifest.
set -uo pipefail
TAG=dev_smoke_2019
B=/data/airslot/logs/raw_inputs_migration_20261013/bcu_20261013
TASKDIR=$B/tasks/$TAG
mkdir -p "$TASKDIR"
LOG=$TASKDIR/log
cd /data/airslot/worktree
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
# Provenance adapter (transparent, no worktree change): the cloud tree carries
# no .git (tarball deployment); the E1/E2E3 runners record `git rev-parse HEAD`.
# A metadata-only git dir declares the TRUE snapshot head from CODE_SNAPSHOT.json
# (583f2c12...) so the recorded revision is the correct code identity; the
# authorized patch chain is recorded separately in this task's meta + verification.
export GIT_DIR=/data/airslot/smoke_gitmeta/repo/.git
PYTHON=/data/airslot/source/.venv/bin/python
SMOKE_DIR=artifacts/experiment/jatm_s34/development_smoke_20261013_2019

echo $$ > "$TASKDIR/pid"
date -u +"started_at=%FT%TZ" >> "$TASKDIR/meta"
echo "code_snapshot=583f2c12 + patch_8cc7a1b7 (d1c72a7) + patch_1d3ba5d3 (ffa7487)" >> "$TASKDIR/meta"
sha256sum "$B/run_dev_smoke.py" \
  artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1/2019/M2_REFERENCES/M2_REFERENCE_BUNDLE_MANIFEST.json \
  artifacts/models/m1/YEAR_2019/M1_HISTORY_PRIMARY_MANIFEST.json \
  artifacts/models/m1/YEAR_2019/M1_CURRENT_COMPARATOR_MANIFEST.json \
  artifacts/models/pre/PRE_MULTIYEAR_V1/2019/PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json \
  > "$TASKDIR/input_sha256.txt"

if [ -f "$SMOKE_DIR/ANNUAL_DEVELOPMENT_MANIFEST.json" ]; then
  echo "BLOCKED_SMOKE_ALREADY_COMPLETE $SMOKE_DIR" >> "$LOG"
  echo BLOCKED_SMOKE_ALREADY_COMPLETE > "$TASKDIR/status"
  exit 2
fi

echo "[$(date -u +%FT%TZ)] START $TAG (bounded annual Development, 2019, DEVELOPMENT-ONLY)" >> "$LOG"
/usr/bin/time -v -o "$TASKDIR/time_v.txt" "$PYTHON" "$B/run_dev_smoke.py" >> "$LOG" 2>&1
rc=$?
echo "$rc" > "$TASKDIR/exitcode"
if [ "$rc" -eq 0 ]; then
  "$PYTHON" - <<PYEOF >> "$LOG" 2>&1
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
out = Path("$SMOKE_DIR/ANNUAL_DEVELOPMENT_MANIFEST.json")
payload = json.loads(out.read_text(encoding="utf-8"))
h = hashlib.sha256(out.read_bytes()).hexdigest()
verification = {
    "schema_version": "AIRSLOT_DEVELOPMENT_SMOKE_VERIFICATION_V1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "year": 2019,
    "scope": "DEVELOPMENT_ONLY (bounded annual Development chain; E1-E4 NOT started; Final-Test sealed)",
    "params": {"n": 4096, "chunk_size": 4, "node_limit": 8, "bootstrap_replicates": 5,
               "entry": "exp.jatm_s34.annual_development.run_year_bounded"},
    "manifest_sha256": h,
    "status": payload.get("status"),
    "scientific_status": payload.get("scientific_status"),
    "final_test_access_count": payload.get("final_test_access_count"),
    "input_contract_status": payload.get("input_contract", {}).get("status"),
    "smoke_result": "PASS" if payload.get("status") == "DEVELOPMENT_COMPLETE" else "FAIL",
}
Path("$B/DEVELOPMENT_SMOKE_VERIFICATION.json").write_text(
    json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("DEVELOPMENT_SMOKE_VERIFICATION written:", verification["smoke_result"])
PYEOF
  echo PASS > "$TASKDIR/status"
  echo "DEV_SMOKE_PASS" >> "$LOG"
else
  echo "DEV_SMOKE_FAIL rc=$rc" >> "$LOG"
  echo "FAILED_rc=$rc" > "$TASKDIR/status"
fi
echo "finished_at=$(date -u +%FT%TZ)" >> "$TASKDIR/meta"
exit "$rc"
