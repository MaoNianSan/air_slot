"""Stream the frozen H32 scenario envelope over all Development nodes."""

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
from model.common.identity import content_id


INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp2/full_development_scenarios_v1")
CHECKPOINT = Path("artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt")
SUPPORT = Path("artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/M1_V2_TARGET_SUPPORT_MANIFEST.json")

SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
}


def _load(path: Path) -> dict[str, Any]:
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
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def materialize(
    *,
    root: Path,
    input_root: Path | None = None,
    output_root: Path | None = None,
    scenario_count: int = SCENARIO_COUNT,
    scenario_seed: int = SCENARIO_SEED,
) -> dict[str, Path]:
    root = root.resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    manifest_path = input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
    cohort_path = input_root / "DATA2_FULL_DEVELOPMENT_COHORT.json"
    inputs_path = input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
    support_path = root / SUPPORT
    checkpoint_path = root / CHECKPOINT
    _require(all(path.is_file() for path in (manifest_path, cohort_path, inputs_path, support_path, checkpoint_path)), "FULL_DEVELOPMENT_SCENARIO_INPUT_MISSING")
    binding, cohort, inputs, support = map(_load, (manifest_path, cohort_path, inputs_path, support_path))
    _require(binding["status"] == "FULL_DEVELOPMENT_INPUTS_READY", "FULL_DEVELOPMENT_INPUT_BINDING_INVALID")
    _require(cohort["cohort_hash"] == inputs["cohort_hash"] == binding["cohort_hash"], "FULL_DEVELOPMENT_SCENARIO_COHORT_HASH_MISMATCH")
    _require(binding["frozen_hashes"]["model_hash"] == _sha(checkpoint_path), "FULL_DEVELOPMENT_SCENARIO_MODEL_HASH_MISMATCH")
    _require(binding["frozen_hashes"]["support_hash"] in {support.get("artifact_hash"), support.get("support_hash")}, "FULL_DEVELOPMENT_SCENARIO_SUPPORT_HASH_MISMATCH")
    _require(scenario_count > 0, "FULL_DEVELOPMENT_SCENARIO_COUNT_INVALID")

    pipeline = M1Pipeline.load(checkpoint_path)
    pipeline.model.eval()
    encoded_by_node = {row["decision_node_id"]: row for row in inputs["inference_inputs"]}
    parquet_path = output_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
    temporary = parquet_path.with_suffix(".parquet.tmp")
    output_root.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    class_counts = {target: Counter() for target in TARGETS}
    row_count = 0
    try:
        for episode_id, serialized_states in sorted(inputs["pre_states_by_episode"].items()):
            for serialized in serialized_states:
                pre = PREState.model_validate(serialized)
                node = pre.decision_node
                encoded = encoded_by_node[node.decision_node_id]
                values = torch.tensor(encoded["encoded_adaptive_prefix"], dtype=torch.float32)
                lengths = torch.tensor([len(values)], dtype=torch.long)
                static = torch.tensor(encoded["encoded_static_context"], dtype=torch.float32).unsqueeze(0)
                with torch.no_grad():
                    _, _, _, state = pipeline._information_state(
                        values.unsqueeze(0), lengths, static_features=static,
                    )
                observed = _factual_observed(pre)
                base_lineage = (
                    f"pre:cohort={cohort['cohort_hash']}",
                    f"pre:node={node.decision_node_id}",
                    f"m1:checkpoint={binding['frozen_hashes']['model_hash']}",
                    f"m1:support={binding['frozen_hashes']['support_hash']}",
                )
                node_rows: list[dict[str, Any]] = []
                decision_time = node.decision_time.isoformat()
                for scenario_id in range(scenario_count):
                    ib, ib_index = _draw_target(
                        pipeline, state, "T_IB_A00",
                        _uniform(scenario_seed, episode_id, scenario_id, _rng_target("T_IB_A00"))[0],
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
                        ib_index=ib_index, d_ob_index=d_ob_index, decision_time=decision_time,
                        lineage=base_lineage, observed=observed.get("D_TX"),
                    )
                    envelopes = (ib, d_ob, d_tx)
                    for envelope in envelopes:
                        key = envelope.class_id if envelope.class_id in {"ZERO", "OVERFLOW_TAIL", "ABSTAIN"} else "FINITE"
                        class_counts[envelope.target_name][key] += 1
                    d_to = None if any(item.scalar_support_state != "SUPPORTED" for item in (d_ob, d_tx)) else float(d_ob.scalar_minutes + d_tx.scalar_minutes)
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
                        "target_envelopes_json": json.dumps([item.model_dump(mode="json") for item in envelopes], sort_keys=True),
                        "scenario_seed_key": "|".join(
                            _uniform(scenario_seed, episode_id, scenario_id, _rng_target(target))[1]
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
    _require(row_count == cohort["node_count"] * scenario_count, "FULL_DEVELOPMENT_SCENARIO_CARDINALITY_INVALID")
    temporary.replace(parquet_path)
    parquet_hash = _sha(parquet_path)
    manifest = {
        "schema_version": "M1_V2_FULL_DEVELOPMENT_SCENARIO_MANIFEST_V1",
        "status": "FULL_DEVELOPMENT_TYPED_SCENARIOS_MATERIALIZED",
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "artifact": str(parquet_path.relative_to(root)).replace("\\", "/"),
        "artifact_hash": parquet_hash,
        "cohort_hash": cohort["cohort_hash"],
        "node_count": cohort["node_count"], "row_count": row_count,
        "scenario_count_per_node": scenario_count, "scenario_seed": scenario_seed,
        "class_counts": {target: dict(counts) for target, counts in class_counts.items()},
        "frozen_hashes": dict(binding["frozen_hashes"]),
        "tail_scalar_extrapolation": False,
        "safety": dict(SAFETY),
    }
    manifest["manifest_hash"] = content_id(manifest)
    output_manifest = output_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
    _write(output_manifest, manifest)
    return {"artifact": parquet_path, "manifest": output_manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--scenario-count", type=int, default=SCENARIO_COUNT)
    parser.add_argument("--seed", type=int, default=SCENARIO_SEED)
    args = parser.parse_args(argv)
    materialize(
        root=Path(__file__).resolve().parents[2], input_root=args.input_root,
        output_root=args.output_root, scenario_count=args.scenario_count,
        scenario_seed=args.seed,
    )
    print("FULL_DEVELOPMENT_TYPED_SCENARIOS_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
