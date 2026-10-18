# -*- coding: utf-8 -*-
"""Gate-level provenance recorder for the M5-b autonomous run.

For every gate it appends one record to GATE_PROVENANCE.jsonl containing:
  1. the code version actually used (git head/branch + script hashes);
  2. protocol hash, pilot years, N grid, bootstrap contract and seeds;
  3. input artifact hashes and output artifact hashes;
  4. the state/status_detail/next_action observed for the gate, including any
     state migration that reopened it.

Idempotent: a gate is skipped when a record with the same content signature
already exists.  Files larger than HASH_LIMIT are fingerprinted by size +
sampled sha256 (clearly labelled), never silently skipped.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import consequence_stability_metrics as m5b  # noqa: E402

STUDY = m5b.STUDY_ROOT
LEDGER = STUDY / "GATE_PROVENANCE.jsonl"
STATE_FILE = STUDY / "AUTORUN_STATE.json"
HASH_LIMIT = 64 * 1024 * 1024
SAMPLE_BYTES = 1024 * 1024

GATES: dict[str, dict[str, list[str]]] = {
    "REUSE_ARTIFACT_AUDIT": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl",
            "data2/reports/cohort_size_stability/2019/HASH_RANKED_POOL_SUMMARY.json"],
        "outputs": [
            "data2/reports/cohort_size_stability/PRE_STATE_MATERIALIZATION_AUDIT_V2.json",
            "data2/reports/cohort_size_stability/PRE_STATE_MATERIALIZATION_AUDIT_V2.md"]},
    "PROTOCOL_GATE": {
        "inputs": [
            "data2/reports/cohort_size_stability/CONSEQUENCE_STABILITY_PROTOCOL_V1.json"],
        "outputs": [
            "data2/reports/cohort_size_stability/CONSEQUENCE_STABILITY_PROTOCOL_V2.json"]},
    "DETERMINISM_SENTINEL": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl",
            "artifacts/models/pre/PRE_MULTIYEAR_V1/2019/DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json",
            "artifacts/models/pre/PRE_MULTIYEAR_V1/2019/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json"],
        "outputs": [
            "data2/reports/cohort_size_stability/M1_DETERMINISM_SENTINEL.json",
            "data2/reports/cohort_size_stability/2019/sentinel_N128_r1/N128/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/sentinel_N128_r2/N128/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/sentinel_N4096_r1/N4096/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/sentinel_N4096_r2/N4096/M1_N_HASHES.json"]},
    "M2_REFERENCE_GATE": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl"],
        "outputs": [
            "artifacts/models/pre/PRE_MULTIYEAR_V1/2019/M2_REFERENCES/M2_REFERENCE_BUNDLE_MANIFEST.json",
            "artifacts/models/pre/PRE_MULTIYEAR_V1/2020/M2_REFERENCES/M2_REFERENCE_BUNDLE_MANIFEST.json",
            "data2/reports/cohort_size_stability/2019/M2_TRAIN_HEADROOM_SUMMARY.json",
            "data2/reports/cohort_size_stability/2020/M2_TRAIN_HEADROOM_SUMMARY.json"]},
    "LADDER_PROBE": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl"],
        "outputs": [
            "data2/reports/cohort_size_stability/LADDER_PROBE_2019.json",
            "data2/reports/cohort_size_stability/LADDER_PROBE_2020.json"]},
    "DETERMINISM_FLOOR_QUANTIFICATION": {
        "inputs": [
            "data2/reports/cohort_size_stability/M1_DETERMINISM_SENTINEL.json",
            "data2/reports/cohort_size_stability/2019/M2_TRAIN_HEADROOM_SUMMARY.json",
            "data2/reports/cohort_size_stability/2019/passes/floorN128_r1/PASS_MANIFEST.json",
            "data2/reports/cohort_size_stability/2019/passes/floorN128_r2/PASS_MANIFEST.json",
            "data2/reports/cohort_size_stability/2019/passes/floorN4096_r1/PASS_MANIFEST.json",
            "data2/reports/cohort_size_stability/2019/passes/floorN4096_r2/PASS_MANIFEST.json"],
        "outputs": [
            "data2/reports/cohort_size_stability/M5B_FLOOR_QUANTIFICATION.json"]},
    "EVAL_SMOKE_GATE": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/sentinel_N128_r1/N128/M1_N_HASHES.json"],
        "outputs": ["data2/reports/cohort_size_stability/M5B_SMOKE.json"]},
    "FIT_SIZE_STABILITY": {
        "inputs": [
            "data2/reports/cohort_size_stability/2019/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl"],
        "outputs": [
            "data2/reports/cohort_size_stability/2019/N128/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/N256/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/N512/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/N1024/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/N2048/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2019/N4096/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N128/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N256/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N512/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N1024/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N2048/M1_N_HASHES.json",
            "data2/reports/cohort_size_stability/2020/N4096/M1_N_HASHES.json"]},
    "EVAL_SIZE_STABILITY": {
        "inputs": [
            "data2/reports/cohort_size_stability/M5B_FLOOR_QUANTIFICATION.json"],
        "outputs": ["data2/reports/cohort_size_stability/EVAL_SUMMARY.json"]},
}


def fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"path": str(path.relative_to(REPO)), "state": "MISSING"}
    size = path.stat().st_size
    if size <= HASH_LIMIT:
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        return {"path": str(path.relative_to(REPO)), "state": "OK",
                "bytes": size, "sha256": digest}
    with path.open("rb") as handle:
        head = handle.read(SAMPLE_BYTES)
    sampled = "sha256:" + hashlib.sha256(head).hexdigest()
    return {"path": str(path.relative_to(REPO)), "state": "OK",
            "bytes": size, "sampled_sha256_first_1MiB": sampled,
            "fingerprint_scope": "SAMPLED_LARGE_FILE"}


def _state_payload() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def state_snapshot() -> dict:
    payload = _state_payload()
    detail = payload.get("status_detail")
    return {"status": payload.get("status"),
            "failed_state": payload.get("failed_state"),
            "status_detail": (str(detail)[:400] if detail else None),
            "next_action": payload.get("next_action"),
            "completed_states": payload.get("completed_states")}


def protocol_block() -> dict:
    protocol = json.loads((STUDY / m5b.V2_PROTOCOL_NAME).read_text(encoding="utf-8"))
    fit = protocol["stages"]["FIT_SIZE_STABILITY"]["bootstrap"]
    return {"protocol_hash": protocol["protocol_hash"],
            "schema_version": protocol["schema_version"],
            "pilot_years": protocol["pilot"]["years"],
            "n_grid": protocol["n_grid"],
            "bootstrap_replicates": fit["replicates"],
            "bootstrap_seed": fit["seed"],
            "train_seed": m5b.TRAIN_SEED,
            "floor_fraction": protocol["m1_determinism_sentinel"]["floor_rule"]["floor_fraction"]}


def code_block() -> dict:
    provenance = m5b.git_provenance()
    return {"git_head": provenance["git_head"],
            "git_branch": provenance["git_branch"],
            "source_script_hashes": m5b.source_script_hashes(),
            "recorded_by": "data2/scripts/record_gate_provenance.py"}


def existing_signatures() -> set:
    if not LEDGER.is_file():
        return set()
    signatures = set()
    with LEDGER.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            signatures.add(record.get("signature"))
    return signatures


def record(gate: str, *, force: bool = False) -> dict | None:
    spec = GATES[gate]
    inputs = [fingerprint(REPO / rel) for rel in spec["inputs"]]
    outputs = [fingerprint(REPO / rel) for rel in spec["outputs"]]
    ready = all(item["state"] == "OK" for item in outputs)
    if not ready and not force:
        # a gate is recorded only once its outputs exist; partial states are
        # reported on stdout, never appended as if they were gate records
        missing = [item["path"] for item in outputs if item["state"] != "OK"]
        print(f"skip {gate}: not complete ({len(missing)} outputs missing)")
        return None
    signature = m5b.sha256_json({"gate": gate, "outputs": outputs})
    known = existing_signatures()
    if not force and signature in known:
        print(f"skip {gate}: identical record already present")
        return None
    state = _state_payload()
    migrations = [migration for migration in state.get("state_migrations", [])
                  if gate in migration.get("reopened_states", [])]
    payload = {
        "gate": gate,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "completeness": "COMPLETE" if ready else "OUTPUTS_MISSING",
        "code": code_block(),
        "protocol": protocol_block(),
        "inputs": inputs,
        "outputs": outputs,
        "state_after_gate": state_snapshot(),
        "state_migrations_reopening_this_gate": migrations,
        "supersedes_quarantined": [migration.get("quarantined", [])
                                   for migration in migrations],
        "signature": signature,
    }
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    print(f"recorded {gate}: {payload['completeness']}")
    return payload


def main() -> int:
    gates = sys.argv[1:] or list(GATES)
    for gate in gates:
        if gate not in GATES:
            print(f"unknown gate: {gate}")
            continue
        try:
            record(gate)
        except FileNotFoundError as error:
            print(f"skip {gate}: prerequisite missing ({error})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
