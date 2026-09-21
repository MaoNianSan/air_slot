"""Immutable execution freeze for the stage-matched Phase-7 Final-Test epoch.

Both worktrees are intentionally dirty. The freeze therefore binds the actual
runtime bytes and scientific contract rather than treating either branch HEAD
as the executed implementation.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from model.common.identity import content_id
from model.M3.stage1 import ATTENTION_CAPACITY_GRID, STAGE_I_TIE_BREAK

from . import constants as C
from .authority import validate_instruction_copies, validate_phase7_authority
from .errors import TypedBlocker, _require
from .executor import paper_views as _paper_views
from .executor import stages as S
from .executor.raw_source import LOCAL_ONLY_INPUTS, REFERENCE_PAYLOAD_FILES
from .materialization import _file_sha256, _read_json, _write_json_atomic
from .stage2_authority import production_solver_metadata


FREEZE_SCHEMA_VERSION = "AIR_SLOT_V2_JATM_STAGE_MATCHED_EXECUTION_FREEZE_V2"
PRE_OPEN_SCHEMA_VERSION = "AIR_SLOT_V2_JATM_STAGE_MATCHED_PRE_OPEN_GATE_V2"
FREEZE_ID = "JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2"
PREVIOUS_NONCANONICAL_FINAL_TEST_EPOCH = (
    "SEALED_AUDIT_FAILED_CANONICALIZATION"
)
PREVIOUS_FINAL_TEST_EPOCH = (
    "SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE"
)
CONSUMED_NONCANONICAL_EPOCH_SEAL_STATUS = "SEALED_AUDIT_FAILED"
CONSUMED_EPOCH_SEAL_STATUS = (
    "SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE"
)
CANONICAL_STAGE_NODE_CONTRACT = (
    "ONE_NODE_PER_EPISODE_STAGE_BEFORE_SUPPORT"
)
FORMAL_EXECUTOR_RECONCILIATION = "SCIENTIFIC_OUTPUT_COMPLETENESS"
GOVERNANCE_DELTA_CLASSIFICATION = (
    "FORMAL_EXECUTION_COMPLETENESS_ONLY"
)
GOVERNANCE_DELTA_SCOPE = (
    "PAIRED_MARGINAL_INCREMENT_AND_SECTION5_ROBUSTNESS_EXECUTION_ONLY"
)
PAPER_PRIMARY_ROOT_ENV = "AIRSLOT_PAPER_PRIMARY_ROOT"
# After the authority consolidation the paper-primary content lives in the
# canonical repository itself; the freeze self-probes this repository and no
# longer depends on any other worktree path. The environment override is
# retained for historical validation scenarios only.
DEFAULT_PAPER_PRIMARY_ROOT = C.ROOT
FREEZE_JSON_PATH = (
    C.ROOT / "formal" / "JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json"
)
FREEZE_MD_PATH = (
    C.ROOT / "formal" / "JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.md"
)
PRE_OPEN_REPORT_PATH = (
    C.ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_phase7"
    / "STAGE_MATCHED_PRE_OPEN_GATE.json"
)

PHASE7_RUNTIME_SOURCE_SPECS = (
    ("formal", (".py",)),
    ("model", (".py",)),
    ("validation/v2_phase5", (".py",)),
    ("exp/shared", (".py",)),
)
PHASE7_RUNTIME_CONFIG_SPECS = (
    ("configs", None),
    ("registries", None),
)
PHASE7_VALIDATION_SPECS = (
    ("tests/phase7", (".py",)),
    ("validation/v2_phase7", (".py",)),
)
PAPER_PRIMARY_RUNTIME_SOURCE_SPECS = (
    ("exp/jatm_section5", (".py",)),
    ("exp/jatm_section4", (".py",)),
    ("model", (".py",)),
)
PAPER_PRIMARY_CONFIG_SPECS = (
    ("configs", None),
    ("registries", None),
)
PAPER_PRIMARY_VALIDATION_SPECS = (
    ("tests/jatm_section5", (".py",)),
)

PHASE7_VOLATILE_OUTPUT_PREFIXES = (
    "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V1.json",
    "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V1.md",
    "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json",
    "formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.md",
    "artifacts/diagnostics/v2_phase7/STAGE_MATCHED_PRE_OPEN_GATE.json",
    "artifacts/experiment/final_test_v2_stage_matched",
    "artifacts/experiment/final_test_v2_stage_matched_canonical_v1",
    "artifacts/experiment/final_test_v2_stage_matched_canonical_v2",
)
PHASE7_TASK_OWNED_PREFIXES = (
    "formal/v2_phase7/executor/attention_decisions.py",
    "formal/v2_phase7/__init__.py",
    "formal/v2_phase7/constants.py",
    "formal/v2_phase7/execution_freeze.py",
    "formal/v2_phase7/gate_b.py",
    "formal/v2_phase7/executor/m4_comparisons.py",
    "formal/v2_phase7/executor/paper_views.py",
    "formal/v2_phase7/executor/reference_cohort.py",
    "formal/v2_phase7/executor/stages.py",
    "formal/v2_phase7_final_test_run.py",
    "model/PRE/streaming/data2.py",
    "tests/phase7/",
    "validation/v2_phase7/",
    "artifacts/diagnostics/v2_phase7/",
)
PAPER_PRIMARY_TASK_OWNED_PREFIXES = (
    "exp/jatm_section4/",
    "exp/jatm_section5/",
    "tests/jatm_section5/",
    "artifacts/diagnostics/jatm_section4/",
    "artifacts/experiment/jatm_section5/",
)
PAPER_PRIMARY_PRE_EXISTING_INCLUDED_PREFIXES = ("model/M3/", "model/M4/")
PAPER_PRIMARY_PRE_EXISTING_NOT_FINAL_TEST_RUNTIME_PREFIXES = (
    "artifacts/diagnostics/m1_v2_feature_gate_b2r/",
    "docs/ACTION_DECISION_CONTRACT.md",
    "formal/RUNTIME_PATH.md",
    "tmp/",
    "$null",
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=Path(root),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_lines(root: Path, *args: str) -> tuple[str, ...]:
    output = _git(root, *args)
    return tuple(line for line in output.splitlines() if line.strip())


def _worktree_identity(root: Path) -> dict[str, Any]:
    return {
        "root": str(Path(root).resolve()),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git(root, "rev-parse", "HEAD"),
        "dirty": bool(
            _git(root, "status", "--porcelain=v1", "--untracked-files=all")
        ),
    }


def _iter_spec_files(
    root: Path, specs: Sequence[tuple[str, tuple[str, ...] | None]]
) -> tuple[Path, ...]:
    files: set[Path] = set()
    for relative, suffixes in specs:
        target = Path(root) / relative
        if target.is_file():
            if suffixes is None or target.suffix.lower() in suffixes:
                files.add(target)
            continue
        if not target.is_dir():
            continue
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            if suffixes is None or path.suffix.lower() in suffixes:
                files.add(path)
    return tuple(sorted(files, key=lambda item: item.as_posix()))


def _hash_files(root: Path, files: Iterable[Path]) -> dict[str, str]:
    base = Path(root).resolve()
    records: dict[str, str] = {}
    for path in files:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(base).as_posix()
        records[relative] = _file_sha256(resolved)
    return records


def _classify(
    paths: Sequence[str], prefixes: Sequence[str]
) -> list[str]:
    return sorted(
        path
        for path in paths
        if any(path == prefix or path.startswith(prefix) for prefix in prefixes)
    )


def _status_paths(root: Path) -> list[str]:
    paths: list[str] = []
    for line in _git_lines(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    ):
        if len(line) >= 4:
            paths.append(line[3:].strip('"'))
    return sorted(paths)


def _record_if_present(
    path: Path, *, declared_hash: str | None = None
) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {
            "path": str(target),
            "exists": False,
            "sha256": None,
            "declared_sha256": declared_hash,
        }
    actual = _file_sha256(target)
    return {
        "path": str(target),
        "exists": True,
        "sha256": actual,
        "declared_sha256": declared_hash,
        "declared_hash_match": (
            None if declared_hash is None else actual == declared_hash
        ),
    }


def _is_read_only(path: Path) -> bool:
    st = Path(path).stat()
    attributes = getattr(st, "st_file_attributes", None)
    if attributes is not None:
        return bool(attributes & stat.FILE_ATTRIBUTE_READONLY)
    return not bool(st.st_mode & stat.S_IWUSR)


def _historical_epoch_provenance() -> dict[str, Any]:
    """Disclose the immutable prior epoch without treating it as current state."""

    paths = C.historical_epoch_paths()

    def record(path: Path) -> dict[str, Any]:
        if not Path(path).is_file():
            return {
                "path": str(path),
                "exists": False,
                "sha256": None,
                "is_read_only": None,
            }
        return {
            "path": str(path),
            "exists": True,
            "sha256": _file_sha256(path),
            "is_read_only": _is_read_only(path),
        }

    return {
        "root": str(paths.root),
        "present": paths.root.exists(),
        "release": record(paths.gate_b_release_path),
        "access_audit": record(paths.access_audit_path),
        "used_for_scientific_computation": False,
        "used_for_selection": False,
    }


def _failed_epoch_provenance(
    root: Path,
    *,
    previous_epoch: str,
    expected_seal_status: str,
    expected_blocking_failures: Sequence[str],
) -> dict[str, Any]:
    """Disclose one sealed failed epoch without reusing or rewriting it."""

    root = Path(root)
    seal_path = root / "EPOCH_SEAL.json"
    audit_path = root / "POST_EXECUTION_AUDIT.json"
    release_path = root / "GATE_B_HUMAN_RELEASE.json"
    record = {
        "root": str(root),
        "previous_final_test_epoch": previous_epoch,
        "present": root.exists(),
        "epoch_seal_path": str(seal_path),
        "epoch_seal_exists": seal_path.is_file(),
        "epoch_seal_sha256": (
            _file_sha256(seal_path) if seal_path.is_file() else None
        ),
        "post_execution_audit_path": str(audit_path),
        "post_execution_audit_exists": audit_path.is_file(),
        "post_execution_audit_sha256": (
            _file_sha256(audit_path) if audit_path.is_file() else None
        ),
        "human_release_path": str(release_path),
        "human_release_exists": release_path.is_file(),
        "human_release_sha256": (
            _file_sha256(release_path) if release_path.is_file() else None
        ),
        "tree_content_hash": _epoch_tree_hash(root),
        "invalid_for_paper_results": True,
        "used_for_current_epoch": False,
        "used_for_scientific_computation": False,
        "used_for_selection": False,
        "expected_seal_status": expected_seal_status,
        "expected_blocking_failure_codes": list(expected_blocking_failures),
    }
    if seal_path.is_file():
        seal = _read_json(seal_path)
        record["seal_status"] = seal.get("status")
        record["blocking_failure_codes"] = list(
            seal.get("blocking_failure_codes", ())
        )
        record["access_epoch_consumed"] = bool(
            seal.get("access_epoch_consumed")
        )
    if audit_path.is_file():
        audit = _read_json(audit_path)
        record["post_execution_audit_status"] = audit.get("status")
        guards = audit.get("guard_results")
        if isinstance(guards, Mapping):
            canonicalization = guards.get(
                "CANONICALIZATION_BEFORE_SUPPORT"
            )
        else:
            canonicalization = next(
                (
                    check.get("status")
                    for check in audit.get("checks", ())
                    if check.get("code")
                    == "CANONICALIZATION_BEFORE_SUPPORT"
                ),
                None,
            )
        record["canonicalization_before_support"] = canonicalization
    return record


def _consumed_stage_matched_epoch_provenance() -> dict[str, Any]:
    """Disclose the canonical-but-output-incomplete failed epoch."""

    return _failed_epoch_provenance(
        C.CONSUMED_CANONICAL_V1_FINAL_TEST_ROOT,
        previous_epoch=PREVIOUS_FINAL_TEST_EPOCH,
        expected_seal_status=CONSUMED_EPOCH_SEAL_STATUS,
        expected_blocking_failures=(
            "PAIRED_MARGINAL_INCREMENT_NOT_EXECUTED",
            "SECTION5_ROBUSTNESS_RESULTS_NOT_EXECUTED",
        ),
    )


def _previous_noncanonical_epoch_provenance() -> dict[str, Any]:
    """Disclose the earlier canonicalization-failed epoch."""

    return _failed_epoch_provenance(
        C.CONSUMED_STAGE_MATCHED_FINAL_TEST_ROOT,
        previous_epoch=PREVIOUS_NONCANONICAL_FINAL_TEST_EPOCH,
        expected_seal_status=CONSUMED_NONCANONICAL_EPOCH_SEAL_STATUS,
        expected_blocking_failures=("CANONICALIZATION_BEFORE_SUPPORT",),
    )


def _authority_records() -> dict[str, Any]:
    records = {
        "r2_registry": (C.R2_REGISTRY_PATH, C.R2_REGISTRY_FILE_SHA256),
        "parent_registry": (
            C.PARENT_REGISTRY_PATH,
            C.PARENT_REGISTRY_FILE_SHA256,
        ),
        "stage2_authority_overlay": (
            C.STAGE2_AUTHORITY_RECONCILIATION_PATH,
            C.STAGE2_AUTHORITY_RECONCILIATION_FILE_SHA256,
        ),
        "m2_v5_registry": (
            C.M2_V5_REGISTRY_PATH,
            C.M2_V5_REGISTRY_FILE_SHA256,
        ),
        "passenger_supersession_v3": (
            C.PASSENGER_SUPERSESSION_V3_PATH,
            C.PASSENGER_SUPERSESSION_V3_FILE_SHA256,
        ),
        "m2_reference": (
            C.M2_REFERENCE_PATH,
            C.M2_REFERENCE_FILE_SHA256,
        ),
        "train_support_summary": (
            C.TRAIN_SUPPORT_SUMMARY_PATH,
            C.TRAIN_SUPPORT_SUMMARY_FILE_SHA256,
        ),
        "train_support_samples": (
            C.TRAIN_SUPPORT_SAMPLES_PATH,
            C.TRAIN_SUPPORT_SAMPLES_FILE_SHA256,
        ),
        "formal_cohort_authority": (
            C.COHORT_AUTHORITY_PATH,
            C.COHORT_AUTHORITY_FILE_SHA256,
        ),
        "formal_cohort_manifest": (
            C.COHORT_MANIFEST_PATH,
            C.COHORT_MANIFEST_FILE_SHA256,
        ),
        "instruction_repo": (C.INSTRUCTION_REPO_PATH, None),
        "instruction_download": (C.INSTRUCTION_DOWNLOAD_PATH, None),
        "bootstrap_seed_lock": (C.BOOTSTRAP_SEED_LOCK_PATH, None),
        "bootstrap_seed_source": (C.BOOTSTRAP_SEED_SOURCE_PATH, None),
        "h16_primary_checkpoint": (
            C.ROOT
            / "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/"
            "M1_H16_HISTORY_PRIMARY.pt",
            None,
        ),
        "h16_primary_manifest": (
            C.ROOT
            / "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/"
            "M1_H16_HISTORY_PRIMARY_MANIFEST.json",
            None,
        ),
        "current_comparator_checkpoint": (
            C.ROOT
            / "artifacts/models/m1/M1_H16_CURRENT_COMPARATOR/"
            "M1_H16_CURRENT_COMPARATOR.pt",
            None,
        ),
        "current_comparator_manifest": (
            C.ROOT
            / "artifacts/models/m1/M1_H16_CURRENT_COMPARATOR/"
            "M1_H16_CURRENT_COMPARATOR_MANIFEST.json",
            None,
        ),
        "tail_continuation_manifest": (
            C.ROOT
            / "artifacts/diagnostics/m1_positive_tail_continuation_v1/"
            "M1_POSITIVE_TAIL_CONTINUATION_V1.json",
            None,
        ),
    }
    output = {
        name: _record_if_present(path, declared_hash=declared)
        for name, (path, declared) in records.items()
    }
    for name, relative in REFERENCE_PAYLOAD_FILES.items():
        output[f"reference_payload_{name}"] = _record_if_present(
            C.ROOT / relative
        )
    return output


def _dirty_classification() -> dict[str, Any]:
    paper_root = Path(
        os.environ.get(PAPER_PRIMARY_ROOT_ENV, DEFAULT_PAPER_PRIMARY_ROOT)
    )
    phase7_status = _status_paths(C.ROOT)
    paper_paths = _status_paths(paper_root)
    volatile = _classify(
        phase7_status, PHASE7_VOLATILE_OUTPUT_PREFIXES
    )
    phase7_paths = [
        path for path in phase7_status if path not in set(volatile)
    ]
    phase7_task = _classify(phase7_paths, PHASE7_TASK_OWNED_PREFIXES)
    return {
        "authority_scope": "CONTENT_ADDRESSED_RUNTIME_NOT_GIT_HEAD",
        "phase7_all_dirty_paths": phase7_paths,
        "phase7_volatile_outputs_excluded": volatile,
        "phase7_task_owned_stage_matched": phase7_task,
        "phase7_pre_existing_dirty": sorted(
            set(phase7_paths) - set(phase7_task)
        ),
        "paper_primary_all_dirty_paths": paper_paths,
        "paper_primary_task_owned_stage_matched": _classify(
            paper_paths, PAPER_PRIMARY_TASK_OWNED_PREFIXES
        ),
        "paper_primary_pre_existing_dirty_included_in_development_authority": (
            _classify(
                paper_paths,
                PAPER_PRIMARY_PRE_EXISTING_INCLUDED_PREFIXES,
            )
        ),
        "paper_primary_pre_existing_dirty_not_in_final_test_runtime": (
            _classify(
                paper_paths,
                PAPER_PRIMARY_PRE_EXISTING_NOT_FINAL_TEST_RUNTIME_PREFIXES,
            )
        ),
    }


def _development_manifest_path(paper_root: Path) -> Path:
    return (
        paper_root
        / "artifacts"
        / "experiment"
        / "jatm_section5"
        / "development"
        / "report"
        / "JATM_SECTION5_MANIFEST.json"
    )


def _load_development_manifest(paper_root: Path) -> dict[str, Any]:
    path = _development_manifest_path(paper_root)
    _require(path.is_file(), "FREEZE_DEVELOPMENT_MANIFEST_MISSING", str(path))
    manifest = _read_json(path)
    checks = (
        (
            "development_ready_for_freeze",
            "YES",
            "FREEZE_DEVELOPMENT_NOT_READY",
        ),
        (
            "scientific_patch",
            "STAGE_MATCHED_PRE_TURN_SCREENING",
            "FREEZE_DEVELOPMENT_PATCH_MISSING",
        ),
        (
            "stage1_overall_aggregation",
            "PRE_TURN_OBJECTIVE_THEN_NORMALIZE",
            "FREEZE_DEVELOPMENT_AGGREGATION_INVALID",
        ),
        (
            "stage2_sobt_coordinate",
            "NODE_RELATIVE_SOBT",
            "FREEZE_DEVELOPMENT_SOBT_COORDINATE_INVALID",
        ),
        (
            "section5_primary_model",
            "H16_FROZEN_PRIMARY",
            "FREEZE_DEVELOPMENT_PRIMARY_MODEL_INVALID",
        ),
        (
            "section4_h_capacity_status",
            "REUSED_NOT_RERUN",
            "FREEZE_DEVELOPMENT_SECTION4_STATUS_INVALID",
        ),
    )
    for field, expected, code in checks:
        _require(manifest.get(field) == expected, code, manifest.get(field))
    return manifest


def _development_artifact_records(paper_root: Path) -> dict[str, Any]:
    manifest_path = _development_manifest_path(paper_root)
    report_path = (
        manifest_path.parent / "JATM_SECTION5_DEVELOPMENT_REPORT.md"
    )
    return {
        "manifest": _record_if_present(manifest_path),
        "report": _record_if_present(report_path),
    }


def _phase7_cross_contract_snapshot() -> dict[str, Any]:
    return {
        "stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "classes": ["PRE", "TURN"],
        "representations": list(S.PRIMARY_STATE_VARIANTS),
        "reference": S.REFERENCE_VARIANT,
        "comparators": list(S.COMPARATOR_VARIANTS),
        "q_grid": [float(value) for value in ATTENTION_CAPACITY_GRID],
        "tie": STAGE_I_TIE_BREAK,
        "lambda_grid": [0.10, 0.25, 0.50, 1.00],
        "action_grid_u45": [float(value) for value in range(0, 50, 5)],
        "exact_enumeration_status": "EXACT_ENUMERATION",
    }


def _paper_primary_cross_contract_snapshot(
    paper_root: Path,
) -> dict[str, Any]:
    """Read the paper-side contract in a separate interpreter."""

    probe = """
import json
from exp.jatm_section5.contracts import (
    FLATTENED_UNION_SEMANTICS,
    REPRESENTATIONS,
    STAGE1_ACTIONABLE_STAGE_CLASSES,
    STAGE1_ACTIONABLE_STAGES,
)
from model.M3.stage1 import ATTENTION_CAPACITY_GRID, STAGE_I_TIE_BREAK
from model.M3.stage2 import LAMBDA_GRID, action_grid
from model.common.decision_contracts import SolverStatus

print(json.dumps({
    "stages": [stage.value for stage in STAGE1_ACTIONABLE_STAGES],
    "classes": list(STAGE1_ACTIONABLE_STAGE_CLASSES),
    "representations": list(REPRESENTATIONS),
    "reference": "HISTORY_JOINT",
    "comparators": [
        value for value in REPRESENTATIONS if value != "HISTORY_JOINT"
    ],
    "q_grid": [float(value) for value in ATTENTION_CAPACITY_GRID],
    "tie": STAGE_I_TIE_BREAK,
    "lambda_grid": [float(value) for value in LAMBDA_GRID],
    "action_grid_u45": [float(value) for value in action_grid(45.0)],
    "exact_enumeration_status": SolverStatus.EXACT_ENUMERATION.value,
    "flattened_union_semantics": FLATTENED_UNION_SEMANTICS,
}, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(paper_root).resolve())
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(paper_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise TypedBlocker(
            "FREEZE_PAPER_PRIMARY_CONTRACT_PROBE_FAILED",
            {
                "returncode": completed.returncode,
                "stderr": completed.stderr.strip()[-2000:],
            },
        )
    lines = [
        line for line in completed.stdout.splitlines() if line.strip()
    ]
    _require(bool(lines), "FREEZE_PAPER_PRIMARY_CONTRACT_PROBE_EMPTY")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise TypedBlocker(
            "FREEZE_PAPER_PRIMARY_CONTRACT_PROBE_INVALID",
            completed.stdout.strip()[-2000:],
        ) from error


def _cross_worktree_contract(paper_root: Path) -> dict[str, Any]:
    paper = _paper_primary_cross_contract_snapshot(paper_root)
    phase7 = _phase7_cross_contract_snapshot()
    comparable_paper = {
        key: value
        for key, value in paper.items()
        if key != "flattened_union_semantics"
    }
    if comparable_paper != phase7:
        raise TypedBlocker(
            "FREEZE_CROSS_WORKTREE_CONTRACT_MISMATCH",
            {"paper_primary": comparable_paper, "phase7": phase7},
        )
    _require(
        paper.get("flattened_union_semantics")
        == "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION",
        "FREEZE_FLATTENED_UNION_SEMANTICS_INVALID",
        paper.get("flattened_union_semantics"),
    )
    return {
        "status": "PASS",
        "scope": "STAGE1_SCREENING_AND_REPRESENTATION_CONTRACT",
        "paper_primary": paper,
        "phase7": phase7,
        "equal_on_shared_contract": True,
    }


def _contract() -> dict[str, Any]:
    action_grid = __import__(
        "model.M3.stage2", fromlist=["action_grid"]
    ).action_grid(C.NOMINAL_U_MAX)
    return {
        "scientific_patch": "STAGE_MATCHED_PRE_TURN_SCREENING",
        "cross_worktree_contract": "PASS",
        "formal_executor_reconciliation": FORMAL_EXECUTOR_RECONCILIATION,
        "paired_marginal_increment": "FROZEN_AND_EXECUTABLE",
        "section5_robustness": "FROZEN_AND_EXECUTABLE",
        "canonicalization_rule": (
            "CANONICAL_NODE_BY_EPISODE_STAGE_EARLIEST_DECISION_TIME_NODE_ID_"
            "THEN_SUPPORT"
        ),
        "stage1_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "pooled_stage1_ranking": False,
        "taxi_comp_stage1_participation": False,
        "stage1_overall_aggregation": (
            "PRE_TURN_OBJECTIVE_THEN_NORMALIZE"
        ),
        "q_grid": [float(value) for value in C.Q_GRID],
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "section5_primary_model": "H16_FROZEN_PRIMARY",
        "stage2_reference_cohort_rule": (
            "SUPPORT_QUALIFIED_UNION_OF_PRE_TURN_Q10_CONSEQUENCE_SHORTLISTS"
        ),
        "transition_coordinate": "NODE_RELATIVE_SOBT",
        "turnaround": {
            "nominal_q20_minutes": float(C.NOMINAL_TURNAROUND_Q20),
            "grid_minutes": [34.0, 41.0, 47.0],
            "quantiles": ["Q10", "Q20", "Q30"],
        },
        "u_max": {
            "nominal_minutes": float(C.NOMINAL_U_MAX),
            "by_specification": {
                key: float(value)
                for key, value in C.U_MAX_BY_SPECIFICATION.items()
            },
            "grid_minutes": [
                float(value)
                for value in C.U_MAX_BY_SPECIFICATION.values()
            ],
            "quantiles": ["Q80", "Q90", "Q95"],
        },
        "lambda": {
            "nominal": float(C.NOMINAL_LAMBDA),
            "grid": [0.10, 0.25, 0.50, 1.00],
        },
        "action_grid": [float(value) for value in action_grid],
        "bootstrap": {
            "replicates": int(C.BOOTSTRAP_REPLICATES),
            "seed": int(C.BOOTSTRAP_SEED),
            "interval": C.BOOTSTRAP_INTERVAL,
            "resampling_unit": C.BOOTSTRAP_RESAMPLING_UNIT,
        },
        "solver": production_solver_metadata(),
        "sensitivity_axes": list(_paper_views.SECTION_5_5_AXES),
    }


def _final_test_epoch() -> dict[str, Any]:
    paths = C.stage_matched_epoch_paths()
    return {
        "output_root": str(paths.root),
        "gate_a_preflight_path": str(paths.gate_a_preflight_path),
        "gate_a_dry_run_path": str(paths.gate_a_dry_run_path),
        "release_path": str(paths.gate_b_release_path),
        "access_audit_path": str(paths.access_audit_path),
        "scientific_output_root": str(paths.scientific_output_root),
        "checkpoint_root": str(paths.checkpoint_root),
        "human_release_required": True,
        "pre_open_gate_required": True,
        "new_epoch_access_count_before_open": 0,
        "prior_final_test_v2_reused": False,
        "legacy_final_test_tree_read_by_freeze": False,
        "phase7_v2_tree_read_by_freeze": False,
    }


def build_execution_freeze() -> dict[str, Any]:
    """Build the current content-addressed execution freeze."""

    paper_root = Path(
        os.environ.get(PAPER_PRIMARY_ROOT_ENV, DEFAULT_PAPER_PRIMARY_ROOT)
    )
    _require(
        paper_root.is_dir(),
        "FREEZE_PAPER_PRIMARY_ROOT_MISSING",
        str(paper_root),
    )
    development = _load_development_manifest(paper_root)
    phase7_sources = _hash_files(
        C.ROOT, _iter_spec_files(C.ROOT, PHASE7_RUNTIME_SOURCE_SPECS)
    )
    phase7_configs = _hash_files(
        C.ROOT, _iter_spec_files(C.ROOT, PHASE7_RUNTIME_CONFIG_SPECS)
    )
    phase7_validation = _hash_files(
        C.ROOT, _iter_spec_files(C.ROOT, PHASE7_VALIDATION_SPECS)
    )
    paper_sources = _hash_files(
        paper_root,
        _iter_spec_files(paper_root, PAPER_PRIMARY_RUNTIME_SOURCE_SPECS),
    )
    paper_configs = _hash_files(
        paper_root,
        _iter_spec_files(paper_root, PAPER_PRIMARY_CONFIG_SPECS),
    )
    paper_validation = _hash_files(
        paper_root,
        _iter_spec_files(paper_root, PAPER_PRIMARY_VALIDATION_SPECS),
    )
    manifest_path = _development_manifest_path(paper_root)
    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "freeze_id": FREEZE_ID,
        "status": "FROZEN_PRE_OPEN_AUTHORITY",
        "development_selection_closed": True,
        "paper_primary": {
            **_worktree_identity(paper_root),
            "runtime_file_hashes": paper_sources,
            "runtime_config_hashes": paper_configs,
            "validation_file_hashes": paper_validation,
            "runtime_file_count": len(paper_sources) + len(paper_configs),
        },
        "phase7": {
            **_worktree_identity(C.ROOT),
            "runtime_file_hashes": phase7_sources,
            "runtime_config_hashes": phase7_configs,
            "validation_file_hashes": phase7_validation,
            "runtime_file_count": (
                len(phase7_sources) + len(phase7_configs)
            ),
        },
        "governance_delta": {
            "classification": GOVERNANCE_DELTA_CLASSIFICATION,
            "scope": GOVERNANCE_DELTA_SCOPE,
            "previous_final_test_epoch": PREVIOUS_FINAL_TEST_EPOCH,
            "canonical_stage_node_contract": CANONICAL_STAGE_NODE_CONTRACT,
            "formal_executor_reconciliation": (
                FORMAL_EXECUTOR_RECONCILIATION
            ),
            "paired_marginal_increment": "FROZEN_AND_EXECUTABLE",
            "section5_robustness": "FROZEN_AND_EXECUTABLE",
            "m1_definition_changed": False,
            "m2_definition_changed": False,
            "m3_selector_definition_changed": False,
            "m3_stage2_definition_changed": False,
            "m4_loss_definition_changed": False,
            "stage1_orchestration_changed": False,
            "scientific_orchestration_changed": False,
            "formal_execution_completeness_changed": True,
            "scientific_definition_changed": False,
        },
        "consumed_stage_matched_epoch_provenance": (
            _consumed_stage_matched_epoch_provenance()
        ),
        "previous_noncanonical_epoch_provenance": (
            _previous_noncanonical_epoch_provenance()
        ),
        "historical_epoch_provenance": _historical_epoch_provenance(),
        "development_authority": {
            "manifest_sha256": _file_sha256(manifest_path),
            "manifest_artifact_content_id": development.get("artifact_hash"),
            "report_sha256": _file_sha256(
                manifest_path.parent
                / "JATM_SECTION5_DEVELOPMENT_REPORT.md"
            ),
            "scientific_patch": development.get("scientific_patch"),
            "stage1_overall_aggregation": development.get(
                "stage1_overall_aggregation"
            ),
            "stage2_sobt_coordinate": development.get(
                "stage2_sobt_coordinate"
            ),
            "section5_primary_model": development.get(
                "section5_primary_model"
            ),
            "section4_h_capacity_status": development.get(
                "section4_h_capacity_status"
            ),
            "artifact_files": _development_artifact_records(paper_root),
        },
        "authority_artifact_hashes": _authority_records(),
        "external_runtime_inputs": {
            "policy": "LOCAL_ONLY_NOT_READ_DURING_FREEZE",
            "root_env": C.PHASE7_LOCAL_INPUT_ROOT_ENV,
            "items": list(LOCAL_ONLY_INPUTS),
            "hashed_in_freeze": False,
            "must_be_resolved_at_pre_open": True,
        },
        "cross_worktree_contract": _cross_worktree_contract(paper_root),
        "scientific_contract": _contract(),
        "stage_matched_final_test_epoch": _final_test_epoch(),
        "dirty_change_classification": _dirty_classification(),
        "final_test_accounting": {
            "new_stage_matched_epoch_access_count_before_open": 0,
            "human_release_required": True,
            "pre_open_gate_required": True,
            "prior_final_test_v2_tree_reused": False,
            "legacy_final_test_tree_read_for_freeze": False,
            "development_artifacts_used_as_final_test_outcomes": False,
        },
    }
    payload["artifact_hash"] = content_id(payload)
    return payload


def _without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key != "artifact_hash"
    }


def _authority_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the content-addressed authority fields.

    Git identity, dirty-state provenance, and generated governance outputs are
    excluded. Runtime bytes, authority hashes, and the scientific contract stay
    inside the projection and fail closed on scientific or executable changes.
    """

    projection = dict(_without_hash(payload))
    projection.pop("dirty_change_classification", None)
    for worktree_key in ("paper_primary", "phase7"):
        block = projection.get(worktree_key)
        if isinstance(block, Mapping):
            projection[worktree_key] = {
                key: value
                for key, value in block.items()
                if key not in {"branch", "head", "dirty"}
            }
    return projection


def _validate_frozen_contract(payload: Mapping[str, Any]) -> None:
    cross = payload.get("cross_worktree_contract", {})
    _require(
        cross.get("status") == "PASS"
        and cross.get("equal_on_shared_contract") is True,
        "FREEZE_CROSS_WORKTREE_CONTRACT_NOT_PASS",
        cross,
    )
    governance = payload.get("governance_delta", {})
    _require(
        governance.get("classification") == GOVERNANCE_DELTA_CLASSIFICATION
        and governance.get("previous_final_test_epoch")
        == PREVIOUS_FINAL_TEST_EPOCH
        and governance.get("canonical_stage_node_contract")
        == CANONICAL_STAGE_NODE_CONTRACT
        and governance.get("formal_executor_reconciliation")
        == FORMAL_EXECUTOR_RECONCILIATION
        and governance.get("paired_marginal_increment")
        == "FROZEN_AND_EXECUTABLE"
        and governance.get("section5_robustness")
        == "FROZEN_AND_EXECUTABLE"
        and governance.get("scientific_orchestration_changed") is False
        and governance.get("formal_execution_completeness_changed") is True
        and governance.get("scientific_definition_changed") is False,
        "FREEZE_GOVERNANCE_DELTA_INVALID",
        governance,
    )
    consumed = payload.get("consumed_stage_matched_epoch_provenance", {})
    _require(
        consumed.get("present") is True
        and consumed.get("epoch_seal_exists") is True
        and consumed.get("previous_final_test_epoch")
        == PREVIOUS_FINAL_TEST_EPOCH
        and consumed.get("seal_status") == CONSUMED_EPOCH_SEAL_STATUS
        and consumed.get("blocking_failure_codes")
        == [
            "PAIRED_MARGINAL_INCREMENT_NOT_EXECUTED",
            "SECTION5_ROBUSTNESS_RESULTS_NOT_EXECUTED",
        ]
        and consumed.get("canonicalization_before_support") == "PASS"
        and consumed.get("invalid_for_paper_results") is True
        and consumed.get("used_for_current_epoch") is False
        and consumed.get("used_for_scientific_computation") is False
        and consumed.get("used_for_selection") is False,
        "FREEZE_CONSUMED_EPOCH_PROVENANCE_INVALID",
        consumed,
    )
    previous_noncanonical = payload.get(
        "previous_noncanonical_epoch_provenance", {}
    )
    _require(
        previous_noncanonical.get("present") is True
        and previous_noncanonical.get("epoch_seal_exists") is True
        and previous_noncanonical.get("previous_final_test_epoch")
        == PREVIOUS_NONCANONICAL_FINAL_TEST_EPOCH
        and previous_noncanonical.get("seal_status")
        == CONSUMED_NONCANONICAL_EPOCH_SEAL_STATUS
        and previous_noncanonical.get("blocking_failure_codes")
        == ["CANONICALIZATION_BEFORE_SUPPORT"]
        and previous_noncanonical.get("canonicalization_before_support")
        == "FAIL"
        and previous_noncanonical.get("invalid_for_paper_results") is True
        and previous_noncanonical.get("used_for_current_epoch") is False
        and previous_noncanonical.get(
            "used_for_scientific_computation"
        )
        is False
        and previous_noncanonical.get("used_for_selection") is False,
        "FREEZE_PREVIOUS_NONCANONICAL_EPOCH_PROVENANCE_INVALID",
        previous_noncanonical,
    )
    contract = payload.get("scientific_contract", {})
    _require(
        contract.get("stage1_stages") == ["PRE_IB", "POST_IB_PRE_OB"],
        "FREEZE_STAGE1_STAGES_INVALID",
        contract.get("stage1_stages"),
    )
    _require(
        contract.get("pooled_stage1_ranking") is False
        and contract.get("taxi_comp_stage1_participation") is False,
        "FREEZE_STAGE1_SCOPE_INVALID",
        contract,
    )
    _require(
        contract.get("stage1_overall_aggregation")
        == "PRE_TURN_OBJECTIVE_THEN_NORMALIZE",
        "FREEZE_STAGE1_AGGREGATION_INVALID",
        contract.get("stage1_overall_aggregation"),
    )
    _require(
        contract.get("transition_coordinate") == "NODE_RELATIVE_SOBT",
        "FREEZE_SOBT_COORDINATE_INVALID",
        contract.get("transition_coordinate"),
    )
    _require(
        contract.get("section5_primary_model") == "H16_FROZEN_PRIMARY",
        "FREEZE_PRIMARY_MODEL_INVALID",
        contract.get("section5_primary_model"),
    )
    _require(
        contract.get("formal_executor_reconciliation")
        == FORMAL_EXECUTOR_RECONCILIATION
        and contract.get("paired_marginal_increment")
        == "FROZEN_AND_EXECUTABLE"
        and contract.get("section5_robustness")
        == "FROZEN_AND_EXECUTABLE",
        "FREEZE_COMPLETENESS_CONTRACT_INVALID",
        contract,
    )
    epoch = payload.get("stage_matched_final_test_epoch", {})
    _require(
        epoch.get("output_root")
        == str(C.STAGE_MATCHED_FINAL_TEST_ROOT),
        "FREEZE_EPOCH_ROOT_INVALID",
        epoch.get("output_root"),
    )
    _require(
        epoch.get("new_epoch_access_count_before_open") == 0
        and epoch.get("human_release_required") is True
        and epoch.get("pre_open_gate_required") is True,
        "FREEZE_EPOCH_AUTHORIZATION_CONTRACT_INVALID",
        epoch,
    )


def validate_execution_freeze(
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the persisted freeze against the current worktree bytes."""

    if payload is None:
        _require(
            FREEZE_JSON_PATH.is_file(),
            "FREEZE_MANIFEST_MISSING",
            str(FREEZE_JSON_PATH),
        )
        payload = _read_json(FREEZE_JSON_PATH)
    _require(
        payload.get("schema_version") == FREEZE_SCHEMA_VERSION,
        "FREEZE_SCHEMA_VERSION_MISMATCH",
        payload.get("schema_version"),
    )
    _require(
        payload.get("artifact_hash") == content_id(_without_hash(payload)),
        "FREEZE_ARTIFACT_HASH_MISMATCH",
    )
    _validate_frozen_contract(payload)
    current = build_execution_freeze()
    actual = _authority_projection(payload)
    expected = _authority_projection(current)
    if actual != expected:
        differing = sorted(
            key
            for key in set(actual) | set(expected)
            if actual.get(key) != expected.get(key)
        )
        raise TypedBlocker(
            "FREEZE_RUNTIME_AUTHORITY_MISMATCH",
            {"differing_top_level_keys": differing},
        )
    return {
        "status": "PASS",
        "freeze_id": payload["freeze_id"],
        "artifact_hash": payload["artifact_hash"],
        "phase7_head": payload["phase7"]["head"],
        "paper_primary_head": payload["paper_primary"]["head"],
        "runtime_file_count": {
            "phase7": payload["phase7"]["runtime_file_count"],
            "paper_primary": payload["paper_primary"]["runtime_file_count"],
        },
        "cross_worktree_contract": payload["cross_worktree_contract"][
            "status"
        ],
        "authority_scope": "CONTENT_ADDRESSED_RUNTIME_NOT_GIT_HEAD",
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    contract = payload["scientific_contract"]
    phase7 = payload["phase7"]
    paper = payload["paper_primary"]
    development = payload["development_authority"]
    epoch = payload["stage_matched_final_test_epoch"]
    cross = payload["cross_worktree_contract"]
    governance = payload["governance_delta"]
    historical = payload["historical_epoch_provenance"]
    consumed = payload["consumed_stage_matched_epoch_provenance"]
    previous_noncanonical = payload[
        "previous_noncanonical_epoch_provenance"
    ]
    return "\n".join(
        [
            "# JATM Stage-Matched Final-Test Execution Freeze V2",
            "",
            f"- Freeze ID: {payload['freeze_id']}",
            f"- Status: {payload['status']}",
            f"- Artifact hash: {payload['artifact_hash']}",
            "",
            "## Worktrees",
            f"- Paper-primary branch: {paper['branch']}",
            f"- Paper-primary HEAD: {paper['head']}",
            f"- Paper-primary runtime files: {paper['runtime_file_count']}",
            f"- Phase-7 branch: {phase7['branch']}",
            f"- Phase-7 HEAD: {phase7['head']}",
            f"- Phase-7 runtime files: {phase7['runtime_file_count']}",
            "",
            "## Development Authority",
            f"- Manifest SHA256: {development['manifest_sha256']}",
            f"- Manifest artifact hash: {development['manifest_artifact_content_id']}",
            f"- Report SHA256: {development['report_sha256']}",
            f"- Scientific patch: {development['scientific_patch']}",
            f"- Stage-I aggregation: {development['stage1_overall_aggregation']}",
            f"- Stage-II coordinate: {development['stage2_sobt_coordinate']}",
            f"- Section 5 primary model: {development['section5_primary_model']}",
            f"- Section 4 status: {development['section4_h_capacity_status']}",
            "",
            "## Governance Delta",
            f"- Classification: {governance['classification']}",
            f"- Scope: {governance['scope']}",
            f"- Previous Final-Test epoch: {governance['previous_final_test_epoch']}",
            f"- Canonical stage-node contract: {governance['canonical_stage_node_contract']}",
            "- Formal executor reconciliation: "
            f"{governance['formal_executor_reconciliation']}",
            "- Paired marginal increment: "
            f"{governance['paired_marginal_increment']}",
            "- Section 5.4 robustness: "
            f"{governance['section5_robustness']}",
            f"- M1 definition changed: {governance['m1_definition_changed']}",
            f"- M2 definition changed: {governance['m2_definition_changed']}",
            f"- M3 selector definition changed: {governance['m3_selector_definition_changed']}",
            f"- M3 Stage-II definition changed: {governance['m3_stage2_definition_changed']}",
            f"- M4 loss definition changed: {governance['m4_loss_definition_changed']}",
            f"- Stage-I orchestration changed: {governance['stage1_orchestration_changed']}",
            "- Scientific orchestration changed: "
            f"{governance['scientific_orchestration_changed']}",
            "- Formal execution completeness changed: "
            f"{governance['formal_execution_completeness_changed']}",
            f"- Scientific definition changed: {governance['scientific_definition_changed']}",
            "",
            "## Historical Epoch Provenance",
            f"- Root: {historical['root']}",
            f"- Present: {historical['present']}",
            f"- Release SHA256: {historical['release']['sha256']}",
            f"- Release read-only: {historical['release']['is_read_only']}",
            f"- Access audit SHA256: {historical['access_audit']['sha256']}",
            f"- Access audit read-only: {historical['access_audit']['is_read_only']}",
            "- Used for scientific computation: NO",
            "- Used for selection: NO",
            "",
            "## Consumed Stage-Matched Epoch Provenance",
            f"- Root: {consumed['root']}",
            f"- Present: {consumed['present']}",
            f"- Seal status: {consumed.get('seal_status')}",
            f"- Seal SHA256: {consumed['epoch_seal_sha256']}",
            "- Blocking failure codes: "
            f"{consumed.get('blocking_failure_codes')}",
            "- Post-execution audit status: "
            f"{consumed.get('post_execution_audit_status')}",
            "- Canonicalization before support: "
            f"{consumed.get('canonicalization_before_support')}",
            "- Invalid for paper results: YES",
            "- Used for current epoch: NO",
            "- Used for scientific computation: NO",
            "- Used for selection: NO",
            "",
            "## Previous Noncanonical Failed Epoch Provenance",
            f"- Root: {previous_noncanonical['root']}",
            f"- Present: {previous_noncanonical['present']}",
            f"- Seal status: {previous_noncanonical.get('seal_status')}",
            f"- Seal SHA256: {previous_noncanonical['epoch_seal_sha256']}",
            "- Blocking failure codes: "
            f"{previous_noncanonical.get('blocking_failure_codes')}",
            "- Post-execution audit status: "
            f"{previous_noncanonical.get('post_execution_audit_status')}",
            "- Canonicalization before support: "
            f"{previous_noncanonical.get('canonicalization_before_support')}",
            "- Invalid for paper results: YES",
            "- Used for current epoch: NO",
            "- Used for scientific computation: NO",
            "- Used for selection: NO",
            "",
            "## Frozen Contract",
            f"- Cross-worktree contract: {cross['status']}",
            f"- Stage-I stages: {contract['stage1_stages']}",
            f"- Pooled Stage-I ranking: {contract['pooled_stage1_ranking']}",
            f"- TAXI/COMP Stage-I participation: {contract['taxi_comp_stage1_participation']}",
            f"- Canonicalization: {contract['canonicalization_rule']}",
            f"- Overall aggregation: {contract['stage1_overall_aggregation']}",
            f"- Reference representation: {contract['reference_representation_id']}",
            f"- R* rule: {contract['stage2_reference_cohort_rule']}",
            f"- Transition coordinate: {contract['transition_coordinate']}",
            f"- Bootstrap: {contract['bootstrap']}",
            "",
            "## New Final-Test Epoch",
            f"- Output root: {epoch['output_root']}",
            f"- New-epoch access count before open: {epoch['new_epoch_access_count_before_open']}",
            f"- Human release required: {epoch['human_release_required']}",
            f"- Pre-open gate required: {epoch['pre_open_gate_required']}",
            f"- Prior `final_test_v2` reused: {epoch['prior_final_test_v2_reused']}",
            "",
            "## Access Boundary",
            "- Final-Test raw data read by freeze: NO",
            "- Legacy Final-Test result tree read by freeze: NO",
            "- Prior `final_test_v2` tree read by freeze: NO",
            "",
        ]
    )


def write_execution_freeze() -> dict[str, Any]:
    """Write JSON and Markdown freeze authorities from current bytes."""

    payload = build_execution_freeze()
    FREEZE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(FREEZE_JSON_PATH, payload)
    FREEZE_MD_PATH.write_text(
        _render_markdown(payload), encoding="utf-8"
    )
    return payload


def pre_open_gate(*, write_report: bool = True) -> dict[str, Any]:
    """Run all non-Final-Test checks required before human release opens."""

    freeze = validate_execution_freeze()
    paths = C.stage_matched_epoch_paths()
    root = paths.root
    _require(
        not root.exists(),
        "FREEZE_STAGE_MATCHED_EPOCH_ROOT_PREEXISTING",
        str(root),
    )
    _require(
        not paths.gate_b_release_path.exists(),
        "FREEZE_STAGE_MATCHED_HUMAN_RELEASE_PREEXISTING",
        str(paths.gate_b_release_path),
    )
    _require(
        not paths.access_audit_path.exists(),
        "FREEZE_STAGE_MATCHED_ACCESS_AUDIT_PREEXISTING",
        str(paths.access_audit_path),
    )
    instruction = validate_instruction_copies()
    authority = validate_phase7_authority()
    from .gate_b0 import DEFAULT_NODE_LIMIT, run_gate_b0_binding_audit

    gate_b0 = run_gate_b0_binding_audit(
        output_root=C.ROOT
        / "artifacts/diagnostics/v2_phase7/"
        "STAGE_MATCHED_GATE_B0_REPORT.json",
        fixture_root=C.FIXTURE_DAG_DIAGNOSTICS_ROOT,
        node_limit=DEFAULT_NODE_LIMIT,
        epoch_paths=paths,
        historical_paths=C.historical_epoch_paths(),
        write=False,
    )
    _require(
        gate_b0.get("status") == "PASS",
        "FREEZE_GATE_B0_NOT_PASS",
        gate_b0.get("status"),
    )
    gate_checks = {
        str(item.get("name")): str(item.get("status"))
        for item in gate_b0.get("checks", ())
    }
    guard_results = gate_b0.get("scientific_guard_results") or {}
    persisted_freeze = _read_json(FREEZE_JSON_PATH)
    historical_stability = _historical_failed_epoch_hash_stability(
        persisted_freeze
    )
    _require(
        historical_stability.get("status") == "PASS",
        "FREEZE_HISTORICAL_FAILED_EPOCH_HASH_MISMATCH",
        historical_stability,
    )
    payload = {
        "schema_version": PRE_OPEN_SCHEMA_VERSION,
        "status": "PASS",
        "freeze_id": freeze["freeze_id"],
        "freeze_artifact_hash": freeze["artifact_hash"],
        "development_selection_closed": True,
        "runtime_hashes_match_freeze": True,
        "phase7_contract_bound": True,
        "FREEZE_VALIDATION": "PASS",
        "PRE_OPEN_GATE": "PASS",
        "NEW_EPOCH_ROOT_PREEXISTING": "NO",
        "NEW_RELEASE_PREEXISTING": "NO",
        "NEW_ACCESS_AUDIT_PREEXISTING": "NO",
        "PAIRED_MARGINAL_INCREMENT_EXECUTABLE": gate_checks.get(
            "PAIRED_MARGINAL_INCREMENT_EXECUTABLE", "FAIL"
        ),
        "ROBUSTNESS_EXECUTABLE": gate_checks.get(
            "ROBUSTNESS_OFAT_EXECUTED", "FAIL"
        ),
        "CANONICALIZATION_BEFORE_SUPPORT": guard_results.get(
            "CANONICALIZATION_BEFORE_SUPPORT", "FAIL"
        ),
        "CROSS_WORKTREE_CONTRACT": freeze["cross_worktree_contract"],
        "HISTORICAL_FAILED_EPOCH_HASH_STABILITY": historical_stability[
            "status"
        ],
        "scientific_guard_results": guard_results,
        "HISTORICAL_FAILED_EPOCH_HASH_STABILITY_REPORT": historical_stability,
        "scientific_contract": build_execution_freeze()[
            "scientific_contract"
        ],
        "stage_matched_epoch_output_root": str(root),
        "root_exists_before_open": False,
        "new_epoch_access_count_before_open": 0,
        "human_release_required": True,
        "pre_open_gate_required": True,
        "final_test_data_read": False,
        "legacy_final_test_result_tree_read": False,
        "prior_final_test_v2_tree_read": False,
        "instruction_check": instruction,
        "authority_check": authority,
        "gate_b0_status": gate_b0["status"],
        "blockers": [],
    }
    if write_report:
        _write_json_atomic(PRE_OPEN_REPORT_PATH, payload)
    return payload


def _epoch_tree_hash(root: Path) -> dict[str, Any]:
    """Return a path-and-content hash over every file in an epoch tree."""

    root = Path(root)
    if not root.exists():
        return {
            "root": str(root),
            "present": False,
            "file_count": 0,
            "sha256": None,
        }
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _file_sha256(path),
        }
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    ]
    return {
        "root": str(root.resolve()),
        "present": True,
        "file_count": len(files),
        "sha256": content_id(files),
    }


def _historical_failed_epoch_hash_stability(
    persisted: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed if either immutable failed epoch changed after freeze."""

    current = {
        "consumed_stage_matched_epoch_provenance": (
            _consumed_stage_matched_epoch_provenance()
        ),
        "previous_noncanonical_epoch_provenance": (
            _previous_noncanonical_epoch_provenance()
        ),
    }
    epochs: list[dict[str, Any]] = []
    for key, observed in current.items():
        expected = persisted.get(key) or {}
        file_fields = (
            "epoch_seal_sha256",
            "post_execution_audit_sha256",
            "human_release_sha256",
        )
        file_matches = {
            field: (
                expected.get(field) is not None
                and observed.get(field) == expected.get(field)
            )
            for field in file_fields
        }
        tree_match = (
            expected.get("tree_content_hash", {}).get("sha256") is not None
            and observed.get("tree_content_hash", {}).get("sha256")
            == expected.get("tree_content_hash", {}).get("sha256")
        )
        epochs.append(
            {
                "provenance_key": key,
                "root": observed.get("root"),
                "expected_tree_sha256": expected.get(
                    "tree_content_hash", {}
                ).get("sha256"),
                "current_tree_sha256": observed.get(
                    "tree_content_hash", {}
                ).get("sha256"),
                "tree_hash_match": tree_match,
                "file_hash_matches": file_matches,
            }
        )
    passed = all(
        item["tree_hash_match"]
        and all(item["file_hash_matches"].values())
        for item in epochs
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "epochs": epochs,
    }


__all__ = [
    "DEFAULT_PAPER_PRIMARY_ROOT",
    "FREEZE_ID",
    "FREEZE_JSON_PATH",
    "FREEZE_MD_PATH",
    "FREEZE_SCHEMA_VERSION",
    "GOVERNANCE_DELTA_CLASSIFICATION",
    "GOVERNANCE_DELTA_SCOPE",
    "PAPER_PRIMARY_ROOT_ENV",
    "PREVIOUS_FINAL_TEST_EPOCH",
    "CONSUMED_EPOCH_SEAL_STATUS",
    "CANONICAL_STAGE_NODE_CONTRACT",
    "FORMAL_EXECUTOR_RECONCILIATION",
    "PHASE7_VOLATILE_OUTPUT_PREFIXES",
    "PRE_OPEN_REPORT_PATH",
    "PRE_OPEN_SCHEMA_VERSION",
    "build_execution_freeze",
    "pre_open_gate",
    "validate_execution_freeze",
    "write_execution_freeze",
]
