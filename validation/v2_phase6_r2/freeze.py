"""Build and validate the Freeze R2 correction registry and report.

The original Phase 6 registry and annotated tag are immutable inputs. R2 is a
narrow authority-only reconciliation layered on top of them; it does not
rewrite the Phase 6 bytes and does not change any scientific parameter.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validation.v2_phase6_r2.common import (  # noqa: E402
    BASE_REGISTRY_PATH,
    BASE_TAG,
    PROJECT_ROOT,
    R2_REGISTRY_PATH,
    R2_TAG,
    R2Error,
    RECONCILIATION_PATH,
    REPORT_PATH,
    file_hash,
    payload_hash,
    read_json,
    relative_path,
)

from validation.v2_phase6_r2.reconcile import (  # noqa: E402
    FORMAL_SOLVER,
    OBJECTIVE_PERTURBATION,
    PARITY_ORACLE,
    STATUS_PASS,
    TIE_RULE,
    TOLERANCE,
    TOLERANCE_NAME,
    build_reconciliation_report,
)


SCHEMA_VERSION = "V2_SCIENTIFIC_FREEZE_R2"
ARTIFACT_KIND = "SCIENTIFIC_FREEZE_R2_CORRECTION"
STATUS_ACTIVE = "SCIENTIFIC_FREEZE_R2_ACTIVE"
FREEZE_COMMIT = "PENDING_R2_ACTIVATION_COMMIT"
FREEZE_COMMIT_SEMANTICS = "R2_ACTIVATION_COMMIT_RESOLVED_BY_ANNOTATED_TAG"
TAG_TARGET = "RESOLVED_AFTER_COMMIT"
R2_COMMIT_MESSAGE = "v2(phase6-r2): set highs as formal stage2 solver"
BASE_REGISTRY_FILE_SHA256 = (
    "sha256:2b89976da5158f0fee87222daef33a8b3b617d61ece94ade00a001869134afdd"
)
BASE_REGISTRY_ARTIFACT_HASH = (
    "sha256:3828b17ac93cbaf81579e865faf32ed9547a1d540a65d3679ab4248a2bf17e2d"
)
BASE_REGISTRY_BLOB_SHA256 = (
    "sha256:a8c43beffbdefaf2ca9c573ec7730ae9a2f55ce3"
)
BASE_TAG_OBJECT = "35d5fe1896dd9e17be92bec601f87ec33adb4d56"
BASE_TAG_TARGET_COMMIT = "d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1"


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise R2Error(f"{code}:{detail}")


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(text.encode("utf-8"))
    temporary.replace(path)


def _assert_base_identity() -> dict[str, Any]:
    base = read_json(BASE_REGISTRY_PATH)
    _require(
        file_hash(BASE_REGISTRY_PATH) == BASE_REGISTRY_FILE_SHA256,
        "R2_BASE_REGISTRY_FILE_HASH_MISMATCH",
        file_hash(BASE_REGISTRY_PATH),
    )
    _require(
        payload_hash(base) == BASE_REGISTRY_ARTIFACT_HASH,
        "R2_BASE_REGISTRY_ARTIFACT_HASH_MISMATCH",
        payload_hash(base),
    )
    blob = _git("hash-object", relative_path(BASE_REGISTRY_PATH))
    _require(
        f"sha256:{blob}" == BASE_REGISTRY_BLOB_SHA256,
        "R2_BASE_REGISTRY_BLOB_HASH_MISMATCH",
        blob,
    )
    _require(
        _git("rev-parse", f"{BASE_TAG}^{{tag}}") == BASE_TAG_OBJECT,
        "R2_BASE_TAG_OBJECT_MISMATCH",
    )
    _require(
        _git("rev-parse", f"{BASE_TAG}^{{commit}}") == BASE_TAG_TARGET_COMMIT,
        "R2_BASE_TAG_TARGET_MISMATCH",
    )
    return base


def _reconciliation_payload() -> dict[str, Any]:
    if not RECONCILIATION_PATH.is_file():
        raise R2Error("R2_RECONCILIATION_REPORT_MISSING")
    report = read_json(RECONCILIATION_PATH)
    _require(
        report.get("status") == STATUS_PASS,
        "R2_RECONCILIATION_NOT_PASS",
        report.get("status"),
    )
    _require(
        report.get("artifact_hash") == payload_hash(report),
        "R2_RECONCILIATION_ARTIFACT_HASH_MISMATCH",
    )
    return report


def build_registry_payload() -> dict[str, Any]:
    """Return the deterministic R2 registry payload."""

    base = _assert_base_identity()
    reconciliation = _reconciliation_payload()
    payload = copy.deepcopy(base)
    payload.pop("artifact_hash", None)

    payload.update(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_kind": ARTIFACT_KIND,
            "status": STATUS_ACTIVE,
            "not_a_formal_freeze": False,
            "phase": "PHASE_6_R2",
            "freeze_commit": FREEZE_COMMIT,
            "freeze_commit_semantics": FREEZE_COMMIT_SEMANTICS,
            "complete_frozen_repository_state": "ANNOTATED_TAG_RESOLUTION",
            "activation_owner": "PHASE6_R2_AUTHORITY_RECONCILIATION",
            "activation_tag": R2_TAG,
            "activation_tag_target": TAG_TARGET,
            "formal_solver": FORMAL_SOLVER,
            "parity_oracle": PARITY_ORACLE,
            "objective_perturbation": OBJECTIVE_PERTURBATION,
            "long_term_deviation": False,
        }
    )
    payload["activation_state"] = {
        "parent_activation_tag": BASE_TAG,
        "parent_tag_object": BASE_TAG_OBJECT,
        "parent_tag_target_commit": BASE_TAG_TARGET_COMMIT,
        "parent_registry_file_sha256": BASE_REGISTRY_FILE_SHA256,
        "parent_registry_artifact_hash": BASE_REGISTRY_ARTIFACT_HASH,
        "parent_registry_blob_sha256": BASE_REGISTRY_BLOB_SHA256,
        "parent_registry_bytes_rewritten": False,
        "activation_tag": R2_TAG,
        "activation_tag_target": TAG_TARGET,
        "complete_state_authority": "ANNOTATED_TAG_RESOLUTION",
        "authority_scope": "STAGE2_SOLVER_AUTHORITY_ONLY",
        "phase7_entered": False,
        "m1_retrained": False,
        "scientific_outputs_recomputed": False,
        "metadata_only_correction": False,
    }
    payload["phase6_r2_activation"] = {
        "phase": "PHASE_6_R2_FREEZE_AUTHORITY_RECONCILIATION",
        "status": STATUS_ACTIVE,
        "commit_message": R2_COMMIT_MESSAGE,
        "activation_tag": R2_TAG,
        "activation_tag_target": TAG_TARGET,
        "complete_frozen_repository_state": "ANNOTATED_TAG_RESOLUTION",
        "authority_scope": "STAGE2_SOLVER_AUTHORITY_ONLY",
        "decision_equivalence_required": True,
        "action_disagreements_allowed": False,
        "final_test_access_total": 1,
        "current_freeze_run_increment": 0,
        "new_final_test_execution": False,
        "phase_7_entered": False,
        "m1_retrained": False,
        "scientific_outputs_recomputed": False,
    }
    payload["parent_freeze"] = {
        "tag": BASE_TAG,
        "tag_object": BASE_TAG_OBJECT,
        "tag_target_commit": BASE_TAG_TARGET_COMMIT,
        "registry_path": relative_path(BASE_REGISTRY_PATH),
        "registry_file_sha256": BASE_REGISTRY_FILE_SHA256,
        "registry_artifact_hash": BASE_REGISTRY_ARTIFACT_HASH,
        "registry_blob_sha256": BASE_REGISTRY_BLOB_SHA256,
        "immutable": True,
    }
    payload["stage2_solver"] = {
        "formal_path": FORMAL_SOLVER,
        "formal_solver": FORMAL_SOLVER,
        "parity_backend": PARITY_ORACLE,
        "parity_oracle": PARITY_ORACLE,
        "parity_scope": "ALL_AVAILABLE_NON_TEST_STAGE2_VALIDATION_CORPUS",
        "objective_perturbation": OBJECTIVE_PERTURBATION,
        "long_term_deviation": False,
        "tie_rule": TIE_RULE,
        "tie_rule_implementation": (
            "two-stage lexicographic HiGHS solve: primary objective J, then "
            "minimize u subject to J <= J* + tau"
        ),
        "numerical_comparison_tolerance": {
            "name": TOLERANCE_NAME,
            "value": TOLERANCE,
            "scientific_parameter": False,
            "role": "SOLVER_NUMERICAL_COMPARISON_ONLY",
        },
    }
    payload["r2_authority_reconciliation"] = {
        "artifact": {
            "path": relative_path(RECONCILIATION_PATH),
            "file_sha256": file_hash(RECONCILIATION_PATH),
            "artifact_hash": reconciliation["artifact_hash"],
            "status": reconciliation["status"],
        },
        "scope": "STAGE2_SOLVER_AUTHORITY_ONLY",
        "formal_solver": FORMAL_SOLVER,
        "parity_oracle": PARITY_ORACLE,
        "objective_perturbation": OBJECTIVE_PERTURBATION,
        "long_term_deviation": False,
        "tie_rule": TIE_RULE,
        "tolerance": {
            "name": TOLERANCE_NAME,
            "value": TOLERANCE,
            "scientific_parameter": False,
        },
        "counts": reconciliation["counts"],
        "error_summary": reconciliation["error_summary"],
        "action_disagreements_allowed": False,
        "decision_equivalent_to_pre_r2_finite_grid_rule": True,
    }
    payload["r2_authority_sources"] = {
        relative_path(PROJECT_ROOT / "model" / "M3" / "solver.py"): file_hash(
            PROJECT_ROOT / "model" / "M3" / "solver.py"
        ),
        relative_path(PROJECT_ROOT / "model" / "M3" / "stage2.py"): file_hash(
            PROJECT_ROOT / "model" / "M3" / "stage2.py"
        ),
        relative_path(
            PROJECT_ROOT / "model" / "common" / "decision_contracts.py"
        ): file_hash(PROJECT_ROOT / "model" / "common" / "decision_contracts.py"),
        relative_path(
            PROJECT_ROOT / "validation" / "m3_enumeration_highs_parity.py"
        ): file_hash(
            PROJECT_ROOT / "validation" / "m3_enumeration_highs_parity.py"
        ),
        relative_path(
            PROJECT_ROOT / "validation" / "v2_phase6_r2" / "reconcile.py"
        ): file_hash(
            PROJECT_ROOT / "validation" / "v2_phase6_r2" / "reconcile.py"
        ),
    }
    payload["r2_final_test_accounting"] = {
        "historical_access_total": 1,
        "current_freeze_run_increment": 0,
        "current_total": 1,
        "new_final_test_execution": False,
        "phase_7_entered": False,
        "final_test_path_touched": False,
    }
    payload["final_test_access_count"] = 1
    payload["final_test_run_increment"] = 0
    payload["new_final_test_execution"] = False
    payload["phase_7_entered"] = False
    payload["artifact_hash"] = payload_hash(payload)
    return payload


def build_report_text(
    registry: Mapping[str, Any],
    *,
    registry_file_sha256: str,
    reconciliation: Mapping[str, Any],
) -> str:
    counts = reconciliation["counts"]
    errors = reconciliation["error_summary"]
    return (
        "# AirSlot V2 Freeze R2 Correction Report\n"
        "\n"
        "## Status\n"
        "\n"
        "- Phase: `PHASE_6_R2_FREEZE_AUTHORITY_RECONCILIATION`.\n"
        "- Status: `SCIENTIFIC_FREEZE_R2_ACTIVE`.\n"
        "- Scope: `STAGE2_SOLVER_AUTHORITY_ONLY`.\n"
        "- Parent freeze: `v2-scientific-freeze` "
        f"(`{BASE_TAG_OBJECT}` -> `{BASE_TAG_TARGET_COMMIT}`).\n"
        "- Parent registry remains byte-identical: "
        f"`{BASE_REGISTRY_FILE_SHA256}`.\n"
        "- R2 activation tag: `v2-scientific-freeze-r2`.\n"
        "- Activation tag target: `RESOLVED_AFTER_COMMIT`; the complete "
        "R2 frozen repository state is defined by annotated tag resolution.\n"
        f"- R2 registry artifact hash: `{registry['artifact_hash']}`.\n"
        f"- R2 registry file SHA-256: `{registry_file_sha256}`.\n"
        f"- Reconciliation artifact hash: `{reconciliation['artifact_hash']}`.\n"
        "\n"
        "## Authority Reconciliation\n"
        "\n"
        f"- Formal solver: `{FORMAL_SOLVER}`.\n"
        f"- Parity oracle: `{PARITY_ORACLE}`.\n"
        f"- Objective perturbation: `{OBJECTIVE_PERTURBATION}`.\n"
        "- Long-term deviation: `false`.\n"
        f"- Tie rule: `{TIE_RULE}`.\n"
        "- Tie implementation: two-stage lexicographic HiGHS solve; first "
        "minimize `J`, then minimize `u` subject to `J <= J* + tau`.\n"
        f"- `{TOLERANCE_NAME} = {TOLERANCE}`; it is "
        "`NOT_A_SCIENTIFIC_PARAMETER`.\n"
        "- Diagnostics `tie_break_applied` and `near_tie_candidate_count` are "
        "computational audit fields only.\n"
        "\n"
        "## Decision Equivalence\n"
        "\n"
        "- Corpus: all available non-Test Stage-II validation fixtures, "
        "closed over their admissible specification grid.\n"
        f"- Actionable cases: `{counts['actionable_cases']}`.\n"
        f"- Typed non-actionable cases: "
        f"`{counts['typed_non_actionable_cases']}`.\n"
        f"- Action disagreements: `{counts['action_disagreements']}`.\n"
        f"- Tie-break cases: `{counts['tie_break_cases']}`.\n"
        f"- Maximum near-tie candidate count: "
        f"`{counts['near_tie_candidate_count_max']}`.\n"
        f"- Maximum objective absolute error: "
        f"`{errors['objective_absolute_error_max']}` "
        f"(tolerance `{errors['objective_absolute_error_tolerance']}`).\n"
        f"- Maximum recoverable-value absolute error: "
        f"`{errors['recoverable_value_absolute_error_max']}` "
        f"(tolerance "
        f"`{errors['recoverable_value_absolute_error_tolerance']}`).\n"
        "- Action equality is exact; objective and `V` parity use only the "
        "declared numerical comparison tolerance.\n"
        "- TAXI/COMP remain `NOT_ACTIONABLE`, singleton action set `{0}`, "
        "solver `NOT_RUN`, and undefined recoverable value.\n"
        "\n"
        "## Boundary\n"
        "\n"
        "- No scientific parameter, estimand, feasible set, state transition, "
        "consequence definition, objective, or evaluation population changed.\n"
        "- M1 was not retrained and no scientific output was recomputed.\n"
        "- No Final-Test path was read or written; historical access total "
        "remains `1`, current R2 increment is `0`.\n"
        "- Phase 7 Gate B was not entered; human release is still required.\n"
        "- The original Phase 6 registry and `v2-scientific-freeze` tag remain "
        "immutable.\n"
    )


def write_all() -> dict[str, Any]:
    reconciliation = _reconciliation_payload()
    registry = build_registry_payload()
    registry_text = _json_text(registry)
    _write_text(R2_REGISTRY_PATH, registry_text)
    registry_file_sha256 = _sha256_bytes(registry_text.encode("utf-8"))
    report_text = build_report_text(
        registry,
        registry_file_sha256=registry_file_sha256,
        reconciliation=reconciliation,
    )
    _write_text(REPORT_PATH, report_text)
    return {
        "status": STATUS_ACTIVE,
        "registry_path": str(R2_REGISTRY_PATH),
        "registry_file_sha256": registry_file_sha256,
        "registry_artifact_hash": registry["artifact_hash"],
        "report_path": str(REPORT_PATH),
        "reconciliation_artifact_hash": reconciliation["artifact_hash"],
        "counts": reconciliation["counts"],
    }


def check_all() -> dict[str, Any]:
    reconciliation = _reconciliation_payload()
    registry = build_registry_payload()
    registry_text = _json_text(registry)
    expected_registry_sha256 = _sha256_bytes(registry_text.encode("utf-8"))
    failures: list[str] = []
    if not R2_REGISTRY_PATH.is_file():
        failures.append("R2_REGISTRY_MISSING")
    elif R2_REGISTRY_PATH.read_bytes() != registry_text.encode("utf-8"):
        failures.append("R2_REGISTRY_BYTES_MISMATCH")
    expected_report = build_report_text(
        registry,
        registry_file_sha256=expected_registry_sha256,
        reconciliation=reconciliation,
    )
    if not REPORT_PATH.is_file():
        failures.append("R2_REPORT_MISSING")
    elif REPORT_PATH.read_bytes() != expected_report.encode("utf-8"):
        failures.append("R2_REPORT_BYTES_MISMATCH")
    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "registry_file_sha256": expected_registry_sha256,
        "registry_artifact_hash": registry["artifact_hash"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        result = write_all()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = check_all()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_KIND",
    "BASE_REGISTRY_ARTIFACT_HASH",
    "BASE_REGISTRY_BLOB_SHA256",
    "BASE_REGISTRY_FILE_SHA256",
    "BASE_TAG_OBJECT",
    "BASE_TAG_TARGET_COMMIT",
    "FREEZE_COMMIT",
    "FREEZE_COMMIT_SEMANTICS",
    "R2_COMMIT_MESSAGE",
    "SCHEMA_VERSION",
    "STATUS_ACTIVE",
    "TAG_TARGET",
    "build_registry_payload",
    "build_report_text",
    "check_all",
    "write_all",
]
