"""Final Test calibrated scenario materialization (D6 + T-cal, 2026-08-26).

Re-runs the frozen scenario envelope over the same Development cohort
(1,769 nodes x 250 draws, seed 20260813) with the shared T-cal calibration
artifact applied IN MEMORY to the frozen checkpoints (D7c/D7d):
- STATE_AWARE H32 (M1_V2_GRU_H32): full adaptive prefix, calibrated
  temperatures; the hazard pmf is temperature-scaled inside _draw_target.
- CURRENT-only comparator (M1_V2_GRU_H32_CURRENT_ONLY): single current
  legal node (prefix[-1]), same calibrated procedure.

No retraining, no checkpoint writes, no Final Test split access
(FINAL_TEST_ACCESS_COUNT = 0), no paper_full run.  Outputs are
paper_result=true and live only in the new paper-result root.

The draw procedure is byte-identical to the frozen dev materialization
(exp.common.full_development_scenarios / exp.exp1.current_only_scenarios);
the only changed input is pipeline.temperatures set from the shared artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import torch

from exp.common.official_execution import write_json
from exp.reporting.calibration_artifact import apply_calibration_artifact
from exp.workflows.m1_v2_current_stage_scenario_envelope import (
    SCENARIO_COUNT,
    SCENARIO_SEED,
    TARGETS,
    _draw_target,
    _factual_observed,
    _rng_target,
    _uniform,
)
from model.M1.pipeline import M1Pipeline
from model.PRE.contracts.pre_state import PREState

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("artifacts/paper_results_v1/scenarios")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
COHORT = INPUT_ROOT / "DATA2_FULL_DEVELOPMENT_COHORT.json"
INPUTS = INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
INPUT_MANIFEST = INPUT_ROOT / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
SUPPORT = Path(
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/"
    "M1_V2_TARGET_SUPPORT_MANIFEST.json"
)
STATE_AWARE_CHECKPOINT = Path(
    "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
CURRENT_ONLY_CHECKPOINT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
CALIBRATION_ARTIFACT = Path(
    "artifacts/calibration/m1_v2_calibration_20260826/M1_V2_CALIBRATION_ARTIFACT.json"
)
CURRENT_TRAINING_METRICS = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_CURRENT_ONLY_FAST_TRAIN_METRICS.json"
)
STATE_AWARE_MODEL_ID = "M1_V2_GRU_H32"
CURRENT_ONLY_MODEL_ID = "M1_V2_GRU_H32_CURRENT_ONLY"
SCHEMA_VERSION = "AIR_SLOT_FINAL_TEST_CALIBRATED_SCENARIO_MANIFEST_V1"
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "MODEL_RETRAINED": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _stream_model(
    *,
    pipeline: M1Pipeline,
    inputs_payload: dict[str, Any],
    cohort: dict[str, Any],
    support_hash: str,
    checkpoint_hash: str,
    current_only: bool,
    output_path: Path,
    scenario_count: int = SCENARIO_COUNT,
    scenario_seed: int = SCENARIO_SEED,
) -> dict[str, Any]:
    """Stream the calibrated scenario envelope for one model (dev-identical loop)."""
    pipeline.model.eval()
    encoded_by_node = {
        row["decision_node_id"]: row for row in inputs_payload["inference_inputs"]
    }
    temporary = output_path.with_suffix(".parquet.tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    class_counts = {target: Counter() for target in TARGETS}
    row_count = 0
    try:
        for episode_id, serialized_states in sorted(
            inputs_payload["pre_states_by_episode"].items()
        ):
            for serialized in serialized_states:
                pre = PREState.model_validate(serialized)
                node = pre.decision_node
                encoded = encoded_by_node[node.decision_node_id]
                prefix = encoded["encoded_adaptive_prefix"]
                _require(len(prefix) >= 1, "FINAL_TEST_SCENARIO_EMPTY_PREFIX")
                values = (
                    torch.tensor([prefix[-1]], dtype=torch.float32).unsqueeze(0)
                    if current_only
                    else torch.tensor(prefix, dtype=torch.float32).unsqueeze(0)
                )
                lengths = (
                    torch.tensor([1], dtype=torch.long)
                    if current_only
                    else torch.tensor([len(prefix)], dtype=torch.long)
                )
                static = torch.tensor(
                    encoded["encoded_static_context"], dtype=torch.float32,
                ).unsqueeze(0)
                with torch.no_grad():
                    _, _, _, state = pipeline._information_state(
                        values, lengths, static_features=static,
                    )
                observed = _factual_observed(pre)
                base_lineage = (
                    f"pre:cohort={cohort['cohort_hash']}",
                    f"pre:node={node.decision_node_id}",
                    f"m1:checkpoint={checkpoint_hash}",
                    f"m1:support={support_hash}",
                    "m1:calibration=SHARED_T_CAL_ARTIFACT_20260826",
                )
                node_rows: list[dict[str, Any]] = []
                decision_time = node.decision_time.isoformat()
                for scenario_id in range(scenario_count):
                    ib, ib_index = _draw_target(
                        pipeline, state, "T_IB_A00",
                        _uniform(
                            scenario_seed, episode_id, scenario_id,
                            _rng_target("T_IB_A00"),
                        )[0],
                        ib_index=None, d_ob_index=None, decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("T_IB_A00"),
                    )
                    d_ob, d_ob_index = _draw_target(
                        pipeline, state, "D_OB",
                        _uniform(scenario_seed, episode_id, scenario_id, "D_OB")[0],
                        ib_index=ib_index, d_ob_index=None, decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("D_OB"),
                    )
                    d_tx, _ = _draw_target(
                        pipeline, state, "D_TX",
                        _uniform(scenario_seed, episode_id, scenario_id, "D_TX")[0],
                        ib_index=ib_index, d_ob_index=d_ob_index,
                        decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("D_TX"),
                    )
                    envelopes = (ib, d_ob, d_tx)
                    for envelope in envelopes:
                        key = (
                            envelope.class_id
                            if envelope.class_id in {"ZERO", "OVERFLOW_TAIL", "ABSTAIN"}
                            else "FINITE"
                        )
                        class_counts[envelope.target_name][key] += 1
                    d_to = (
                        None
                        if any(
                            item.scalar_support_state != "SUPPORTED"
                            for item in (d_ob, d_tx)
                        )
                        else float(d_ob.scalar_minutes + d_tx.scalar_minutes)
                    )
                    node_rows.append({
                        "episode_id": episode_id,
                        "decision_node_id": node.decision_node_id,
                        "scenario_id": scenario_id,
                        "scenario_weight": 1.0 / scenario_count,
                        "operational_stage": node.operational_stage.value,
                        "decision_time_utc": decision_time,
                        "information_cutoff_utc": node.information_cutoff.isoformat(),
                        "T_IB_A00": ib.scalar_minutes,
                        "D_OB": d_ob.scalar_minutes,
                        "D_TX": d_tx.scalar_minutes,
                        "D_TO": d_to,
                        "target_envelopes_json": json.dumps(
                            [item.model_dump(mode="json") for item in envelopes],
                            sort_keys=True,
                        ),
                        "scenario_seed_key": "|".join(
                            _uniform(
                                scenario_seed, episode_id, scenario_id,
                                _rng_target(target),
                            )[1]
                            for target in TARGETS
                        ),
                        "lineage_json": json.dumps(base_lineage),
                    })
                table = pa.Table.from_pylist(node_rows)
                if writer is None:
                    writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
                writer.write_table(table)
                row_count += len(node_rows)
    finally:
        if writer is not None:
            writer.close()
    _require(
        row_count == int(cohort["node_count"]) * scenario_count,
        "FINAL_TEST_SCENARIO_CARDINALITY_INVALID",
    )
    temporary.replace(output_path)
    return {
        "row_count": row_count,
        "node_count": int(cohort["node_count"]),
        "class_counts": {target: dict(counts) for target, counts in class_counts.items()},
    }


def run(*, root: Path | None = None, output_root: Path | None = None) -> dict[str, Path]:
    root = (root or ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_root.parents, "FINAL_TEST_SCENARIO_OUTPUT_OUTSIDE_PROJECT")

    for relative in (
        INPUTS, COHORT, INPUT_MANIFEST, SUPPORT,
        STATE_AWARE_CHECKPOINT, CURRENT_ONLY_CHECKPOINT,
        CALIBRATION_ARTIFACT, CURRENT_TRAINING_METRICS,
    ):
        _require((root / relative).is_file(), f"FINAL_TEST_SCENARIO_INPUT_MISSING:{relative}")

    binding = json.loads((root / INPUT_MANIFEST).read_text(encoding="utf-8"))
    cohort = json.loads((root / COHORT).read_text(encoding="utf-8"))
    inputs_payload = json.loads((root / INPUTS).read_text(encoding="utf-8"))
    support = json.loads((root / SUPPORT).read_text(encoding="utf-8"))
    training_metrics = json.loads((root / CURRENT_TRAINING_METRICS).read_text(encoding="utf-8"))
    artifact = json.loads((root / CALIBRATION_ARTIFACT).read_text(encoding="utf-8"))

    _require(binding["status"] == "FULL_DEVELOPMENT_INPUTS_READY", "FINAL_TEST_SCENARIO_BINDING_INVALID")
    _require(
        cohort["cohort_hash"] == inputs_payload["cohort_hash"] == binding["cohort_hash"],
        "FINAL_TEST_SCENARIO_COHORT_HASH_MISMATCH",
    )
    _require(
        binding["frozen_hashes"]["model_hash"] == _sha256(root / STATE_AWARE_CHECKPOINT),
        "FINAL_TEST_SCENARIO_MODEL_HASH_MISMATCH",
    )
    _require(
        training_metrics.get("checkpoint_sha256") == _sha256(root / CURRENT_ONLY_CHECKPOINT),
        "FINAL_TEST_SCENARIO_CURRENT_CHECKPOINT_HASH_MISMATCH",
    )
    _require(artifact.get("artifact_hash") is not None, "FINAL_TEST_SCENARIO_ARTIFACT_UNHASHED")
    support_hash = support.get("artifact_hash") or support.get("support_hash")

    history_path = output_root / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_HISTORY.parquet"
    current_path = output_root / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_CURRENT.parquet"

    history: dict[str, Any] = {}
    current: dict[str, Any] = {}
    if not history_path.is_file():
        pipeline = M1Pipeline.load(root / STATE_AWARE_CHECKPOINT)
        applied = apply_calibration_artifact(pipeline, artifact, STATE_AWARE_MODEL_ID)
        print("STATE_AWARE calibrated temperatures:", applied)
        history = _stream_model(
            pipeline=pipeline,
            inputs_payload=inputs_payload,
            cohort=cohort,
            support_hash=support_hash,
            checkpoint_hash=binding["frozen_hashes"]["model_hash"],
            current_only=False,
            output_path=history_path,
        )
    else:
        print("history scenarios already materialized; skipping")
    if not current_path.is_file():
        pipeline = M1Pipeline.load(root / CURRENT_ONLY_CHECKPOINT)
        applied = apply_calibration_artifact(pipeline, artifact, CURRENT_ONLY_MODEL_ID)
        print("CURRENT_ONLY calibrated temperatures:", applied)
        current = _stream_model(
            pipeline=pipeline,
            inputs_payload=inputs_payload,
            cohort=cohort,
            support_hash=support_hash,
            checkpoint_hash=training_metrics["checkpoint_sha256"],
            current_only=True,
            output_path=current_path,
        )
    else:
        print("current scenarios already materialized; skipping")

    _require(history_path.is_file() and current_path.is_file(), "FINAL_TEST_SCENARIO_OUTPUT_MISSING")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "FINAL_TEST_CALIBRATED_SCENARIOS_MATERIALIZED",
        "scope": "FINAL_TEST_CALIBRATED_REMATERIALIZATION_DEVELOPMENT_COHORT",
        "paper_result": True,
        "dataset": "DATA2",
        "split": "DEVELOPMENT",
        "cohort_hash": cohort["cohort_hash"],
        "node_count": int(cohort["node_count"]),
        "episode_count": int(cohort["episode_count"]),
        "scenario_count_per_node": SCENARIO_COUNT,
        "scenario_seed": SCENARIO_SEED,
        "bootstrap_seed": 20260825,
        "row_count": int(cohort["node_count"]) * SCENARIO_COUNT,
        "tail_scalar_extrapolation": False,
        "frozen_hashes": dict(binding["frozen_hashes"]),
        "calibration": {
            "artifact": str((root / CALIBRATION_ARTIFACT).relative_to(root)).replace("\\", "/"),
            "artifact_hash": artifact["artifact_hash"],
            "decision_id": artifact.get("decision_id"),
            "application": "IN_MEMORY_PIPELINE_TEMPERATURES_CHECKPOINTS_UNTOUCHED",
        },
        "models": {
            STATE_AWARE_MODEL_ID: {
                "checkpoint_sha256": binding["frozen_hashes"]["model_hash"],
                "artifact": str(history_path.relative_to(root)).replace("\\", "/"),
                "artifact_hash": _sha256(history_path),
                "class_counts": history.get("class_counts"),
                "row_count": history.get("row_count"),
            },
            CURRENT_ONLY_MODEL_ID: {
                "checkpoint_sha256": training_metrics["checkpoint_sha256"],
                "artifact": str(current_path.relative_to(root)).replace("\\", "/"),
                "artifact_hash": _sha256(current_path),
                "class_counts": current.get("class_counts"),
                "row_count": current.get("row_count"),
            },
        },
        "input_hashes": {
            "inference_inputs": _sha256(root / INPUTS),
            "cohort": _sha256(root / COHORT),
            "support": support_hash,
            "state_aware_checkpoint": _sha256(root / STATE_AWARE_CHECKPOINT),
            "current_only_checkpoint": _sha256(root / CURRENT_ONLY_CHECKPOINT),
            "calibration_artifact": artifact["artifact_hash"],
        },
        "safety": dict(SAFETY),
        "outputs": {
            "history": str(history_path.relative_to(root)).replace("\\", "/"),
            "current": str(current_path.relative_to(root)).replace("\\", "/"),
            "manifest": str((output_root / "FINAL_TEST_SCENARIO_MANIFEST.json").relative_to(root)).replace("\\", "/"),
        },
    }
    manifest["manifest_hash"] = _content_hash(manifest)
    write_json(output_root / "FINAL_TEST_SCENARIO_MANIFEST.json", manifest)
    print("manifest written:", output_root / "FINAL_TEST_SCENARIO_MANIFEST.json")
    return {
        "history": history_path,
        "current": current_path,
        "manifest": output_root / "FINAL_TEST_SCENARIO_MANIFEST.json",
    }


def _content_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    paths = run(output_root=args.output_root)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
