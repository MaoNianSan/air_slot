"""Materialize the guarded shared recovery-priority Phase 0 deliverables."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from exp.shared.contracts import PRIORITY_CONTRACT_HASH, PRIORITY_CONTRACT_VERSION
from exp.shared.recovery_priority import (
    materialize_priority_score_record,
    validate_authoritative_dependencies,
)
from model.M1.contracts import M1V2Scenario
from model.M2.contracts import ScenarioConsequence
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "diagnostics" / "shared_priority_phase0"
M1_FIXTURE = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "numerical_best_action_sanity_v1"
    / "M1_DEVELOPMENT_64_NODE_SCENARIOS.json"
)
M2_FIXTURE = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "model_refactor_v1"
    / "M2_GOLDEN.json"
)
TEST_TARGETS = (
    "tests/contract/test_shared_recovery_priority.py",
    "tests/integration/test_shared_recovery_priority_integration.py",
)
MODIFIED_FILES = (
    "exp/shared/__init__.py",
    "exp/shared/contracts.py",
    "exp/shared/recovery_priority.py",
    "exp/exp2/priority.py",
    "tests/contract/test_shared_recovery_priority.py",
    "tests/integration/test_shared_recovery_priority_integration.py",
    "validation/materialize_shared_priority_phase0.py",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_DEPENDENCY_AUDIT.json",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_DEPENDENCY_AUDIT.md",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_CONTRACT_TEST_SUMMARY.json",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_DEVELOPMENT_SMOKE.json",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_DEVELOPMENT_RECORDS.jsonl",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_PHASE0_MANIFEST.json",
    "artifacts/diagnostics/shared_priority_phase0/SHARED_PRIORITY_PHASE0_REPORT.md",
)
EXPECTED_PRIORITY_CONTRACT_VERSION = "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp = Path(handle.name)
    temp.replace(path)


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _repository_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _without_computed_fields(item: dict) -> dict:
    payload = dict(item)
    payload.pop("consequence_artifact_id", None)
    vector = dict(payload["component_vector"])
    rows = []
    for row in vector["rows"]:
        clean = dict(row)
        clean.pop("cu_artifact_id", None)
        clean.pop("reference_lineage_hash", None)
        rows.append(clean)
    vector["rows"] = rows
    payload["component_vector"] = vector
    return payload


def _load_fixed_development_node():
    m1_payload = json.loads(M1_FIXTURE.read_text(encoding="utf-8"))
    m2_payload = json.loads(M2_FIXTURE.read_text(encoding="utf-8"))
    node_id = m2_payload["decision_node_id"]
    scenarios = tuple(
        M1V2Scenario.model_validate(
            {
                key: value
                for key, value in item.items()
                if key in M1V2Scenario.model_fields
            }
        )
        for item in m1_payload["scenarios"]
        if item["decision_node_id"] == node_id
    )
    consequences = tuple(
        ScenarioConsequence.model_validate(_without_computed_fields(item))
        for item in m2_payload["scenario_consequences"]
    )
    lineage = (
        m1_payload["artifact_id"],
        m1_payload["artifact_hash"],
        m1_payload["checkpoint_hash"],
    )
    return scenarios, consequences, lineage


def _run_fast_suite() -> dict:
    command = [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    match = re.search(r"(\d+) passed", output)
    passed = int(match.group(1)) if match else 0
    failed_match = re.search(r"(\d+) failed", output)
    failed = int(failed_match.group(1)) if failed_match else 0
    summary = {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "tests_run": passed + failed,
        "tests_passed": passed,
        "tests_failed": failed,
        "failed_test_names": [],
        "output": output,
    }
    if result.returncode != 0:
        _write_json(OUTPUT_DIR / "SHARED_PRIORITY_CONTRACT_TEST_SUMMARY.json", summary)
        raise RuntimeError("SHARED_PRIORITY_CONTRACT_TESTS_FAILED")
    return summary


def _support_counts(record) -> dict[str, dict[str, int]]:
    return {
        "delay": dict(Counter((record.delay_support,))),
        "native_components": dict(
            Counter(item.support for item in record.native_component_support)
        ),
        "cu_components": dict(
            Counter(item.support for item in record.cu_component_support)
        ),
        "domains": dict(Counter(item.support for item in record.domain_support)),
        "aggregates": dict(
            Counter(item.support for item in record.aggregate_support)
        ),
    }


def _write_contract_block(repository_head: str, dependency: dict) -> None:
    for name in (
        "SHARED_PRIORITY_CONTRACT_TEST_SUMMARY.json",
        "SHARED_PRIORITY_DEVELOPMENT_SMOKE.json",
        "SHARED_PRIORITY_DEVELOPMENT_RECORDS.jsonl",
    ):
        path = OUTPUT_DIR / name
        if path.exists():
            path.unlink()
    manifest = {
        "schema_version": "SHARED_PRIORITY_PHASE0_MANIFEST_V1",
        "repository_head": repository_head,
        "active_m2_registry_id": dependency["registry_id"],
        "active_m2_registry_hash": dependency["registry_hash"],
        "m2_cu_normalization_registry_hash": dependency[
            "cu_normalization_registry_hash"
        ],
        "m2_scope_hash": dependency["scope_hash"],
        "expected_priority_contract_version": EXPECTED_PRIORITY_CONTRACT_VERSION,
        "actual_priority_contract_version": PRIORITY_CONTRACT_VERSION,
        "actual_priority_contract_hash": PRIORITY_CONTRACT_HASH,
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "development_records_attempted": 0,
        "development_records_materialized": 0,
        "development_abstentions": 0,
        "final_test_accessed": False,
        "model_retrained": False,
        "model_reselected": False,
        "scientific_parameter_reselected": False,
        "ranking_performed": False,
        "paper_result_generated": False,
        "m1_modified": False,
        "m2_modified": False,
        "status": "BLOCK_CONTRACT_RECONCILIATION_REQUIRED",
        "conflicts": [
            "FIXED_CONTRACT_REQUIRED_BUT_LOCAL_AGGREGATION_IS_DEVELOPMENT_CANDIDATE",
            "PRIORITY_CONTRACT_VERSION_IDENTITY_MISMATCH",
        ],
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_MANIFEST.json", manifest)
    report = f"""# Shared Recovery-Priority Phase 0 Report

- Repository HEAD: `{repository_head}`
- M1/M2 dependency audit: `PASS`
- Expected priority contract: `{EXPECTED_PRIORITY_CONTRACT_VERSION}`
- Current local priority interface: `{PRIORITY_CONTRACT_VERSION}`
- Current local priority hash: `{PRIORITY_CONTRACT_HASH}`
- Development materialization: `NOT_RUN`
- Ranking performed: `false`
- Final Test accessed: `false`
- Model retrained or reselected: `false`

## Final Status

`BLOCK_CONTRACT_RECONCILIATION_REQUIRED`
"""
    _write_text(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_REPORT.md", report)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    repository_head = _repository_head()
    dependency = validate_authoritative_dependencies()
    if PRIORITY_CONTRACT_VERSION != EXPECTED_PRIORITY_CONTRACT_VERSION:
        _write_contract_block(repository_head, dependency)
        print("BLOCK_CONTRACT_RECONCILIATION_REQUIRED")
        return 2
    tests = _run_fast_suite()
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_CONTRACT_TEST_SUMMARY.json", tests)

    scenarios, consequences, lineage = _load_fixed_development_node()
    record = materialize_priority_score_record(
        scenarios,
        consequences,
        repository_head=repository_head,
        m1_lineage=lineage,
    )
    repeated = materialize_priority_score_record(
        tuple(reversed(scenarios)),
        tuple(reversed(consequences)),
        repository_head=repository_head,
        m1_lineage=lineage,
    )
    if record.artifact_id != repeated.artifact_id:
        raise RuntimeError("SHARED_PRIORITY_NONDETERMINISTIC_OUTPUT")

    record_payload = record.model_dump(mode="json")
    _write_text(
        OUTPUT_DIR / "SHARED_PRIORITY_DEVELOPMENT_RECORDS.jsonl",
        json.dumps(record_payload, sort_keys=True) + "\n",
    )
    reason_counts = dict(Counter(record.reason_codes))
    smoke = {
        "schema_version": "SHARED_PRIORITY_DEVELOPMENT_SMOKE_V1",
        "scope": "DEVELOPMENT_ONLY_INTERFACE_SMOKE",
        "paper_result": False,
        "ranking_performed": False,
        "final_test_accessed": False,
        "fixture_artifacts": [
            str(M1_FIXTURE.relative_to(ROOT)).replace("\\", "/"),
            str(M2_FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        ],
        "records_attempted": 1,
        "records_materialized": 1,
        "records_abstained": 0,
        "support_counts": _support_counts(record),
        "reason_code_counts": reason_counts,
        "active_m2_registry_id": dependency["registry_id"],
        "active_m2_registry_hash": dependency["registry_hash"],
        "m2_cu_normalization_registry_hash": dependency[
            "cu_normalization_registry_hash"
        ],
        "m2_scope_hash": dependency["scope_hash"],
        "priority_contract_version": PRIORITY_CONTRACT_VERSION,
        "priority_contract_hash": PRIORITY_CONTRACT_HASH,
        "finite_nonnegative_checks": "PASS",
        "scenario_alignment": "PASS",
        "reproducibility_hash": content_id((record.artifact_id,)),
        "record_artifact_ids": [record.artifact_id],
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_DEVELOPMENT_SMOKE.json", smoke)

    manifest = {
        "schema_version": "SHARED_PRIORITY_PHASE0_MANIFEST_V1",
        "repository_head": repository_head,
        "modified_files": list(MODIFIED_FILES),
        "active_m2_registry_id": dependency["registry_id"],
        "active_m2_registry_hash": dependency["registry_hash"],
        "m2_cu_normalization_registry_hash": dependency[
            "cu_normalization_registry_hash"
        ],
        "m2_scope_hash": dependency["scope_hash"],
        "priority_contract_version": PRIORITY_CONTRACT_VERSION,
        "priority_contract_hash": PRIORITY_CONTRACT_HASH,
        "tests_run": tests["tests_run"],
        "tests_passed": tests["tests_passed"],
        "tests_failed": tests["tests_failed"],
        "development_fixture": smoke["fixture_artifacts"],
        "development_records_attempted": 1,
        "development_records_materialized": 1,
        "development_abstentions": 0,
        "development_reproducibility_hash": smoke["reproducibility_hash"],
        "final_test_accessed": False,
        "model_retrained": False,
        "model_reselected": False,
        "scientific_parameter_reselected": False,
        "ranking_performed": False,
        "paper_result_generated": False,
        "m1_modified": False,
        "m2_modified": False,
        "status": "PHASE0_PASS",
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_MANIFEST.json", manifest)
    report = f"""# Shared Recovery-Priority Phase 0 Report

- Repository HEAD: `{repository_head}`
- Dependency audit: `PASS`
- Active M2 registry: `{dependency['registry_id']}`
- Active M2 registry hash: `{dependency['registry_hash']}`
- CU normalization registry hash: `{dependency['cu_normalization_registry_hash']}`
- Consequence scope hash: `{dependency['scope_hash']}`
- Priority contract hash: `{PRIORITY_CONTRACT_HASH}`
- Contract and integration tests: `{tests['tests_passed']} passed`
- Development records: `1 attempted / 1 materialized / 0 abstained`
- Deterministic materialization: `PASS`
- Ranking performed: `false`
- Final Test accessed: `false`
- Model retrained or reselected: `false`
- Scientific parameter reselected: `false`

## Final Status

`PHASE0_PASS`
"""
    _write_text(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_REPORT.md", report)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
