"""Exp1B CURRENT-only typed scenario materialization (DEVELOPMENT_COMPARATOR_ONLY).

Replays the frozen H32-CURRENT-only checkpoint over all 1,769 Development
nodes with the same scenario protocol as the HISTORY materialization
(``exp.common.full_development_scenarios``): S=250 draws per node, the same
``SCENARIO_SEED`` and CRN key scheme, and the same class-aware envelope
representation.  The only changed input is the model state: the frozen
inference inputs are sliced read-only to ``encoded_adaptive_prefix[-1]``
(single current legal node) instead of the full adaptive prefix.

No model is trained here; no calibration or Final Test data are read.
``paper_result=false``, ``FINAL_TEST_ACCESS_COUNT=0``.
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
from model.common.errors import ContractError
from model.common.identity import content_id

INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_TYPED_SCENARIOS.parquet"
)
TRAINING_METRICS = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_CURRENT_ONLY_FAST_TRAIN_METRICS.json"
)
CHECKPOINT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_FAST_TRAIN_MODE.pt"
)
SUPPORT = Path(
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/"
    "M1_V2_TARGET_SUPPORT_MANIFEST.json"
)
SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP1_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"CURRENT_ONLY_SCENARIO_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def materialize(
    *, root: Path, output_path: Path | None = None, scenario_count: int = SCENARIO_COUNT,
) -> dict[str, Path]:
    """Stream the CURRENT-only scenario envelope over all Development nodes."""
    root = root.resolve()
    output_path = (output_path or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_path.parents, "CURRENT_ONLY_SCENARIO_OUTPUT_OUTSIDE_PROJECT")
    manifest_path = root / INPUT_ROOT / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
    cohort_path = root / INPUT_ROOT / "DATA2_FULL_DEVELOPMENT_COHORT.json"
    inputs_path = root / INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
    support_path = root / SUPPORT
    training_metrics_path = root / TRAINING_METRICS
    checkpoint_path = root / CHECKPOINT
    _require(
        all(path.is_file() for path in (
            manifest_path, cohort_path, inputs_path, support_path,
            training_metrics_path, checkpoint_path,
        )),
        "CURRENT_ONLY_SCENARIO_INPUT_MISSING",
    )
    binding, cohort, inputs, support = map(_load, (manifest_path, cohort_path, inputs_path, support_path))
    training_metrics = _load(training_metrics_path)
    _require(binding["status"] == "FULL_DEVELOPMENT_INPUTS_READY", "CURRENT_ONLY_SCENARIO_INPUT_BINDING_INVALID")
    _require(
        cohort["cohort_hash"] == inputs["cohort_hash"] == binding["cohort_hash"],
        "CURRENT_ONLY_SCENARIO_COHORT_HASH_MISMATCH",
    )
    _require(
        training_metrics.get("model_id") == "M1_V2_GRU_H32_CURRENT_ONLY",
        "CURRENT_ONLY_SCENARIO_MODEL_ID_INVALID",
    )
    _require(
        training_metrics.get("budget_identical_to_reference") is True,
        "CURRENT_ONLY_SCENARIO_BUDGET_NOT_IDENTICAL",
    )
    _require(
        training_metrics.get("checkpoint_sha256") is not None
        and _sha(checkpoint_path) == training_metrics["checkpoint_sha256"],
        "CURRENT_ONLY_SCENARIO_CHECKPOINT_HASH_MISMATCH",
    )
    _require(scenario_count > 0, "CURRENT_ONLY_SCENARIO_COUNT_INVALID")

    pipeline = M1Pipeline.load(checkpoint_path)
    pipeline.model.eval()
    encoded_by_node = {row["decision_node_id"]: row for row in inputs["inference_inputs"]}
    temporary = output_path.with_suffix(".parquet.tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    class_counts = {target: Counter() for target in TARGETS}
    row_count = 0
    current_node_only = True
    try:
        for episode_id, serialized_states in sorted(inputs["pre_states_by_episode"].items()):
            for serialized in serialized_states:
                pre = PREState.model_validate(serialized)
                node = pre.decision_node
                encoded = encoded_by_node[node.decision_node_id]
                prefix = encoded["encoded_adaptive_prefix"]
                _require(len(prefix) >= 1, "CURRENT_ONLY_SCENARIO_EMPTY_PREFIX")
                values = torch.tensor([prefix[-1]], dtype=torch.float32).unsqueeze(0)
                lengths = torch.tensor([1], dtype=torch.long)
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
                    f"m1:checkpoint={training_metrics['checkpoint_sha256']}",
                    f"m1:support={binding['frozen_hashes']['support_hash']}",
                    "m1:input_representation=CURRENT",
                )
                node_rows: list[dict[str, Any]] = []
                decision_time = node.decision_time.isoformat()
                for scenario_id in range(scenario_count):
                    ib, ib_index = _draw_target(
                        pipeline, state, "T_IB_A00",
                        _uniform(SCENARIO_SEED, episode_id, scenario_id, _rng_target("T_IB_A00"))[0],
                        ib_index=None, d_ob_index=None, decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("T_IB_A00"),
                    )
                    d_ob, d_ob_index = _draw_target(
                        pipeline, state, "D_OB",
                        _uniform(SCENARIO_SEED, episode_id, scenario_id, "D_OB")[0],
                        ib_index=ib_index, d_ob_index=None, decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("D_OB"),
                    )
                    d_tx, _ = _draw_target(
                        pipeline, state, "D_TX",
                        _uniform(SCENARIO_SEED, episode_id, scenario_id, "D_TX")[0],
                        ib_index=ib_index, d_ob_index=d_ob_index, decision_time=decision_time,
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
                        if any(item.scalar_support_state != "SUPPORTED" for item in (d_ob, d_tx))
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
                            [item.model_dump(mode="json") for item in envelopes], sort_keys=True,
                        ),
                        "scenario_seed_key": "|".join(
                            _uniform(SCENARIO_SEED, episode_id, scenario_id, _rng_target(target))[1]
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
        row_count == cohort["node_count"] * scenario_count,
        "CURRENT_ONLY_SCENARIO_CARDINALITY_INVALID",
    )
    temporary.replace(output_path)
    parquet_hash = _sha(output_path)
    manifest_payload = {
        "schema_version": "EXP1B_CURRENT_ONLY_TYPED_SCENARIO_MANIFEST_V1",
        "status": "EXP1B_CURRENT_ONLY_TYPED_SCENARIOS_MATERIALIZED",
        "scope": "DATA2_FULL_DEVELOPMENT_DEVELOPMENT_COMPARATOR_ONLY",
        "paper_result": False,
        "artifact": str(output_path.relative_to(root)).replace("\\", "/"),
        "artifact_hash": parquet_hash,
        "cohort_hash": cohort["cohort_hash"],
        "node_count": cohort["node_count"],
        "row_count": row_count,
        "scenario_count_per_node": scenario_count,
        "scenario_seed": SCENARIO_SEED,
        "crn_paired_with_history_scenarios": True,
        "input_representation": "CURRENT",
        "input_slice": "encoded_adaptive_prefix[-1] (read-only single current legal node)",
        "model_id": training_metrics["model_id"],
        "checkpoint_sha256": training_metrics["checkpoint_sha256"],
        "history_mode": training_metrics["history_mode"],
        "class_counts": {target: dict(counts) for target, counts in class_counts.items()},
        "frozen_hashes": binding["frozen_hashes"],
        "tail_scalar_extrapolation": False,
        "raw_factual_values_preserved_separately": True,
        "safety": dict(SAFETY),
    }
    manifest_payload["manifest_hash"] = content_id(manifest_payload)
    manifest_path = output_path.with_name(
        "EXP1B_CURRENT_ONLY_TYPED_SCENARIO_MANIFEST.json"
    )
    _write(manifest_path, manifest_payload)
    return {"artifact": output_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--scenario-count", type=int, default=SCENARIO_COUNT)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    materialize(
        root=root, output_path=args.output_path, scenario_count=args.scenario_count,
    )
    print("EXP1B_CURRENT_ONLY_TYPED_SCENARIOS_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["DEFAULT_OUTPUT", "materialize"]
