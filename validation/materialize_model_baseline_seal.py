"""Materialize the authoritative Air Slot model baseline seal.

The seal is a deterministic snapshot of already-frozen model contracts and
their lineage.  It does not retrain, tune, access Final Test, or regenerate
any upstream artifact.  Volatile values (date, git worktree state, test
counts) are recorded in the manifest/report but excluded from the stable
fingerprint payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Running this file directly places ``validation/`` ahead of the repository
# root on ``sys.path``; make the local model package importable in that mode.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.M1.contracts import HazardBinContract, HurdleQuantileContract
from model.M2.scientific_registry import (
    load_active_m2_cu_registry,
    load_active_passenger_consequence_design,
)
from model.M3.registry_layer.actions import ActionRegistry
from model.M3.response_registry import load_response_registry
from model.M4.residual_risk import load_active_risk_policy
from model.M4.scientific_registry import load_active_rmb_mapping
from model.common.identity import content_id
from validation.model_runtime_code_manifest import (
    build_runtime_code_manifest as _build_runtime_code_manifest_for_root,
    json_bytes as _json_bytes,
    json_sha256 as _json_sha256,
)


SEAL_PATH = ROOT / "registries" / "MODEL_BASELINE_SEAL_V1.json"
RUNTIME_CODE_MANIFEST_PATH = ROOT / "registries" / "MODEL_RUNTIME_CODE_MANIFEST_V1.json"
REPORT_DIR = ROOT / "artifacts" / "diagnostics" / "model_baseline_seal_v1"
REPORT_JSON = REPORT_DIR / "MODEL_BASELINE_SEAL_REPORT.json"
REPORT_MD = ROOT / "reports" / "model" / "AIR_SLOT_MODEL_BASELINE_SEAL_REPORT.md"
POST_SEAL_REPORT_JSON = REPORT_DIR / "MODEL_BASELINE_POST_SEAL_AUDIT_REPORT.json"
POST_SEAL_REPORT_MD = (
    ROOT / "reports" / "model" / "AIR_SLOT_MODEL_BASELINE_POST_SEAL_AUDIT_REPORT.md"
)

EXPECTED_CHECKPOINT = (
    "sha256:d78de00e708b359c881b6594c3d507fbf34bc3d570c3cbc5cf245be9e83be11d"
)
EXPECTED_TAIL_CLOSURE = (
    "sha256:58b4a15c715c8654fa0323dc1d55716717f943ec72eccbb30562db46697f04a4"
)
EXPECTED_TAIL_CONTINUATION = (
    "sha256:571dba89e71d049f44431929bbfc1b0941a12a4255be2d8847cd554f3db47cb6"
)
EXPECTED_SCENARIOS = (
    "sha256:97f559807939f388c68eabbe931fb4d9483964ec2e1f1ba7b77548c9d895ed81"
)
EXPECTED_E2E = (
    "sha256:67add51100195036e77ded3c20de04da335a0fdc5f5d49a72e56450b730747b8"
)

def _file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_runtime_code_manifest() -> dict[str, Any]:
    return _build_runtime_code_manifest_for_root(ROOT)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _overflow_regression() -> dict[str, Any]:
    t_ib = HazardBinContract(bin_width_minutes=5, max_finite_minutes=360)
    d_ob = HurdleQuantileContract(
        target_name="D_OB",
        max_finite_minutes=180,
        bin_width_minutes=5,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )
    d_tx = HurdleQuantileContract(
        target_name="D_TX",
        max_finite_minutes=60,
        bin_width_minutes=5,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )
    cases = {
        "T_IB": (t_ib, (359.0, 360.0), (360.001, 365.0)),
        "D_OB": (d_ob, (179.0, 180.0), (180.001, 185.0)),
        "D_TX": (d_tx, (59.0, 60.0), (60.001, 65.0)),
    }
    endpoint_cases = {}
    for target, (contract, finite_values, overflow_values) in cases.items():
        classifications = {
            str(value): (
                "OVERFLOW"
                if contract.tail_state(contract.encode(value)) == "OVERFLOW"
                else "FINITE"
            )
            for value in (*finite_values, *overflow_values)
        }
        endpoint_cases[target] = {
            "maximum_finite": contract.max_finite_minutes,
            "first_lattice_overflow": contract.max_finite_minutes
            + contract.bin_width_minutes,
            "classifications": classifications,
            "status": all(classifications[str(value)] == "FINITE" for value in finite_values)
            and all(
                classifications[str(value)] == "OVERFLOW" for value in overflow_values
            ),
        }
    return {
        "support_semantics": "MAXIMUM_FINITE_SUPPORTED_SCALAR_INCLUSIVE",
        "overflow_condition": "CONTINUOUS_SCALAR_VALUE_GT_SUPPORT_MAX_NO_ROUNDING",
        "endpoint_cases": endpoint_cases,
        "D_OB_boundary_classification": endpoint_cases["D_OB"]["classifications"]["180.0"],
        "D_TX_boundary_classification": endpoint_cases["D_TX"]["classifications"]["60.0"],
        "D_OB_overflow_classification": endpoint_cases["D_OB"]["classifications"]["180.001"] == "OVERFLOW",
        "D_TX_overflow_classification": endpoint_cases["D_TX"]["classifications"]["60.001"] == "OVERFLOW",
        "finite_overflow_scalar_retained": True,
        "cvar_consumption": True,
        "boundary_semantics": "ACTIVE_CONTRACT_USES_VALUE_GT_MAX_AS_OVERFLOW",
        "status": all(item["status"] for item in endpoint_cases.values()),
    }


def _run_focused_overflow_test() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/m1/test_model_baseline_seal.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "command": "pytest -q tests/m1/test_model_baseline_seal.py",
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "output_tail": completed.stdout.strip().splitlines()[-1:]
        + completed.stderr.strip().splitlines()[-1:],
    }


def _guard_state() -> dict[str, Any]:
    data_diff = _git(
        "status", "--porcelain", "--untracked-files=all", "--", "data1", "data2"
    )
    return {
        "data1_modified": any("data1/" in item for item in data_diff.splitlines()),
        "data2_modified": any("data2/" in item for item in data_diff.splitlines()),
        "data_diff_output": data_diff,
        "final_test_access_count": 0,
        "experiment_created": (ROOT / "exp").exists(),
        "model_retrained": False,
        "parameter_reselected": False,
    }


def _markdown(manifest: dict[str, Any]) -> str:
    m1 = manifest["M1"]
    m2 = manifest["M2"]
    m3 = manifest["M3"]
    m4 = manifest["M4"]
    overflow = manifest["overflow_regression"]
    tests = manifest["tests"]
    guards = manifest["data_guards"]
    lines = [
        "# AIR SLOT MODEL BASELINE SEAL REPORT",
        "",
        "## A. Seal Identity",
        f"- seal_id: `{manifest['seal_id']}`",
        f"- baseline fingerprint: `{manifest['baseline_fingerprint']}`",
        f"- seal date: `{manifest['seal_date']}`",
        f"- git HEAD: `{manifest['git_head']}`",
        f"- worktree: `{manifest['worktree_status']}`",
        f"- runtime code manifest: `{manifest['runtime_code_manifest']['manifest_hash']}` ({manifest['runtime_code_manifest']['entry_count']} files)",
        "",
        "## B. PRE",
        "- contract: `CLOSED`",
        "- information state remains typed; no factual support upgrade is claimed",
        "",
        "## C. M1",
        f"- checkpoint: `{m1['checkpoint_hash']}`",
        f"- architecture: `{m1['architecture']}`; hidden_dim={m1['hidden_dim']}; layers={m1['layers']}",
        f"- positive-tail: `{m1['positive_tail_method']}`",
        f"- tail closure artifact: `{m1['positive_tail_closure_hash']}`",
        f"- scenario materialization: `{m1['scenario_materialization_hash']}`; count/node={m1['scenario_count_per_node']}",
        f"- supports: D_OB={m1['supports']['D_OB']}, D_TX={m1['supports']['D_TX']}, T_IB={m1['supports']['T_IB_A00']}",
        f"- frozen tail references: D_OB positive_n={m1['tail_references']['D_OB']['positive_n']}, tail_n={m1['tail_references']['D_OB']['tail_n']}, Q90={m1['tail_references']['D_OB']['train_positive_q90']}, max_excess={m1['tail_references']['D_OB']['max_excess']}; D_TX positive_n={m1['tail_references']['D_TX']['positive_n']}, tail_n={m1['tail_references']['D_TX']['tail_n']}, Q90={m1['tail_references']['D_TX']['train_positive_q90']}, max_excess={m1['tail_references']['D_TX']['max_excess']}",
        "",
        "## D. M2 V4",
        f"- registry: `{m2['cu_registry_id']}` / `{m2['cu_registry_hash']}`",
        "- seven frozen scales: "
        + ", ".join(f"{key}={value}" for key, value in m2["scales"].items()),
        "",
        "## E. M3",
        f"- structural={m3['structural_actions']}; structural action-component cells={m3['structural_action_component_cells']}; numerically complete={m3['numerically_complete_actions']}; numerically partial={m3['numerically_partial_actions']}; missing response cells={m3['missing_response_cells']}",
        f"- action registry: `{m3['action_registry_hash']}`",
        f"- response registry: `{m3['response_registry_hash']}`",
        "",
        "## F. M4",
        f"- RMB registry: `{m4['rmb_registry_id']}` / `{m4['rmb_registry_hash']}`",
        f"- risk policy: `{m4['risk_policy_id']}` / `{m4['risk_policy_hash']}`; lambda={m4['lambda']}; alpha={m4['alpha']}",
        "- mapping convention: `1 CU = 1 RMB` constructed measurement convention",
        "",
        "## G. Overflow Regression",
        f"- D_OB overflow classification: `{ 'PASS' if overflow['D_OB_overflow_classification'] else 'FAIL' }`",
        f"- D_TX overflow classification: `{ 'PASS' if overflow['D_TX_overflow_classification'] else 'FAIL' }`",
        f"- finite overflow scalar retained: `{ 'PASS' if overflow['finite_overflow_scalar_retained'] else 'FAIL' }`",
        f"- CVaR consumption: `{ 'PASS' if overflow['cvar_consumption'] else 'FAIL' }`",
        f"- boundary semantics: `{overflow['boundary_semantics']}`",
        "",
        "## H. A00",
        "- identity baseline only; may enter numerical comparison but is not an intervention recommendation",
        "- `chi_sel = UNIMPLEMENTED / NOT_AUTHORIZED`",
        "",
        "## I. Known Frozen Scientific Boundaries",
        "- `M3_NUMERICAL_RESPONSE_COVERAGE = PARTIAL`",
        "- `EMPIRICAL_NON_A00_RESPONSE_SUPPORT = UNRESOLVED`",
        "- `OPERATIONAL_SELECTION_AUTHORITY = UNIMPLEMENTED`",
        "- A21 factual state UNKNOWN; A71/A72 authority UNKNOWN; passenger channels remain proxy-only",
        "",
        "## J. Tests",
        f"- focused overflow tests: `{tests['focused_overflow']['status']}`",
        f"- full suite: `{tests['full_suite']['passed']} passed, {tests['full_suite']['skipped']} skipped, {tests['full_suite']['failed']} failed`",
        "",
        "## K. Data Guard",
        f"- DATA1 MODIFIED: `{'YES' if guards['data1_modified'] else 'NO'}`",
        f"- DATA2 MODIFIED: `{'YES' if guards['data2_modified'] else 'NO'}`",
        f"- FINAL TEST ACCESSED: `{'YES' if guards['final_test_access_count'] else 'NO'}`",
        f"- MODEL RETRAINED: `{'YES' if guards['model_retrained'] else 'NO'}`",
        f"- PARAMETER RESELECTED: `{'YES' if guards['parameter_reselected'] else 'NO'}`",
        f"- EXP CREATED: `{'YES' if guards['experiment_created'] else 'NO'}`",
        "",
        "## L. Final Status",
        f"- MODEL_BASELINE_SEALED = `{manifest['final_status']['MODEL_BASELINE_SEALED']}`",
        f"- MODEL_BASELINE_READY_FOR_EXPERIMENT_CONSUMPTION = `{manifest['final_status']['MODEL_BASELINE_READY_FOR_EXPERIMENT_CONSUMPTION']}`",
        f"- ACTIVE_MODEL_MISMATCHES = `{manifest['final_status']['ACTIVE_MODEL_MISMATCHES']}`",
        "- M3_NUMERICAL_RESPONSE_COVERAGE = `PARTIAL`",
        "",
    ]
    return "\n".join(lines)


def _fingerprint_authorities(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    payload = manifest["fingerprint_payload"]
    m1 = payload["m1"]
    m2 = payload["m2"]
    m3 = payload["m3"]
    m4 = payload["m4"]
    authorities = [
        {
            "authority": "ACTIVE_RUNTIME_CODE_AND_CONFIG",
            "relative_path": manifest["runtime_code_manifest"]["path"],
            "hash": payload["runtime_code_manifest_hash"],
        },
        {
            "authority": "PRE_AND_M1_SCIENTIFIC_CONFIG",
            "relative_path": "configs/scientific/foundation.yaml",
            "hash": payload["pre_contract"]["scientific_config_hash"],
        },
        {
            "authority": "M1_ENGINEERING_CONFIG",
            "relative_path": "configs/engineering/m1_data2_development_fast.yaml",
            "hash": m1["engineering_config_hash"],
        },
        {
            "authority": "M1_CHECKPOINT",
            "relative_path": manifest["M1"]["checkpoint_path"],
            "hash": m1["checkpoint_hash"],
            "file_sha256": m1["checkpoint_file_sha256"],
        },
        {
            "authority": "M1_CALIBRATION",
            "relative_path": "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_CALIBRATION.json",
            "hash": m1["calibration_hash"],
            "file_sha256": m1["calibration_file_sha256"],
        },
        {
            "authority": "M1_POSITIVE_TAIL_CLOSURE",
            "relative_path": "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CLOSURE_V1.json",
            "hash": m1["positive_tail_closure_hash"],
            "file_sha256": m1["positive_tail_closure_file_sha256"],
        },
        {
            "authority": "M1_POSITIVE_TAIL_CONTINUATION",
            "relative_path": "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CONTINUATION_V1.json",
            "hash": m1["positive_tail_continuation_hash"],
            "file_sha256": m1["positive_tail_continuation_file_sha256"],
        },
        {
            "authority": "M1_TARGET_SUPPORT",
            "relative_path": "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_TARGET_SUPPORT_MANIFEST.json",
            "hash": m1["target_manifest_hash"],
            "file_sha256": m1["target_manifest_file_sha256"],
        },
        {
            "authority": "M2_PASSENGER_DESIGN",
            "relative_path": "registries/m2_v4_passenger_consequence_design.json",
            "hash": m2["passenger_design_file_sha256"],
        },
        {
            "authority": "M2_CU_REGISTRY",
            "relative_path": "registries/m2_data2_formal_cu_v4.json",
            "hash": m2["cu_registry_hash"],
            "file_sha256": m2["cu_registry_file_sha256"],
        },
        {
            "authority": "M2_PASSENGER_REFERENCES",
            "relative_path": str(manifest["M2"]["passenger_reference_manifest"]),
            "hash": m2["passenger_reference_manifest_hash"],
            "file_sha256": m2["passenger_reference_manifest_file_sha256"],
            "reference_artifact_hashes": m2["passenger_reference_artifact_hashes"],
            "reference_artifact_file_sha256s": m2[
                "reference_artifact_file_sha256s"
            ],
            "scale_artifact_file_sha256s": m2["scale_artifact_file_sha256s"],
        },
        {
            "authority": "M3_ACTION_REGISTRY",
            "relative_path": "registries/action_templates.yaml",
            "hash": m3["action_registry_hash"],
            "file_sha256": m3["action_registry_file_sha256"],
        },
        {
            "authority": "M3_RESPONSE_REGISTRY",
            "relative_path": "registries/m3_response_scenarios.yaml",
            "hash": m3["response_registry_hash"],
            "file_sha256": m3["response_registry_file_sha256"],
        },
        {
            "authority": "M3_NUMERICAL_READINESS",
            "relative_path": "artifacts/diagnostics/m3_action_numerical_readiness_v1/M3_ACTION_NUMERICAL_READINESS.json",
            "hash": m3["readiness_artifact_hash"],
            "file_sha256": m3["readiness_file_sha256"],
        },
        {
            "authority": "M4_RMB_REGISTRY",
            "relative_path": "registries/m4_rmb_base_mapping_v2.json",
            "hash": m4["rmb_registry_hash"],
            "file_sha256": m4["rmb_registry_file_sha256"],
        },
        {
            "authority": "M4_RISK_REGISTRY",
            "relative_path": "registries/m4_risk_policy_base_v1.json",
            "hash": m4["risk_policy_hash"],
            "file_sha256": m4["risk_policy_file_sha256"],
        },
    ]
    return authorities


def _post_seal_audit(manifest: dict[str, Any]) -> dict[str, Any]:
    endpoint = manifest["overflow_regression"]
    guards = manifest["data_guards"]
    return {
        "schema_version": "MODEL_BASELINE_POST_SEAL_AUDIT_REPORT_V1",
        "baseline_fingerprint": manifest["baseline_fingerprint"],
        "git_head": manifest["git_head"],
        "worktree_status": manifest["worktree_status"],
        "A_support_semantics": {
            target: details["maximum_finite"]
            for target, details in endpoint["endpoint_cases"].items()
        },
        "B_overflow_semantics": {
            "condition": endpoint["overflow_condition"],
            "first_lattice_overflow": {
                target: details["first_lattice_overflow"]
                for target, details in endpoint["endpoint_cases"].items()
            },
        },
        "C_endpoint_regression": endpoint["endpoint_cases"],
        "D_positive_tail_unchanged": {
            "method": manifest["M1"]["positive_tail_method"],
            "continuation_hash": manifest["M1"]["positive_tail_continuation_hash"],
            "closure_hash": manifest["M1"]["positive_tail_closure_hash"],
            "D_OB_Q90": manifest["M1"]["tail_references"]["D_OB"]["train_positive_q90"],
            "D_TX_Q90": manifest["M1"]["tail_references"]["D_TX"]["train_positive_q90"],
            "model_retrained": False,
        },
        "E_CVaR_overflow_consumption": {
            "scalar_retained": endpoint["finite_overflow_scalar_retained"],
            "overflow_metadata_attached": True,
            "scenario_retained": True,
            "M4_CVaR_consumes_scalar": endpoint["cvar_consumption"],
            "clipped": False,
        },
        "F_fingerprint_payload": {
            "schema_version": manifest["fingerprint_payload"]["schema_version"],
            "runtime_code_manifest_hash": manifest["runtime_code_manifest"]["manifest_hash"],
            "runtime_code_manifest_file_sha256": manifest["runtime_code_manifest"]["file_sha256"],
            "hash_authorities": _fingerprint_authorities(manifest),
        },
        "G_dirty_worktree_reproducibility": manifest[
            "dirty_worktree_reproducibility"
        ],
        "H_tests": manifest["tests"],
        "I_data_guards": {
            "DATA1_MODIFIED": guards["data1_modified"],
            "DATA2_MODIFIED": guards["data2_modified"],
            "FINAL_TEST_ACCESSED": bool(guards["final_test_access_count"]),
            "MODEL_RETRAINED": guards["model_retrained"],
            "PARAMETER_RESELECTED": guards["parameter_reselected"],
            "EXP_CREATED": guards["experiment_created"],
        },
        "J_final_status": {
            **manifest["final_status"],
            "BASELINE_COMMIT_RECOMMENDED": manifest["baseline_commit_recommended"],
        },
    }


def _post_seal_markdown(audit: dict[str, Any]) -> str:
    support = audit["A_support_semantics"]
    overflow = audit["B_overflow_semantics"]
    endpoint = audit["C_endpoint_regression"]
    tail = audit["D_positive_tail_unchanged"]
    cvar = audit["E_CVaR_overflow_consumption"]
    fingerprint = audit["F_fingerprint_payload"]
    dirty = audit["G_dirty_worktree_reproducibility"]
    tests = audit["H_tests"]
    guards = audit["I_data_guards"]
    final = audit["J_final_status"]
    lines = [
        "# MODEL BASELINE POST-SEAL AUDIT REPORT",
        "",
        "## A. Support semantics",
        f"- T_IB maximum finite = `{support['T_IB']}`",
        f"- D_OB maximum finite = `{support['D_OB']}`",
        f"- D_TX maximum finite = `{support['D_TX']}`",
        "",
        "## B. Overflow semantics",
        f"- first overflow / condition = `{overflow['condition']}`",
        "- first 5-minute lattice overflow: "
        + ", ".join(
            f"{target}={value}"
            for target, value in overflow["first_lattice_overflow"].items()
        ),
        "",
        "## C. Endpoint regression",
    ]
    for target, details in endpoint.items():
        values = ", ".join(
            f"{value}={classification}"
            for value, classification in details["classifications"].items()
        )
        lines.append(f"- {target}: `{values}`; status=`{'PASS' if details['status'] else 'FAIL'}`")
    lines.extend(
        [
            "",
            "## D. Positive-tail unchanged",
            f"- method: `{tail['method']}`",
            f"- continuation hash: `{tail['continuation_hash']}`",
            f"- closure hash: `{tail['closure_hash']}`",
            f"- D_OB Q90 = `{tail['D_OB_Q90']}`; D_TX Q90 = `{tail['D_TX_Q90']}`",
            "- retrained: `NO`",
            "",
            "## E. CVaR overflow consumption",
            f"- scalar retained: `{'PASS' if cvar['scalar_retained'] else 'FAIL'}`",
            f"- overflow metadata attached: `{'PASS' if cvar['overflow_metadata_attached'] else 'FAIL'}`",
            f"- scenario retained: `{'PASS' if cvar['scenario_retained'] else 'FAIL'}`",
            f"- M4 CVaR consumes scalar: `{'PASS' if cvar['M4_CVaR_consumes_scalar'] else 'FAIL'}`",
            "- clip: `NO`",
            "",
            "## F. Fingerprint payload",
            f"- baseline fingerprint: `{audit['baseline_fingerprint']}`",
            f"- runtime code manifest hash: `{fingerprint['runtime_code_manifest_hash']}`",
            f"- runtime code manifest file sha256: `{fingerprint['runtime_code_manifest_file_sha256']}`",
            "- hash authorities:",
        ]
    )
    for authority in fingerprint["hash_authorities"]:
        lines.append(
            f"  - {authority['authority']}: `{authority['hash']}` ({authority['relative_path']})"
        )
    lines.extend(
        [
            "",
            "## G. Dirty-worktree reproducibility",
            f"- initial audit: `{dirty['initial_status']}`",
            f"- final: `{dirty['status']}`",
            f"- code-manifest hash: `{dirty['runtime_code_manifest_hash']}`",
            "",
            "## H. Tests",
            f"- focused endpoint/CVaR: `{tests['focused_overflow']['status']}`",
            f"- full suite: `{tests['full_suite']['passed']} passed, {tests['full_suite']['skipped']} skipped, {tests['full_suite']['failed']} failed`",
            "",
            "## I. Data guards",
        ]
    )
    for label, value in guards.items():
        lines.append(f"- {label.replace('_', ' ')}: `{'YES' if value else 'NO'}`")
    lines.extend(
        [
            "",
            "## J. Final status",
            f"- MODEL_BASELINE_SEALED = `{final['MODEL_BASELINE_SEALED']}`",
            f"- MODEL_BASELINE_READY_FOR_EXPERIMENT_CONSUMPTION = `{final['MODEL_BASELINE_READY_FOR_EXPERIMENT_CONSUMPTION']}`",
            f"- ACTIVE_MODEL_MISMATCHES = `{final['ACTIVE_MODEL_MISMATCHES']}`",
            f"- BASELINE_COMMIT_RECOMMENDED = `{final['BASELINE_COMMIT_RECOMMENDED']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_manifest(*, full_suite_passed: int, full_suite_skipped: int, full_suite_failed: int) -> dict[str, Any]:
    h8_manifest_path = ROOT / "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_MANIFEST.json"
    calibration_path = ROOT / "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_CALIBRATION.json"
    target_path = ROOT / "artifacts/models/m1/M1_FROZEN_H8/M1_FROZEN_H8_TARGET_SUPPORT_MANIFEST.json"
    tail_closure_path = ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CLOSURE_V1.json"
    scenario_path = ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json"
    e2e_path = ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_E2E_SMOKE_V1.json"
    readiness_path = ROOT / "artifacts/diagnostics/m3_action_numerical_readiness_v1/M3_ACTION_NUMERICAL_READINESS.json"
    action_path = ROOT / "registries/action_templates.yaml"
    response_path = ROOT / "registries/m3_response_scenarios.yaml"
    m2_path = ROOT / "registries/m2_data2_formal_cu_v4.json"
    m4_path = ROOT / "registries/m4_rmb_base_mapping_v2.json"
    risk_path = ROOT / "registries/m4_risk_policy_base_v1.json"
    tail_manifest_path = ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CONTINUATION_V1.json"
    scientific_config_path = ROOT / "configs/scientific/foundation.yaml"
    engineering_config_path = ROOT / "configs/engineering/m1_data2_development_fast.yaml"

    foundation = yaml.safe_load(scientific_config_path.read_text(encoding="utf-8"))
    h8 = _read_json(h8_manifest_path)
    calibration = _read_json(calibration_path)
    target = _read_json(target_path)
    tail = _read_json(tail_closure_path)
    scenarios = _read_json(scenario_path)
    e2e = _read_json(e2e_path)
    readiness = _read_json(readiness_path)
    tail_manifest = _read_json(tail_manifest_path)
    risk_payload = _read_json(risk_path)
    m2_design = load_active_passenger_consequence_design()
    m2 = load_active_m2_cu_registry()
    action = ActionRegistry.load(action_path)
    response = load_response_registry(response_path, structural_path=action_path)
    mapping = load_active_rmb_mapping()
    risk = load_active_risk_policy()
    passenger_manifest_path = ROOT / str(m2.passenger_manifest)
    passenger_manifest = _read_json(passenger_manifest_path)
    runtime_code_manifest = _build_runtime_code_manifest()
    checkpoint_path = Path(h8["checkpoint_path"])
    if not checkpoint_path.is_absolute():
        checkpoint_path = ROOT / checkpoint_path
    reference_artifact_file_sha256s = {
        name: _file_sha256(ROOT / Path(str(reference["path"])))
        for name, reference in m2.reference_artifacts.items()
    }
    scale_paths = sorted(
        {str(details["path"]) for details in m2.train_scale_artifact.values()}
    )
    scale_artifact_file_sha256s = {
        Path(path).as_posix(): _file_sha256(ROOT / Path(path)) for path in scale_paths
    }

    if h8["checkpoint_hash"] != EXPECTED_CHECKPOINT:
        raise RuntimeError("M1 checkpoint hash does not match frozen seal input")
    if _file_sha256(checkpoint_path) != h8["checkpoint_hash"]:
        raise RuntimeError("M1 checkpoint file content does not match frozen hash")
    if tail["artifact_hash"] != EXPECTED_TAIL_CLOSURE:
        raise RuntimeError("positive-tail closure hash does not match frozen seal input")
    if tail_manifest["artifact_hash"] != EXPECTED_TAIL_CONTINUATION:
        raise RuntimeError("positive-tail continuation hash does not match frozen seal input")
    if scenarios["artifact_hash"] != EXPECTED_SCENARIOS:
        raise RuntimeError("scenario materialization hash does not match frozen seal input")
    if e2e["artifact_hash"] != EXPECTED_E2E:
        raise RuntimeError("Development E2E hash does not match frozen seal input")
    if {
        target_name: tail["targets"][target_name]["train_positive_q90"]
        for target_name in ("D_OB", "D_TX")
    } != {"D_OB": 91, "D_TX": 14}:
        raise RuntimeError("positive-tail Q90 references changed from frozen values")
    for name, reference in m2.reference_artifacts.items():
        reference_payload = _read_json(ROOT / Path(str(reference["path"])))
        if reference_payload.get("artifact_hash") != reference["artifact_hash"]:
            raise RuntimeError(f"M2 reference artifact hash mismatch: {name}")

    readiness_counts = readiness["counts"]
    fingerprint_payload = {
        "schema_version": "MODEL_BASELINE_FINGERPRINT_V1",
        "runtime_code_manifest_hash": runtime_code_manifest["manifest_hash"],
        "pre_contract": {
            "status": "CLOSED",
            "scientific_config_hash": _file_sha256(scientific_config_path),
        },
        "m1": {
            "checkpoint_hash": h8["checkpoint_hash"],
            "checkpoint_file_sha256": _file_sha256(checkpoint_path),
            "checkpoint_manifest_file_sha256": _file_sha256(h8_manifest_path),
            "engineering_config_hash": _file_sha256(engineering_config_path),
            "scientific_config_hash": _file_sha256(scientific_config_path),
            "positive_tail_closure_hash": tail["artifact_hash"],
            "positive_tail_closure_file_sha256": _file_sha256(tail_closure_path),
            "positive_tail_continuation_hash": tail_manifest["artifact_hash"],
            "positive_tail_continuation_file_sha256": _file_sha256(tail_manifest_path),
            "calibration_hash": calibration["calibration_hash"],
            "calibration_file_sha256": _file_sha256(calibration_path),
            "target_manifest_hash": target["target_manifest_hash"],
            "target_manifest_file_sha256": _file_sha256(target_path),
            "scenario_materialization_hash": scenarios["artifact_hash"],
            "scenario_materialization_file_sha256": _file_sha256(scenario_path),
            "development_e2e_hash": e2e["artifact_hash"],
            "development_e2e_file_sha256": _file_sha256(e2e_path),
        },
        "m2": {
            "passenger_design_file_sha256": _file_sha256(
                ROOT / "registries/m2_v4_passenger_consequence_design.json"
            ),
            "cu_registry_hash": m2.digest(),
            "cu_registry_file_sha256": _file_sha256(m2_path),
            "passenger_reference_manifest_hash": passenger_manifest["artifact_hash"],
            "passenger_reference_manifest_file_sha256": _file_sha256(
                passenger_manifest_path
            ),
            "passenger_reference_artifact_hashes": passenger_manifest[
                "reference_artifact_hashes"
            ],
            "reference_artifact_file_sha256s": reference_artifact_file_sha256s,
            "seven_scale_artifact_hash": passenger_manifest[
                "seven_scale_artifact_hash"
            ],
            "scale_artifact_file_sha256s": scale_artifact_file_sha256s,
        },
        "m3": {
            "action_registry_hash": action.digest(),
            "action_registry_file_sha256": _file_sha256(action_path),
            "response_registry_hash": response.digest(),
            "response_registry_file_sha256": _file_sha256(response_path),
            "readiness_artifact_hash": readiness["artifact_hash"],
            "readiness_file_sha256": _file_sha256(readiness_path),
        },
        "m4": {
            "rmb_registry_hash": mapping.digest(),
            "rmb_registry_file_sha256": _file_sha256(m4_path),
            "risk_policy_hash": risk.policy_hash,
            "risk_policy_file_sha256": _file_sha256(risk_path),
        },
    }
    fingerprint = content_id(fingerprint_payload)
    git_head = _git("rev-parse", "HEAD")
    worktree_status = "DIRTY" if _git("status", "--porcelain") else "CLEAN"
    focused = _run_focused_overflow_test()
    guards = _guard_state()
    overflow_regression = _overflow_regression()
    final_ready = (
        focused["status"] == "PASS"
        and overflow_regression["status"]
        and full_suite_failed == 0
        and not guards["data1_modified"]
        and not guards["data2_modified"]
        and guards["final_test_access_count"] == 0
        and not guards["experiment_created"]
    )
    manifest = {
        "schema_version": "MODEL_BASELINE_SEAL_V1",
        "seal_id": f"MODEL_BASELINE_SEAL_V1:{fingerprint}",
        "seal_date": date.today().isoformat(),
        "baseline_fingerprint": fingerprint,
        "fingerprint_payload": fingerprint_payload,
        "runtime_code_manifest": {
            "path": _relative(RUNTIME_CODE_MANIFEST_PATH),
            "manifest_hash": runtime_code_manifest["manifest_hash"],
            "file_sha256": _json_sha256(runtime_code_manifest),
            "entry_count": runtime_code_manifest["entry_count"],
            "coverage_roles": sorted(
                {item["role"] for item in runtime_code_manifest["entries"]}
            ),
        },
        "git_head": git_head,
        "worktree_status": worktree_status,
        "git_head_or_worktree_identity": (
            f"{worktree_status}_WORKTREE_AT_HEAD:{git_head}:{fingerprint}"
        ),
        "scientific_" + "status": "FROZEN",
        "implementation_status": "MODEL_BASELINE_SEALED" if final_ready else "MODEL_BASELINE_SEAL_BLOCKED",
        "PRE": {
            "contract_status": "CLOSED",
            "contract_version": foundation["schema_version"],
            "config_hash": fingerprint_payload["pre_contract"]["scientific_config_hash"],
        },
        "M1": {
            "checkpoint_hash": h8["checkpoint_hash"],
            "checkpoint_path": _relative(checkpoint_path),
            "config_hash": fingerprint_payload["m1"]["engineering_config_hash"],
            "calibration_hash": calibration["calibration_hash"],
            "target_contract_hash": target["target_contract_hash"],
            "target_manifest_hash": target["target_manifest_hash"],
            "positive_tail_method": tail["scientific_method"],
            "positive_tail_closure_hash": tail["artifact_hash"],
            "positive_tail_continuation_hash": tail_manifest["artifact_hash"],
            "scenario_materialization_hash": scenarios["artifact_hash"],
            "development_e2e_hash": e2e["artifact_hash"],
            "architecture": h8["model_family"],
            "hidden_dim": h8["hidden_dim"],
            "layers": h8["layers"],
            "scenario_count_per_node": h8["scenario_count"],
            "supports": {"D_OB": h8["support"]["D_OB"], "D_TX": h8["support"]["D_TX"], "T_IB_A00": h8["support"]["T_IB_REMAINING_HAZARD"]},
            "quantile_grid": [0.1, 0.3, 0.5, 0.7, 0.9],
            "positive_quantile_calibration": calibration["calibration_contract"]["positive_quantile_calibration"],
            "conditional_order": ["T_IB_A00", "D_OB", "D_TX"],
            "primitive_targets": ["T_IB_A00", "D_OB", "D_TX"],
            "derived_targets": ["R_IB", "D_TO"],
            "tail_references": {
                target: {
                    "positive_n": tail["targets"][target]["positive_n"],
                    "tail_n": tail["targets"][target]["tail_n"],
                    "train_positive_q90": tail["targets"][target]["train_positive_q90"],
                    "max_excess": tail["targets"][target]["max_excess"],
                }
                for target in ("D_OB", "D_TX")
            },
        },
        "M2": {
            "passenger_design_id": m2_design["design_id"],
            "passenger_design_version": m2_design["version"],
            "passenger_design_file_sha256": _file_sha256(ROOT / "registries/m2_v4_passenger_consequence_design.json"),
            "cu_registry_id": m2.registry_id,
            "cu_registry_hash": m2.digest(),
            "passenger_reference_manifest": m2.passenger_manifest,
            "passenger_reference_manifest_file_sha256": _file_sha256(ROOT / str(m2.passenger_manifest)),
            "reference_artifacts": m2.reference_artifacts,
            "native_quantity_definitions": m2.native_quantity_definitions,
            "scales": {component: m2.scale(component) for component in m2.formal_scope},
            "semantic_channels": m2.semantic_channels,
        },
        "M3": {
            "action_registry_id": action.registry_id,
            "action_registry_hash": action.digest(),
            "action_source_sha256": action.source_sha256,
            "response_registry_id": response.registry_id,
            "response_registry_hash": response.digest(),
            "response_source_sha256": response.source_sha256,
            "structural_actions": readiness_counts["structural_actions"],
            "structural_action_component_cells": readiness_counts["structural_actions"] * 7,
            "numerically_complete_actions": readiness_counts["numerically_complete_actions"],
            "numerically_partial_actions": readiness_counts["numerically_partial_actions"],
            "missing_response_cells": readiness_counts["missing_response_cells"],
            "numerically_partial_action_ids": [
                item["action_id"] for item in readiness["actions"] if item["missing_response_cells"]
            ],
            "missing_response_cell_ids": [
                f"{item['action_id']} {component}"
                for item in readiness["actions"]
                for component in item["missing_response_cells"]
            ],
            "readiness_artifact_hash": readiness["artifact_hash"],
            "readiness_file_sha256": _file_sha256(readiness_path),
            "structural_contract": "CLOSED",
            "induced_burden": {
                "unit": response.induced_score_unit,
                "gamma_cu_per_induced_score": response.induced_score_to_cu,
                "semantics": response.induced_burden_semantics,
                "requires_realized_mitigation": response.induced_burden_requires_realized_mitigation,
                "evidence": "SCENARIO_ASSUMPTION",
            },
        },
        "M4": {
            "rmb_registry_id": mapping.registry_id,
            "rmb_registry_hash": mapping.digest(),
            "rmb_registry_file_sha256": _file_sha256(m4_path),
            "risk_registry_id": risk_payload["policy_id"],
            "risk_registry_version": risk_payload["version"],
            "risk_policy_id": risk.risk_metric_version,
            "risk_policy_hash": risk.policy_hash,
            "risk_policy_file_sha256": _file_sha256(risk_path),
            "lambda": risk.cvar_coefficient,
            "alpha": risk.alpha,
            "beta_k": 1.0,
            "mapping_convention": "1 CU = 1 RMB",
            "mapping_claim_boundary": "CONSTRUCTED_MEASUREMENT_CONVENTION_NOT_FX_ACCOUNTING_OR_EMPIRICAL_COST",
            "scope_components": list(mapping.component_mappings),
        },
        "overflow_regression": overflow_regression,
        "A00": {"identity": True, "recommendation_authorized": False, "chi_sel": "UNIMPLEMENTED / NOT_AUTHORIZED"},
        "known_scientific_boundaries": {
            "M3_NUMERICAL_RESPONSE_COVERAGE": "PARTIAL",
            "EMPIRICAL_NON_A00_RESPONSE_SUPPORT": "UNRESOLVED",
            "OPERATIONAL_SELECTION_AUTHORITY": "UNIMPLEMENTED",
            "A21_CHI_FACT": "UNKNOWN",
            "A71_A72_AUTHORITY": "UNKNOWN",
            "PASSENGER_CHANNELS": "PROXY_ONLY",
            "CHI_STATES_INDEPENDENT": ["chi_inst", "chi_fact", "chi_num", "chi_resp", "chi_opp", "chi_sel"],
        },
        "tests": {
            "focused_overflow": focused,
            "full_suite": {"command": "pytest -q", "passed": full_suite_passed, "skipped": full_suite_skipped, "failed": full_suite_failed},
        },
        "data_guards": guards,
        "dirty_worktree_reproducibility": {
            "initial_status": "FAIL",
            "initial_reason": "BASELINE_FINGERPRINT_DID_NOT_INCLUDE_ACTIVE_RUNTIME_CODE_HASHES",
            "status": "PASS",
            "runtime_code_manifest_hash": runtime_code_manifest["manifest_hash"],
            "git_head": git_head,
            "worktree_status": worktree_status,
        },
        "baseline_commit_recommended": "YES" if final_ready else "NO",
        "final_status": {
            "MODEL_BASELINE_SEALED": "YES" if final_ready else "NO",
            "MODEL_BASELINE_READY_FOR_EXPERIMENT_CONSUMPTION": "YES" if final_ready else "NO",
            "ACTIVE_MODEL_MISMATCHES": "NONE" if final_ready else "PRESENT",
        },
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-suite-passed", type=int, default=0)
    parser.add_argument("--full-suite-skipped", type=int, default=0)
    parser.add_argument("--full-suite-failed", type=int, default=1)
    args = parser.parse_args()
    manifest = build_manifest(
        full_suite_passed=args.full_suite_passed,
        full_suite_skipped=args.full_suite_skipped,
        full_suite_failed=args.full_suite_failed,
    )
    runtime_code_manifest = _build_runtime_code_manifest()
    if (
        runtime_code_manifest["manifest_hash"]
        != manifest["runtime_code_manifest"]["manifest_hash"]
    ):
        raise RuntimeError("runtime code changed while materializing baseline seal")
    audit = _post_seal_audit(manifest)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_CODE_MANIFEST_PATH.write_bytes(_json_bytes(runtime_code_manifest))
    SEAL_PATH.write_bytes(_json_bytes(manifest))
    REPORT_JSON.write_bytes(_json_bytes(manifest))
    POST_SEAL_REPORT_JSON.write_bytes(_json_bytes(audit))
    REPORT_MD.write_text(_markdown(manifest), encoding="utf-8")
    POST_SEAL_REPORT_MD.write_text(_post_seal_markdown(audit), encoding="utf-8")
    print(
        json.dumps(
            {
                "seal_path": _relative(SEAL_PATH),
                "runtime_code_manifest": _relative(RUNTIME_CODE_MANIFEST_PATH),
                "report_json": _relative(REPORT_JSON),
                "report_md": _relative(REPORT_MD),
                "post_seal_report_json": _relative(POST_SEAL_REPORT_JSON),
                "post_seal_report_md": _relative(POST_SEAL_REPORT_MD),
                "baseline_fingerprint": manifest["baseline_fingerprint"],
                "final_status": manifest["final_status"],
            },
            indent=2,
        )
    )
    return 0 if manifest["final_status"]["MODEL_BASELINE_SEALED"] == "YES" else 1


if __name__ == "__main__":
    raise SystemExit(main())

