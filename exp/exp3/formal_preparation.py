"""Development-only preparation for the current Exp3 formal execution contract."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id

from .protocol import (
    EXP3A_ONE_SHOT,
    EXP3A_ROLLING,
    EXP3B_STATE_LAG_10,
    EXP3B_STATE_LAG_5,
    EXP3B_SYNC,
    variant_definition,
)


FORMAL_VARIANT_IDS = (
    "FULL_CHAIN",
    "MODULE_REMOVAL_M1",
    "MODULE_REMOVAL_M2",
    "MODULE_REMOVAL_M3",
    "MODULE_REMOVAL_M4",
    "ROLLING",
    "ONE_SHOT",
    "SYNC",
    "LAG_5",
    "LAG_10",
)
_TEMPORAL_VARIANTS = {
    "ROLLING": EXP3A_ROLLING,
    "ONE_SHOT": EXP3A_ONE_SHOT,
    "SYNC": EXP3B_SYNC,
    "LAG_5": EXP3B_STATE_LAG_5,
    "LAG_10": EXP3B_STATE_LAG_10,
}
_CHAIN = ("PRE", "M1", "M2", "M3", "M4", "ACTION_SET")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "artifact_hash": content_id(payload)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise RuntimeError(f"EXP3_FORMAL_PREPARATION_OUTPUT_CONFLICT:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _inputs(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    paths = {
        "m1_binding": root / "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
        "m1_freeze": root / "artifacts/diagnostics/m1_v2_final_development_freeze/M1_V2_FINAL_FREEZE_MANIFEST.json",
        "exp2_manifest": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_EXECUTION_MANIFEST.json",
        "exp2_lineage": root / "artifacts/experiment/exp2_formal_development/EXP2_FORMAL_ARTIFACT_LINEAGE.json",
    }
    _require(all(path.is_file() for path in paths.values()), "EXP3_FORMAL_PREPARATION_INPUT_MISSING")
    return {name: (path, _load(path)) for name, path in paths.items()}


def _validate(inputs: dict[str, tuple[Path, dict[str, Any]]], root: Path) -> dict[str, Any]:
    binding = inputs["m1_binding"][1]
    freeze = inputs["m1_freeze"][1]
    exp2_manifest = inputs["exp2_manifest"][1]
    exp2_lineage = inputs["exp2_lineage"][1]
    checkpoint = root / binding["checkpoint"]["path"]
    _require(binding["status"] == "BOUND_FROZEN_M1_V2", "EXP3_M1_BINDING_NOT_FROZEN")
    _require(binding["model_id"] == "M1_V2_GRU_H32", "EXP3_M1_MODEL_NOT_H32")
    _require(checkpoint.is_file() and _hash(checkpoint) == binding["checkpoint"]["sha256"], "EXP3_M1_CHECKPOINT_HASH_MISMATCH")
    _require(freeze["status"] == "M1_V2_FINAL_DEVELOPMENT_FREEZE_READY", "EXP3_M1_FREEZE_NOT_READY")
    _require(exp2_manifest["status"] == "EXP2_FORMAL_EXECUTION_COMPLETE", "EXP3_EXP2_BINDING_NOT_COMPLETE")
    _require(exp2_manifest["split"] == "DEVELOPMENT", "EXP3_EXP2_BINDING_NOT_DEVELOPMENT")
    _require(exp2_lineage["status"] == "BOUND_WITH_UNRESOLVED_UPSTREAM_GATES", "EXP3_EXP2_LINEAGE_STATUS_INVALID")
    for payload in (binding, freeze, exp2_manifest, exp2_lineage):
        safety = payload.get("safety", payload)
        _require(safety.get("FINAL_TEST_ACCESS_COUNT", payload.get("FINAL_TEST_ACCESS_COUNT")) == 0, "EXP3_FINAL_TEST_ACCESS_NONZERO")
        _require(safety.get("PAPER_FULL_RUN", payload.get("PAPER_FULL_RUN")) is False, "EXP3_PAPER_FULL_TRUE")
    _require(exp2_manifest["safety"]["FULL"] is False, "EXP3_EXP2_FULL_TRUE")
    return {
        "dataset": exp2_manifest["dataset"],
        "split": exp2_manifest["split"],
        "m1_model_id": binding["model_id"],
        "m1_checkpoint_sha256": binding["checkpoint"]["sha256"],
        "feature_schema_hash": binding["frozen_contracts"]["feature_schema_hash"],
        "cache_hash": binding["frozen_contracts"]["cache_hash"],
        "support_hash": binding["frozen_contracts"]["support_hash"],
        "loss_version": binding["frozen_contracts"]["loss_version"],
        "exp2_cohort_hash": exp2_lineage["cohort"]["cohort_hash"],
        "exp2_cohort_episode_count": exp2_lineage["cohort"]["episode_count"],
        "exp2_cohort_node_count": exp2_lineage["cohort"]["node_count"],
    }


def _variant_contracts() -> dict[str, dict[str, Any]]:
    contracts = {
        "FULL_CHAIN": {
            "variant_type": "FULL_CHAIN_CONTRACT",
            "changed_factor": "NONE",
            "required_modules": _CHAIN,
            "runtime_full": False,
            "meaning": "ALL_CURRENT_TYPED_STAGE_CONTRACTS_REQUIRED_NOT_EXECUTION_TIER_FULL",
        }
    }
    for module in ("M1", "M2", "M3", "M4"):
        contracts[f"MODULE_REMOVAL_{module}"] = {
            "variant_type": "MODULE_REMOVAL_CONTRACT",
            "changed_factor": f"REMOVE_{module}",
            "removed_module": module,
            "remaining_modules": tuple(item for item in _CHAIN if item != module),
            "removed_output_policy": "ABSTAIN_NO_SUBSTITUTION",
            "downstream_metrics": "NOT_RUN_NO_SYNTHETIC_PROXY",
            "zero_fill": False,
        }
    for public_id, protocol_id in _TEMPORAL_VARIANTS.items():
        definition = variant_definition(protocol_id)
        contract = {
            "variant_type": "TEMPORAL_PROCESS_CONTRACT",
            "protocol_variant_id": protocol_id,
            "subexperiment": definition["subexperiment"],
            "changed_factor": definition["changed_factor"],
            "fixed_modules": definition["fixed_factor"],
            "requires_full_chain": True,
        }
        if public_id == "ONE_SHOT":
            contract["anchor_rule"] = "FIRST_NODE_WITH_TWO_COMMON_RANKED_ACTIONS_INCLUDING_A00_AND_ONE_NON_A00"
            contract["anchor_fallback"] = "FORBIDDEN"
        elif public_id == "ROLLING":
            contract["refresh_rule"] = "EVERY_LEGAL_FIVE_MINUTE_DECISION_NODE"
            contract["prior_node_mutation"] = "FORBIDDEN"
        else:
            lag = {"SYNC": 0, "LAG_5": 5, "LAG_10": 10}[public_id]
            contract["state_vintage_lag_minutes"] = lag
            contract["current_direct_information"] = "FIXED"
            contract["future_state_read"] = "FORBIDDEN"
        contracts[public_id] = contract
    return contracts


def _lineage_schema() -> dict[str, Any]:
    return _artifact({
        "schema_version": "EXP3_FORMAL_LINEAGE_SCHEMA_V1",
        "status": "READY_FOR_FROZEN_INPUT_BINDING",
        "required_identity_fields": (
            "episode_id", "decision_node_id", "decision_time_utc", "information_cutoff_utc",
            "variant_id", "cohort_hash", "feature_schema_hash", "support_hash",
            "m1_checkpoint_sha256", "m1_scenario_artifact_hash", "m2_consequence_artifact_hash",
            "m3_action_set_hash", "m3_response_rule_hashes", "m4_mapping_hash", "m4_risk_policy_hash",
        ),
        "temporal_fields": (
            "state_vintage_node_id", "state_vintage_information_cutoff_utc",
            "state_vintage_lag_minutes", "refresh_index", "one_shot_anchor_node_id",
        ),
        "support_fields": (
            "m1_support_state", "m2_component_support", "m3_response_support",
            "m4_ranking_authority", "not_run_reason",
        ),
        "invariants": (
            "INFORMATION_CUTOFF_NOT_AFTER_DECISION_TIME",
            "LAGGED_STATE_NEVER_READS_CURRENT_OR_FUTURE_STATE",
            "ONE_SHOT_HAS_NO_FALLBACK_ANCHOR",
            "ALL_TEMPORAL_VARIANTS_SHARE_FROZEN_CHAIN_IDENTITIES",
            "MODULE_REMOVAL_OUTPUT_IS_ABSTAIN_NOT_ZERO",
            "NO_SYNTHETIC_DOWNSTREAM_METRICS",
        ),
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "FULL": False,
            "PAPER_FULL_RUN": False,
        },
    })


def _readiness(gates: dict[str, Any]) -> dict[str, Any]:
    blockers = tuple(item["status"] for item in gates.values() if str(item["status"]).startswith("BLOCKED_"))
    return _artifact({
        "schema_version": "EXP3_FORMAL_EXECUTION_READINESS_V1",
        "status": "EXP3_FORMAL_EXECUTION_READY",
        "preparation_status": "READY",
        "execution_status": "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES",
        "shared_blockers": blockers,
        "metric_policy": "NOT_RUN_UNTIL_TYPED_CHAIN_ARTIFACTS_ARE_BOUND_NO_ZERO_FILL_NO_SYNTHETIC_DOWNSTREAM_METRICS",
        "variant_readiness": {
            variant: {
                "status": "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES",
                "requires_execution_authorization": True,
            }
            for variant in FORMAL_VARIANT_IDS
        },
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "FULL": False,
            "PAPER_FULL_RUN": False,
        },
    })


def prepare_formal_execution(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/exp3_formal_execution_preparation").resolve()
    inputs = _inputs(root)
    fixed = _validate(inputs, root)
    gates = inputs["exp2_lineage"][1]["gates"]
    contracts = _artifact({
        "schema_version": "EXP3_FORMAL_VARIANT_CONTRACTS_V1",
        "status": "READY",
        "variants": _variant_contracts(),
        "fixed_contract": fixed,
        "safety": {"FINAL_TEST_ACCESS_COUNT": 0, "FULL": False, "PAPER_FULL_RUN": False},
    })
    contracts_path = output_root / "EXP3_FORMAL_VARIANT_CONTRACTS.json"
    _write(contracts_path, contracts)
    schema = _lineage_schema()
    schema_path = output_root / "EXP3_FORMAL_LINEAGE_SCHEMA.json"
    _write(schema_path, schema)
    readiness = _readiness(gates)
    readiness_path = output_root / "EXP3_FORMAL_EXECUTION_READINESS_REPORT.json"
    _write(readiness_path, readiness)
    manifest = _artifact({
        "schema_version": "EXP3_FORMAL_EXECUTION_MANIFEST_V1",
        "status": "EXP3_FORMAL_EXECUTION_READY",
        "execution_scope": "DEVELOPMENT_PREPARATION_NON_FULL",
        "fixed_contract": fixed,
        "variants": FORMAL_VARIANT_IDS,
        "m1_binding": {"model_id": "M1_V2_GRU_H32", "modified": False},
        "shared_gates_source": _relative(inputs["exp2_lineage"][0], root),
        "outputs": {
            "variant_contracts": _relative(contracts_path, root),
            "lineage_schema": _relative(schema_path, root),
            "execution_readiness_report": _relative(readiness_path, root),
        },
        "safety": {
            "M1_TRAINING_RUNS_THIS_PREPARATION": 0,
            "TUNING_RUNS_THIS_PREPARATION": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "FULL": False,
            "PAPER_FULL_RUN": False,
        },
    })
    manifest_path = output_root / "EXP3_FORMAL_EXECUTION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path,
        "variant_contracts": contracts_path,
        "lineage_schema": schema_path,
        "readiness": readiness_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the gated Exp3 Development execution contract.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    prepare_formal_execution(root=Path(__file__).resolve().parents[2], output_root=args.output_root)
    print("EXP3_FORMAL_EXECUTION_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
