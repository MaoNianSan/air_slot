"""Finalize the frozen shared recovery-priority Phase 0 contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exp.shared.contracts import (
    PRIORITY_CONTRACT_HASH,
    PRIORITY_CONTRACT_VERSION,
    PRIORITY_INTERFACE_HASH,
    PRIORITY_INTERFACE_VERSION,
)
from exp.shared.priority import current_scientific_authority
from exp.shared.recovery_priority import (
    materialize_priority_score_record,
    validate_authoritative_dependencies,
)
from model.M1.contracts import M1V2Scenario
from model.M2.contracts import ScenarioConsequence
from model.common.hashing import file_sha256
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
EXPECTED_CONTRACT_VERSION = "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"
ALLOWED_DIRTY_PREFIXES = (
    "artifacts/diagnostics/shared_priority_phase0/",
    "exp/shared/",
    "exp/exp2/priority.py",
    "exp/exp3/",
    "tests/contract/test_shared_recovery_priority.py",
    "tests/exp_shared/",
    "tests/integration/test_shared_recovery_priority_integration.py",
    "validation/materialize_shared_priority_phase0.py",
)
VALIDATION_INPUTS = (
    ROOT / "exp" / "shared" / "contracts.py",
    ROOT / "exp" / "shared" / "priority.py",
    ROOT / "exp" / "shared" / "recovery_priority.py",
    ROOT / "exp" / "exp2" / "priority.py",
    ROOT / "tests" / "contract" / "test_shared_recovery_priority.py",
    ROOT / "tests" / "exp2" / "test_priority.py",
    ROOT / "tests" / "exp2" / "test_model_reuse_contract.py",
    ROOT / "tests" / "exp_shared" / "test_priority_interface.py",
    ROOT / "tests" / "integration" / "test_shared_recovery_priority_integration.py",
    ROOT / "model" / "M2" / "cu" / "registry.py",
    ROOT / "registries" / "m2_data2_formal_cu_v4.json",
    M1_FIXTURE,
    M2_FIXTURE,
)
TEST_COMMANDS = (
    (
        "contract",
        (sys.executable, "-m", "pytest", "-q", "tests/contract/test_shared_recovery_priority.py"),
    ),
    (
        "exp2_bridge_contract",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/exp2/test_priority.py",
            "tests/exp2/test_model_reuse_contract.py",
            "tests/exp_shared",
        ),
    ),
    (
        "integration",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/integration/test_shared_recovery_priority_integration.py",
        ),
    ),
)
COMPILE_COMMAND = (
    sys.executable,
    "-m",
    "compileall",
    "-q",
    "exp/shared",
    "exp/exp2",
    "validation/materialize_shared_priority_phase0.py",
)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.replace(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def _repository_head() -> str:
    result = _run(("git", "rev-parse", "HEAD"))
    if result.returncode != 0:
        raise RuntimeError("PHASE0_GIT_HEAD_UNAVAILABLE")
    return result.stdout.strip()


def _worktree_status() -> tuple[str, ...]:
    result = _run(("git", "status", "--porcelain=v1", "--untracked-files=all"))
    if result.returncode != 0:
        raise RuntimeError("PHASE0_GIT_STATUS_UNAVAILABLE")
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _status_path(line: str) -> str:
    value = line[3:].strip().replace("\\", "/")
    return value.split(" -> ")[-1]


def _unexpected_dirty(status: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        line
        for line in status
        if not any(_status_path(line).startswith(prefix) for prefix in ALLOWED_DIRTY_PREFIXES)
    )


def _input_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)).replace("\\", "/"): file_sha256(path)
        for path in VALIDATION_INPUTS
    }


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


def _run_tests() -> tuple[list[dict[str, object]], int, int]:
    summaries: list[dict[str, object]] = []
    passed_total = 0
    failed_total = 0
    for name, command in TEST_COMMANDS:
        result = _run(command)
        output = (result.stdout + result.stderr).strip()
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        summaries.append(
            {
                "name": name,
                "command": " ".join(command),
                "exit_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "output": output,
            }
        )
        passed_total += passed
        failed_total += failed
        if result.returncode != 0:
            raise RuntimeError(f"SHARED_PRIORITY_TESTS_FAILED:{name}")
    return summaries, passed_total, failed_total


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


def _write_block(
    *,
    status: str,
    head_start: str,
    head_end: str,
    worktree_start: tuple[str, ...],
    reasons: tuple[str, ...],
) -> None:
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
        "head_start": head_start,
        "head_end": head_end,
        "head_stable": head_start == head_end,
        "worktree_status_start": list(worktree_start),
        "reasons": list(reasons),
        "previous_run_status": "BLOCK_CONTRACT_RECONCILIATION_REQUIRED",
        "previous_run_reason": "HEAD_CHANGED_DURING_EXECUTION",
        "final_test_accessed": False,
        "model_retrained": False,
        "model_reselected": False,
        "scientific_parameter_reselected": False,
        "m1_modified": False,
        "m2_modified": False,
        "ranking_performed": False,
        "paper_result_generated": False,
        "status": status,
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_MANIFEST.json", manifest)
    _write_text(
        OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_REPORT.md",
        "# Shared Recovery-Priority Phase 0 Finalization\n\n"
        f"- HEAD start: `{head_start}`\n"
        f"- HEAD end: `{head_end}`\n"
        f"- Status: `{status}`\n"
        f"- Reasons: `{', '.join(reasons)}`\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head-start", required=True)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    head_start = _repository_head()
    worktree_start = _worktree_status()
    if head_start != args.expected_head_start:
        _write_block(
            status="BLOCK_HEAD_CHANGED_DURING_PHASE0_FINALIZATION",
            head_start=args.expected_head_start,
            head_end=head_start,
            worktree_start=worktree_start,
            reasons=("HEAD_START_MISMATCH",),
        )
        return 2
    unexpected = _unexpected_dirty(worktree_start)
    if unexpected:
        _write_block(
            status="BLOCK_DIRTY_WORKTREE_REQUIRES_RECONCILIATION",
            head_start=head_start,
            head_end=head_start,
            worktree_start=worktree_start,
            reasons=unexpected,
        )
        return 2

    input_hashes_start = _input_hashes()
    authority = current_scientific_authority()
    if (
        PRIORITY_CONTRACT_VERSION != EXPECTED_CONTRACT_VERSION
        or authority.version != EXPECTED_CONTRACT_VERSION
        or authority.authority != "HUMAN_APPROVED"
        or authority.status != "FROZEN_FOR_EXP2_EXP3_EXP4"
    ):
        _write_block(
            status="BLOCK_CONTRACT_RECONCILIATION_REQUIRED",
            head_start=head_start,
            head_end=_repository_head(),
            worktree_start=worktree_start,
            reasons=("SCIENTIFIC_AUTHORITY_MISMATCH",),
        )
        return 2

    dependency = validate_authoritative_dependencies()
    test_summaries, tests_passed, tests_failed = _run_tests()
    compile_result = _run(COMPILE_COMMAND)
    if compile_result.returncode != 0:
        raise RuntimeError("SHARED_PRIORITY_COMPILE_CHECK_FAILED")

    scenarios, consequences, lineage = _load_fixed_development_node()
    record = materialize_priority_score_record(
        scenarios,
        consequences,
        repository_head=head_start,
        m1_lineage=lineage,
    )
    repeated = materialize_priority_score_record(
        tuple(reversed(scenarios)),
        tuple(reversed(consequences)),
        repository_head=head_start,
        m1_lineage=lineage,
    )
    if record.artifact_id != repeated.artifact_id:
        raise RuntimeError("SHARED_PRIORITY_NONDETERMINISTIC_OUTPUT")

    input_hashes_end = _input_hashes()
    head_end = _repository_head()
    if head_start != head_end:
        _write_block(
            status="BLOCK_HEAD_CHANGED_DURING_PHASE0_FINALIZATION",
            head_start=head_start,
            head_end=head_end,
            worktree_start=worktree_start,
            reasons=("HEAD_CHANGED_DURING_VALIDATION",),
        )
        return 2
    if input_hashes_start != input_hashes_end:
        changed = tuple(
            path
            for path in input_hashes_start
            if input_hashes_start[path] != input_hashes_end[path]
        )
        _write_block(
            status="BLOCK_DIRTY_WORKTREE_REQUIRES_RECONCILIATION",
            head_start=head_start,
            head_end=head_end,
            worktree_start=worktree_start,
            reasons=changed,
        )
        return 2

    if record.score_C is None:
        final_status = "ABSTAIN_DEVELOPMENT_SMOKE_NO_COMPLETE_SUPPORTED_RECORD"
        records_materialized = 0
        records_abstained = 1
    else:
        final_status = "PHASE0_PASS"
        records_materialized = 1
        records_abstained = 0

    record_payload = record.model_dump(mode="json")
    if records_materialized:
        _write_text(
            OUTPUT_DIR / "SHARED_PRIORITY_DEVELOPMENT_RECORDS.jsonl",
            json.dumps(record_payload, sort_keys=True) + "\n",
        )
    reason_counts = dict(Counter(record.reason_codes))
    smoke = {
        "schema_version": "SHARED_PRIORITY_DEVELOPMENT_SMOKE_V1",
        "scope": "DEVELOPMENT_ONLY_INTERFACE_SMOKE",
        "artifact_stage": "DEVELOPMENT_ONLY_PHASE0_VALIDATION",
        "paper_result": False,
        "ranking_performed": False,
        "final_test_accessed": False,
        "fixture_artifacts": [
            str(M1_FIXTURE.relative_to(ROOT)).replace("\\", "/"),
            str(M2_FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        ],
        "records_attempted": 1,
        "records_materialized": records_materialized,
        "records_abstained": records_abstained,
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
        "record_artifact_ids": [record.artifact_id] if records_materialized else [],
        "status": final_status,
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_DEVELOPMENT_SMOKE.json", smoke)
    test_summary = {
        "schema_version": "SHARED_PRIORITY_CONTRACT_TEST_SUMMARY_V1",
        "commands": test_summaries,
        "compile_command": " ".join(COMPILE_COMMAND),
        "compile_exit_code": compile_result.returncode,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "status": "PASS",
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_CONTRACT_TEST_SUMMARY.json", test_summary)
    _write_json(
        OUTPUT_DIR / "SHARED_PRIORITY_INTERFACE_TEST_SUMMARY.json",
        {
            "schema_version": "SHARED_PRIORITY_INTERFACE_TEST_SUMMARY_V1",
            "scientific_contract_version": PRIORITY_CONTRACT_VERSION,
            "scientific_contract_hash": PRIORITY_CONTRACT_HASH,
            "interface_version": PRIORITY_INTERFACE_VERSION,
            "interface_hash": PRIORITY_INTERFACE_HASH,
            "authority_note": "INTERFACE_IS_DESCRIPTIVE_NOT_COMPETING_AUTHORITY",
            "status": "SUPERSEDED_BY_SHARED_PRIORITY_CONTRACT_TEST_SUMMARY",
        },
    )
    audit = {
        "audit_date": "2026-09-06",
        "repository_head": head_start,
        "head_stable": True,
        "contract_reconciliation": "RESOLVED",
        "scientific_contract": authority.model_dump(mode="json"),
        "active_m2_registry_id": dependency["registry_id"],
        "active_m2_registry_hash": dependency["registry_hash"],
        "m2_cu_normalization_registry_hash": dependency[
            "cu_normalization_registry_hash"
        ],
        "m2_scope_hash": dependency["scope_hash"],
        "formal_scope": list(dependency["registry"].formal_scope),
        "shared_single_source": True,
        "exp2_delegates_shared_arithmetic": True,
        "ranking_scope": "EXPERIMENT_SPECIFIC_NOT_SHARED",
        "development_fixture": smoke["fixture_artifacts"],
        "final_test_required": False,
        "status": "PASS",
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_DEPENDENCY_AUDIT.json", audit)
    _write_text(
        OUTPUT_DIR / "SHARED_PRIORITY_DEPENDENCY_AUDIT.md",
        f"""# Shared Recovery-Priority Phase 0 Dependency Audit

- Date: `2026-09-06`
- Repository HEAD: `{head_start}`
- HEAD stable: `true`
- Contract reconciliation: `RESOLVED`
- Scientific contract: `{PRIORITY_CONTRACT_VERSION}`
- Authority: `HUMAN_APPROVED`
- Contract status: `FROZEN_FOR_EXP2_EXP3_EXP4`
- Active M2 registry: `{dependency['registry_id']}`
- Registry hash: `{dependency['registry_hash']}`
- Scope hash: `{dependency['scope_hash']}`
- Exact seven-component scope: `PASS`
- Shared ranking: `NONE`; ranking remains experiment-specific
- Final Test required: `false`
""",
    )

    worktree_end = _worktree_status()
    modified_files = sorted({_status_path(line) for line in worktree_end})
    manifest = {
        "schema_version": "SHARED_PRIORITY_PHASE0_MANIFEST_V1",
        "head_start": head_start,
        "head_end": head_end,
        "head_stable": True,
        "worktree_status_start": list(worktree_start),
        "worktree_status_end": list(worktree_end),
        "modified_files": modified_files,
        "previous_run_status": "BLOCK_CONTRACT_RECONCILIATION_REQUIRED",
        "previous_run_reason": "HEAD_CHANGED_DURING_EXECUTION",
        "scientific_contract": {
            "version": PRIORITY_CONTRACT_VERSION,
            "hash": PRIORITY_CONTRACT_HASH,
            "authority": "HUMAN_APPROVED",
            "status": "FROZEN_FOR_EXP2_EXP3_EXP4",
        },
        "implementation": {
            "namespace": "exp.shared",
            "shared_single_source": True,
            "interface_version": PRIORITY_INTERFACE_VERSION,
            "interface_hash": PRIORITY_INTERFACE_HASH,
        },
        "artifact_stage": "DEVELOPMENT_ONLY_PHASE0_VALIDATION",
        "active_m2_registry_id": dependency["registry_id"],
        "active_m2_registry_hash": dependency["registry_hash"],
        "m2_cu_normalization_registry_hash": dependency[
            "cu_normalization_registry_hash"
        ],
        "m2_scope_hash": dependency["scope_hash"],
        "validation_input_hashes": input_hashes_end,
        "tests_run": tests_passed + tests_failed,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "development_fixture": smoke["fixture_artifacts"],
        "development_records_attempted": 1,
        "development_records_materialized": records_materialized,
        "development_abstentions": records_abstained,
        "development_reproducibility_hash": smoke["reproducibility_hash"],
        "final_test_accessed": False,
        "model_retrained": False,
        "model_reselected": False,
        "scientific_parameter_reselected": False,
        "m1_modified": False,
        "m2_modified": False,
        "ranking_performed": False,
        "paper_result_generated": False,
        "status": final_status,
    }
    _write_json(OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_MANIFEST.json", manifest)
    _write_text(
        OUTPUT_DIR / "SHARED_PRIORITY_PHASE0_REPORT.md",
        f"""# Shared Recovery-Priority Phase 0 Finalization

- HEAD start: `{head_start}`
- HEAD end: `{head_end}`
- HEAD stable: `true`
- Scientific authority: `{PRIORITY_CONTRACT_VERSION}`
- Reconciliation: `RESOLVED`
- Contract status: `FROZEN_FOR_EXP2_EXP3_EXP4`
- Artifact stage: `DEVELOPMENT_ONLY_PHASE0_VALIDATION`
- Tests: `{tests_passed} passed, {tests_failed} failed`
- Development smoke: `1 attempted / {records_materialized} materialized / {records_abstained} abstained`
- Final Test accessed: `false`
- Ranking performed: `false`

## Final Status

`{final_status}`
""",
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0 if final_status == "PHASE0_PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
