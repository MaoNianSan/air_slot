"""Official Exp1 Development entry point (OUTPUT_CONTRACT_20260823).

``--check`` runs a read-only preflight (frozen binding, required inputs,
variant contract) and validates the output-contract artifact set when a
summary exists.  ``--resume`` validates an existing full-Development
result.  Without flags, Exp1 full-Development executes from the frozen
Data2 Development cohort; missing inputs produce a BLOCK record instead
of fabricated output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from exp.common.full_development_inputs import materialize as materialize_inputs
from exp.common.full_development_scenarios import materialize as materialize_scenarios
from exp.common.official_execution import (
    load_json,
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_files,
)
from exp.exp1.full_state_metrics import compute_full_state_metrics
from exp.exp1.variants import (
    EXP1A_VARIANTS,
    EXP1B_PRINCIPAL_VARIANTS,
    EXP1B_SENSITIVITY_VARIANTS,
    EXP1_VARIANTS,
    EXP1_VARIANTS_WITH_SENSITIVITY,
    variant_definition,
)
from exp.reporting.output_contract import (
    OUTPUT_ROOTS,
    validate_artifacts,
    write_experiment_artifacts,
)
from model.common.errors import ContractError
from model.common.identity import content_id

DEFAULT_OUTPUT = Path(OUTPUT_ROOTS["EXP1"])
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
SCENARIO_ROOT = Path("artifacts/experiments/exp1/full_development_scenarios_v1")
MANIFEST = "EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
REQUIRED_OUTPUTS = (
    "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json",
    "EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json",
    "EXP1_FULL_DEVELOPMENT_DECISION_RELEVANCE.json",
    "EXP1_FULL_DEVELOPMENT_ARTIFACT_LINEAGE.json",
)

OFFICIAL_VARIANTS = EXP1_VARIANTS
SENSITIVITY_VARIANTS = EXP1B_SENSITIVITY_VARIANTS
ALLOWED_MANIFEST_VARIANTS = (EXP1_VARIANTS, EXP1_VARIANTS_WITH_SENSITIVITY)

INPUT_FILES = (
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz",
    "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json",
    "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt",
    "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json",
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/M1_V2_TARGET_SUPPORT_MANIFEST.json",
)

SAFETY = {
    "EXP1_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False,
    "PAPER_FULL_RUN": False,
}


def _write_block_record(root: Path, output_root: Path, message: str) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "EXP1_MODEL_CONTRACT_BLOCKED_V1",
        "status": "BLOCKED",
        "message": message,
        "safety": dict(SAFETY),
    }
    payload["artifact_hash"] = content_id(payload)
    path = output_root / "EXP1_MODEL_CONTRACT_BLOCKED.md"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return path


def validate(root: Path, output_root: Path) -> dict:
    frozen = load_official_frozen_binding(root)
    output_root = require_active_path(output_root, root)
    manifest_path = output_root / MANIFEST
    required = tuple(output_root / name for name in REQUIRED_OUTPUTS)
    require_files((manifest_path, *required), code="EXP1_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP1_OFFICIAL")
    if manifest.get("status") != "EXP1_FULL_DEVELOPMENT_COMPLETE":
        raise ContractError("EXP1_OFFICIAL_STATUS_INVALID")
    if manifest.get("execution_scope") != "FULL_DEVELOPMENT_NOT_PAPER_FULL":
        raise ContractError("EXP1_OFFICIAL_SCOPE_INVALID")
    if manifest.get("development_node_count") != 1769:
        raise ContractError("EXP1_OFFICIAL_NODE_COUNT_INVALID")
    if tuple(manifest.get("variants", ())) not in ALLOWED_MANIFEST_VARIANTS:
        raise ContractError("EXP1_OFFICIAL_VARIANTS_INVALID")
    expected = {
        "m1_checkpoint_sha256": frozen.model_hash,
        "feature_schema_hash": frozen.schema_hash,
        "cache_hash": frozen.cache_hash,
        "support_hash": frozen.support_hash,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ContractError(f"EXP1_OFFICIAL_FROZEN_HASH_MISMATCH:{key}")
    result = {
        "status": "EXP1_OFFICIAL_READY",
        "mode": "VALIDATED_EXISTING_FULL_DEVELOPMENT_RESULT",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "node_count": 1769,
        "frozen_hashes": frozen.as_dict(),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    if (output_root / "exp1_summary.json").is_file():
        result["output_contract"] = validate_artifacts("EXP1", output_root)
    else:
        result["output_contract"] = "NOT_RUN"
    return result


def preflight(root: Path, output_root: Path) -> dict:
    frozen = load_official_frozen_binding(root)
    require_active_path(output_root, root)
    require_files(tuple(root / path for path in INPUT_FILES), code="EXP1_OFFICIAL_INPUT_MISSING")
    if tuple(OFFICIAL_VARIANTS) != (
        "EXP1A_NO_DIRECT_REUSE", "EXP1A_FULL", "EXP1B_CURRENT", "EXP1B_ADAPTIVE_HISTORY",
    ):
        raise ContractError("EXP1_OFFICIAL_VARIANTS_INVALID")
    state = {
        "status": "EXP1_OFFICIAL_PREFLIGHT_PASS",
        "mode": "READ_ONLY_PREFLIGHT",
        "official_variants": list(OFFICIAL_VARIANTS),
        "sensitivity_variants": list(SENSITIVITY_VARIANTS),
        "frozen_hashes": frozen.as_dict(),
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    manifest_path = output_root / MANIFEST
    if manifest_path.is_file():
        legacy = load_json(manifest_path)
        variants = tuple(legacy.get("variants", ()))
        state["existing_full_development"] = (
            "ALIGNED" if variants in ALLOWED_MANIFEST_VARIANTS
            else "LEGACY_VARIANT_TUPLE_OFFICIAL_RERUN_PENDING"
        )
    if (output_root / "exp1_summary.json").is_file():
        state["output_contract"] = validate_artifacts("EXP1", output_root)
    else:
        state["output_contract"] = "NOT_RUN"
    return state


def _metric_rows_from_observations(observations, variants):
    rows = []
    for variant in variants:
        for metric_id, observation in observations[variant].items():
            metadata = dict(observation.metadata)
            bootstrap = metadata.pop("bootstrap", None)
            rows.append({
                "experiment": "EXP1",
                "variant": variant,
                "metric_id": metric_id,
                "level": observation.level.value,
                "value": observation.value,
                "unit": observation.unit,
                "support": observation.support_status.value,
                "estimate": bootstrap["estimate"] if bootstrap else observation.value,
                "ci_lower": bootstrap["ci_lower"] if bootstrap else None,
                "ci_upper": bootstrap["ci_upper"] if bootstrap else None,
                "n_episodes": metadata.get("n_episodes"),
                "reason": metadata.get("reason"),
            })
    return rows


def _metric_rows_from_state_metrics(state_metrics, variants):
    rows = []
    for variant in variants:
        for metric_id, observation in (state_metrics.get("variants", {}).get(variant) or {}).items():
            metadata = dict(observation.get("metadata") or {})
            bootstrap = metadata.pop("bootstrap", None)
            rows.append({
                "experiment": "EXP1",
                "variant": variant,
                "metric_id": metric_id,
                "level": observation.get("level", "STATE"),
                "value": observation.get("value"),
                "unit": observation.get("unit", ""),
                "support": observation.get("support_status", "NOT_RUN"),
                "estimate": bootstrap["estimate"] if bootstrap else observation.get("value"),
                "ci_lower": bootstrap["ci_lower"] if bootstrap else None,
                "ci_upper": bootstrap["ci_upper"] if bootstrap else None,
                "n_episodes": metadata.get("n_episodes"),
                "reason": metadata.get("reason"),
            })
    return rows


def _cohort_metric_rows(input_manifest, scenario_manifest):
    """Main-chain displayable cohort/stage summary (engineering facts)."""
    episode_count = int(input_manifest.get("episode_count", 0))
    node_count = int(input_manifest.get("node_count", 0))
    scenarios_per_node = int(scenario_manifest.get("scenario_count_per_node", 0))
    row_count = int(scenario_manifest.get("row_count", 0))
    coverage = (
        row_count / (node_count * scenarios_per_node)
        if node_count and scenarios_per_node else None
    )
    rows = []
    for metric_id, value, unit, episodes in (
        ("COHORT_EPISODES", episode_count, "episodes", episode_count),
        ("COHORT_NODES", node_count, "nodes", episode_count),
        ("SCENARIOS_PER_NODE", scenarios_per_node, "scenarios/node", episode_count),
        ("SCENARIO_COVERAGE_RATE", coverage, "rate", episode_count),
    ):
        if value is None:
            continue
        rows.append({
            "experiment": "EXP1",
            "variant": "EXP1_COHORT",
            "metric_id": metric_id,
            "value": value,
            "support": "SUPPORTED",
            "estimate": value,
            "ci_lower": None,
            "ci_upper": None,
            "n_episodes": episodes,
            "reason": None,
            "unit": unit,
        })
    return rows


def run_full_development(
    *,
    root: Path,
    input_root: Path,
    scenario_root: Path,
    output_root: Path,
    scenario_count: int,
    include_sensitivity: bool,
) -> dict:
    require_active_path(input_root, root)
    require_active_path(scenario_root, root)
    require_active_path(output_root, root)
    require_files(tuple(root / path for path in INPUT_FILES), code="EXP1_FULL_DEVELOPMENT_INPUT_MISSING")
    try:
        materialize_inputs(root=root, output_root=input_root)
        scenario_output = materialize_scenarios(
            root=root, input_root=input_root, output_root=scenario_root,
            scenario_count=scenario_count,
        )
    except Exception as exc:
        block_path = _write_block_record(root, output_root, f"{type(exc).__name__}: {exc}")
        raise ContractError(f"EXP1_FULL_DEVELOPMENT_BLOCKED_RECORD:{block_path}") from exc

    scenario_manifest = load_json(scenario_output["manifest"])
    scenario_path = root / Path(scenario_manifest["artifact"])
    input_manifest = load_json(input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json")
    labels_payload = load_json(input_root / "M1_V2_FULL_DEVELOPMENT_LABELS.json")
    label_rows = labels_payload.get("labels", ())
    variants = (
        EXP1_VARIANTS_WITH_SENSITIVITY if include_sensitivity else EXP1_VARIANTS
    )
    rows: list[dict] = []
    with pq.ParquetFile(scenario_path) as parquet:
        for batch in parquet.iter_batches(batch_size=20000):
            rows.extend(batch.to_pylist())
    observations = compute_full_state_metrics(
        scenario_rows=rows, label_rows=label_rows, variants=variants, seed=0,
    )
    frozen = load_official_frozen_binding(root)
    metric_rows = _metric_rows_from_observations(observations, variants)
    metric_rows += _cohort_metric_rows(input_manifest, scenario_manifest)

    variants_manifest = {}
    for variant in variants:
        definition = variant_definition(variant)
        variants_manifest[variant] = definition
    variants_manifest["EXP1_COHORT"] = {
        "variant_id": "EXP1_COHORT",
        "subexperiment": "EXP1_COHORT",
        "changed_factor": "frozen cohort materialization",
        "fixed_factor": ("data2_development", "scenario_seed"),
        "claim_scope": "COHORT_STAGE_SUMMARY_ENGINEERING_FACT_NOT_SCIENTIFIC_METRIC",
    }
    cohort = {
        "dataset_id": "DATA2",
        "split": "DEVELOPMENT",
        "episode_count": input_manifest.get("episode_count", 0),
        "node_count": input_manifest.get("node_count", 0),
        "scenario_count_per_node": scenario_count,
        "seed": 0,
    }
    output_contract_paths = write_experiment_artifacts(
        experiment_id="EXP1",
        output_root=output_root,
        metric_rows=metric_rows,
        cohort=cohort,
        variants=variants,
        variant_definitions=variants_manifest,
        frozen_hashes=frozen.as_dict(),
        config_hash=scenario_manifest.get("artifact_hash", ""),
        interpretation=(
            "Exp1 compares direct information reuse (Exp1A) and history "
            "representation (Exp1B) on the frozen Data2 Development cohort. "
            "STATE metrics land first; decision-level metrics remain NOT_RUN "
            "until the shared M4 mapping/replay gate is frozen and therefore "
            "occupy no main-table row. The main table shows the materialized "
            "cohort/stage summary and typed-scenario coverage, which are "
            "engineering facts, not scientific evidence."
        ),
        claim_scope="INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        limitations=(
            "CRPS_PRIMITIVE_TARGET covers R_IB, DeltaOB, T_TX and derived D_TO.",
            "STATE_REPRESENTATION_DIFFERENCE requires masked M1 predictive outputs.",
            "BRIER/CALIBRATION/COVERAGE require a frozen delay-event definition.",
            "TOP1_ACTION_DISAGREEMENT and EXPOST_MODEL_IMPLIED_RESIDUAL_RISK stay NOT_RUN at the M4 gate.",
            "Cohort/stage rows are materialization coverage facts, not model metrics.",
        ),
        omega_insight=(
            "Information reuse and history representation change state quality "
            "measurably, but operational action value cannot be ranked until "
            "the consequence-to-monetary mapping is scientifically frozen."
        ),
        condition_of={
            "EXP1A_NO_DIRECT_REUSE": "No direct reuse",
            "EXP1A_FULL": "Full reuse",
            "EXP1B_CURRENT": "Current state",
            "EXP1B_ADAPTIVE_HISTORY": "Adaptive history",
            "EXP1B_FIXED_HISTORY_30": "Fixed 30-minute history (sensitivity)",
            "EXP1_COHORT": "Frozen Data2 Development cohort",
        },
        split_rows=(),
        leakage_rows=(),
        root=root,
    )

    manifest_payload = {
        "schema_version": "EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST_V1",
        "status": "EXP1_FULL_DEVELOPMENT_COMPLETE",
        "execution_scope": "FULL_DEVELOPMENT_NOT_PAPER_FULL",
        "dataset": "DATA2_2019",
        "split": "DEVELOPMENT",
        "episode_count": input_manifest.get("episode_count", 0),
        "development_node_count": input_manifest.get("node_count", 0),
        "variants": list(variants),
        "m1_model_id": "M1_V2_GRU_H32",
        "m1_checkpoint_sha256": frozen.model_hash,
        "feature_schema_hash": frozen.schema_hash,
        "cache_hash": frozen.cache_hash,
        "support_hash": frozen.support_hash,
        "decision_relevance_status": "BLOCKED_M2_M3_M4_ARTIFACTS_UNAVAILABLE",
        "automatic_selection": False,
        "loss_version": "TARGET_SPECIFIC_EPISODE_BALANCED",
        "outputs": {
            "state_metrics": str((output_root / "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json").relative_to(root)).replace("\\", "/"),
            "variant_comparison": str((output_root / "EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json").relative_to(root)).replace("\\", "/"),
            "decision_relevance": str((output_root / "EXP1_FULL_DEVELOPMENT_DECISION_RELEVANCE.json").relative_to(root)).replace("\\", "/"),
            "lineage": str((output_root / "EXP1_FULL_DEVELOPMENT_ARTIFACT_LINEAGE.json").relative_to(root)).replace("\\", "/"),
        },
        "safety": dict(SAFETY),
    }
    manifest_payload["artifact_hash"] = content_id(manifest_payload)
    (output_root / MANIFEST).write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (output_root / "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json").write_text(
        json.dumps(
            {
                "schema_version": "EXP1_FULL_DEVELOPMENT_STATE_METRICS_V1",
                "status": "STATE_METRICS_MATERIALIZED",
                "variants": {
                    variant: {
                        metric_id: observation.model_dump(mode="json")
                        for metric_id, observation in observations[variant].items()
                    }
                    for variant in variants
                },
                "safety": dict(SAFETY),
            },
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )
    (output_root / "EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json").write_text(
        json.dumps(
            {
                "schema_version": "EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON_V1",
                "status": "EXECUTED_FULL_DEVELOPMENT_ONLY",
                "principal_state_metric": "CRPS_PRIMITIVE_TARGET",
                "variants": {
                    variant: {
                        "crps_minutes": observations[variant]["CRPS_PRIMITIVE_TARGET"].value,
                        "support_status": observations[variant]["CRPS_PRIMITIVE_TARGET"].support_status.value,
                    }
                    for variant in variants
                },
                "automatic_selection": False,
                "paper_result": False,
                "safety": dict(SAFETY),
            },
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )
    (output_root / "EXP1_FULL_DEVELOPMENT_DECISION_RELEVANCE.json").write_text(
        json.dumps(
            {
                "schema_version": "EXP1_FULL_DEVELOPMENT_DECISION_RELEVANCE_V1",
                "status": "DECISION_RELEVANCE_NOT_RUN",
                "decision_metrics_status": "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE",
                "safety": dict(SAFETY),
            },
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )
    (output_root / "EXP1_FULL_DEVELOPMENT_ARTIFACT_LINEAGE.json").write_text(
        json.dumps(
            {
                "schema_version": "EXP1_FULL_DEVELOPMENT_ARTIFACT_LINEAGE_V1",
                "status": "BOUND_WITH_UNRESOLVED_UPSTREAM_GATES",
                "frozen_hashes": frozen.as_dict(),
                "scenario_manifest": str(scenario_manifest["artifact"]),
                "scenario_artifact_hash": scenario_manifest.get("artifact_hash"),
                "safety": dict(SAFETY),
            },
            indent=2, sort_keys=True,
        ) + "\n", encoding="utf-8",
    )
    return validate(root, output_root)


def finalize_output_contract(
    *,
    root: Path,
    input_root: Path,
    scenario_root: Path,
    output_root: Path,
) -> dict:
    """Rebuild the output-contract artifact set from materialized outputs.

    Read-only with respect to experiments: reuses the existing state-metrics
    payload, the input manifest, and the typed-scenario manifest; never
    re-executes M1 inference or scenario materialization.
    """
    require_active_path(input_root, root)
    require_active_path(scenario_root, root)
    require_active_path(output_root, root)
    manifest_path = output_root / MANIFEST
    require_files(
        (
            manifest_path,
            output_root / "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json",
            input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json",
            scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json",
        ),
        code="EXP1_FINALIZE_OUTPUT_MISSING",
    )
    frozen = load_official_frozen_binding(root)
    state_metrics = load_json(output_root / "EXP1_FULL_DEVELOPMENT_STATE_METRICS.json")
    input_manifest = load_json(input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json")
    scenario_manifest = load_json(
        scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
    )
    execution_manifest = load_json(manifest_path)
    variants = tuple(execution_manifest.get("variants", ()))
    metric_rows = _metric_rows_from_state_metrics(state_metrics, variants)
    metric_rows += _cohort_metric_rows(input_manifest, scenario_manifest)
    variants_manifest = {
        variant: variant_definition(variant) for variant in variants
    }
    variants_manifest["EXP1_COHORT"] = {
        "variant_id": "EXP1_COHORT",
        "subexperiment": "EXP1_COHORT",
        "changed_factor": "frozen cohort materialization",
        "fixed_factor": ("data2_development", "scenario_seed"),
        "claim_scope": "COHORT_STAGE_SUMMARY_ENGINEERING_FACT_NOT_SCIENTIFIC_METRIC",
    }
    cohort = {
        "dataset_id": "DATA2",
        "split": "DEVELOPMENT",
        "episode_count": input_manifest.get("episode_count", 0),
        "node_count": input_manifest.get("node_count", 0),
        "scenario_count_per_node": scenario_manifest.get("scenario_count_per_node", 0),
        "seed": 0,
    }
    write_experiment_artifacts(
        experiment_id="EXP1",
        output_root=output_root,
        metric_rows=metric_rows,
        cohort=cohort,
        variants=variants,
        variant_definitions=variants_manifest,
        frozen_hashes=frozen.as_dict(),
        config_hash=scenario_manifest.get("artifact_hash", ""),
        interpretation=(
            "Exp1 compares direct information reuse (Exp1A) and history "
            "representation (Exp1B) on the frozen Data2 Development cohort. "
            "STATE metrics land first; decision-level metrics remain NOT_RUN "
            "until the shared M4 mapping/replay gate is frozen and therefore "
            "occupy no main-table row. The main table shows the materialized "
            "cohort/stage summary and typed-scenario coverage, which are "
            "engineering facts, not scientific evidence."
        ),
        claim_scope="INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        limitations=(
            "CRPS_PRIMITIVE_TARGET covers R_IB, DeltaOB, T_TX and derived D_TO.",
            "STATE_REPRESENTATION_DIFFERENCE requires masked M1 predictive outputs.",
            "BRIER/CALIBRATION/COVERAGE require a frozen delay-event definition.",
            "TOP1_ACTION_DISAGREEMENT and EXPOST_MODEL_IMPLIED_RESIDUAL_RISK stay NOT_RUN at the M4 gate.",
            "Cohort/stage rows are materialization coverage facts, not model metrics.",
        ),
        omega_insight=(
            "Information reuse and history representation change state quality "
            "measurably, but operational action value cannot be ranked until "
            "the consequence-to-monetary mapping is scientifically frozen."
        ),
        condition_of={
            "EXP1A_NO_DIRECT_REUSE": "No direct reuse",
            "EXP1A_FULL": "Full reuse",
            "EXP1B_CURRENT": "Current state",
            "EXP1B_ADAPTIVE_HISTORY": "Adaptive history",
            "EXP1B_FIXED_HISTORY_30": "Fixed 30-minute history (sensitivity)",
            "EXP1_COHORT": "Frozen Data2 Development cohort",
        },
        split_rows=(),
        leakage_rows=(),
        root=root,
    )
    return validate(root, output_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exp1 full-Development entry point.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--finalize-output", action="store_true")
    parser.add_argument("--include-sensitivity", action="store_true")
    parser.add_argument("--scenario-count", type=int, default=250)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--scenario-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    input_root = require_active_path((args.input_root or root / INPUT_ROOT), root)
    scenario_root = require_active_path((args.scenario_root or root / SCENARIO_ROOT), root)
    output_root = require_active_path((args.output_root or root / DEFAULT_OUTPUT), root)
    if args.scenario_count <= 0:
        raise ContractError("EXP1_OFFICIAL_SCENARIO_COUNT_INVALID")
    if args.check:
        print(json.dumps(preflight(root, output_root), sort_keys=True))
        return 0
    if args.resume and (output_root / MANIFEST).is_file():
        print(json.dumps(validate(root, output_root), sort_keys=True))
        return 0
    if args.finalize_output:
        print(json.dumps(
            finalize_output_contract(
                root=root, input_root=input_root, scenario_root=scenario_root,
                output_root=output_root,
            ),
            sort_keys=True,
        ))
        return 0
    result = run_full_development(
        root=root, input_root=input_root, scenario_root=scenario_root,
        output_root=output_root, scenario_count=args.scenario_count,
        include_sensitivity=args.include_sensitivity,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
