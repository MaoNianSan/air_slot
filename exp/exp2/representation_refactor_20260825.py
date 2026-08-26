"""Exp2A representation re-materialization with the freeze-F1 adapter.

DEVELOPMENT_ONLY materialization (2026-08-25).  Reads the frozen full
Development M1 scenario artifact (``artifacts/experiments/exp2/
full_development_scenarios_v1/``) node by node and re-runs the POINT /
MARGINAL / JOINT transforms with the refactored
:class:`ScenarioRepresentationAdapter` whose medoid coordinates are the
manuscript primitive triple (R_IB, D_OB, D_TX); D_TO participates only as a
derived identity check (freeze F1).  Partial-q series are not implemented
(freeze F2).

Records produced earlier with the previous adapter (D_TO inside the medoid
distance) are retained untouched and marked SUPERSEDED in the manifest and
README.  No model training, no Final Test access, no paper run, no change to
frozen artifacts, registries, configs, or the baseline audit document.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp2.representation import (
    PRIMITIVE_FIELDS,
    ScenarioRepresentationAdapter,
)
from exp.exp2.variants import EXP2A_JOINT, EXP2A_MARGINAL, EXP2A_POINT

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = Path(
    "artifacts/experiments/exp2/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
)
SCENARIO_MANIFEST = Path(
    "artifacts/experiments/exp2/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
)
OUTPUT_ROOT = Path("artifacts/experiment/exp2/exp2_representation_refactor_20260825")
ARTIFACT_VERSION = "M1_V2_FULL_DEVELOPMENT_V1"
SCHEMA_VERSION = "AIR_SLOT_EXP2A_REPRESENTATION_REFACTOR_V1"
SUPERSEDED_RECORDS = (
    "artifacts/real_fast/exp2/exp2_exp2a_joint.json",
    "artifacts/real_fast/exp2/exp2_exp2a_marginal.json",
    "artifacts/real_fast/exp2/exp2_exp2a_point.json",
)
SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
    "paper_result": False,
}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _record(
    *,
    node_index: int,
    sample: Any,
    episode_id: str,
    decision_node_id: str,
    operational_stage: str,
    transform_rule: str,
    source_scenario_hash: str,
    representation_hash: str,
) -> dict[str, Any]:
    return {
        "node_index": node_index,
        "episode_id": episode_id,
        "decision_node_id": decision_node_id,
        "operational_stage": operational_stage,
        "scenario_id": sample.scenario_id,
        "scenario_weight": sample.scenario_weight,
        "R_IB": sample.R_IB,
        "D_OB": sample.D_OB,
        "D_TX": sample.D_TX,
        "D_TO": sample.D_TO,
        "lineage_json": json.dumps(list(sample.lineage), ensure_ascii=False, sort_keys=True),
        "field_source_scenario_ids_json": json.dumps(
            sample.field_source_scenario_ids, ensure_ascii=False, sort_keys=True
        ),
        "transform_rule": transform_rule,
        "source_scenario_hash": source_scenario_hash,
        "representation_hash": representation_hash,
    }


def materialize(*, root: Path, output_root: Path, node_limit: int | None = None) -> dict[str, Any]:
    manifest = load_json(root / SCENARIO_MANIFEST)
    _require(
        file_sha256(root / SCENARIOS) == manifest["artifact_hash"],
        "EXP2A_REFACTOR_SCENARIO_HASH_MISMATCH",
    )
    node_count = int(manifest["node_count"])
    row_count = int(manifest["row_count"])
    scenario_seed = int(manifest["scenario_seed"])
    scenario_hash = manifest["artifact_hash"]
    parquet = pq.ParquetFile(root / SCENARIOS)
    _require(parquet.num_row_groups == node_count, "EXP2A_REFACTOR_ROW_GROUP_CARDINALITY_INVALID")

    point_rows: list[dict[str, Any]] = []
    marginal_rows: list[dict[str, Any]] = []
    joint_rows: list[dict[str, Any]] = []
    marginal_check_nodes = 0
    node_range = range(node_count) if node_limit is None else range(min(int(node_limit), node_count))
    for node_index in node_range:
        source = parquet.read_row_group(node_index).to_pylist()
        _require(len(source) == 250, "EXP2A_REFACTOR_NODE_SCENARIO_CARDINALITY_INVALID")
        rows = []
        for item in source:
            lineage = json.loads(item["lineage_json"]) if item.get("lineage_json") else None
            if not lineage:
                lineage = (f"M1_SCENARIO_SEED:{item['scenario_seed_key']}",)
            rows.append({
                "scenario_id": int(item["scenario_id"]),
                "scenario_weight": float(item["scenario_weight"]),
                "T_IB_A00": item["T_IB_A00"],
                "D_OB": item["D_OB"],
                "D_TX": item["D_TX"],
                "D_TO": item["D_TO"],
                "lineage": tuple(lineage),
            })
        adapter = ScenarioRepresentationAdapter(
            rows, artifact_version=ARTIFACT_VERSION, scenario_hash=scenario_hash
        )
        joint = adapter.transform(EXP2A_JOINT)
        marginal = adapter.transform(EXP2A_MARGINAL)
        point = adapter.transform(EXP2A_POINT)
        _require(len(point.samples) == 1, "EXP2A_REFACTOR_POINT_CARDINALITY_INVALID")
        _require(point.samples[0].scenario_weight == 1.0, "EXP2A_REFACTOR_POINT_UNIT_WEIGHT_INVALID")

        # Cross-check: each primitive marginal is preserved between JOINT and
        # MARGINAL; D_TO is derived samplewise; POINT copies a source row.
        for field in PRIMITIVE_FIELDS:
            def marginal_of(representation, name: str = field):
                return sorted(
                    (
                        (getattr(item, name), item.scenario_weight)
                        for item in representation.samples
                    ),
                    key=lambda pair: (pair[0] is None, pair[0], pair[1]),
                )
            _require(
                marginal_of(joint) == marginal_of(marginal),
                "EXP2A_REFACTOR_PRIMITIVE_MARGINAL_MISMATCH",
            )
        for item in joint.samples:
            if item.D_OB is not None and item.D_TX is not None:
                _require(
                    item.D_TO is not None and abs(item.D_TO - (item.D_OB + item.D_TX)) <= 1e-6,
                    "EXP2A_REFACTOR_D_TO_IDENTITY_MISMATCH",
                )
        point_sample = point.samples[0]
        # representation_hash is an uncached property; compute once per node
        # per variant instead of once per record row.
        joint_hash = joint.representation_hash
        marginal_hash = marginal.representation_hash
        point_hash = point.representation_hash
        source_by_id = {int(item["scenario_id"]): item for item in source}
        selected_source = source_by_id[int(point_sample.scenario_id.split(":")[1])]
        _require(
            point_sample.R_IB == selected_source["T_IB_A00"]
            and point_sample.D_OB == selected_source["D_OB"]
            and point_sample.D_TX == selected_source["D_TX"],
            "EXP2A_REFACTOR_POINT_SOURCE_COPY_MISMATCH",
        )
        marginal_check_nodes += 1

        episode_id = source[0]["episode_id"]
        decision_node_id = source[0]["decision_node_id"]
        operational_stage = source[0]["operational_stage"]
        joint_rows.extend(
            _record(
                node_index=node_index, sample=item, episode_id=episode_id,
                decision_node_id=decision_node_id, operational_stage=operational_stage,
                transform_rule=joint.transform_rule,
                source_scenario_hash=joint.source_scenario_hash,
                representation_hash=joint_hash,
            )
            for item in joint.samples
        )
        marginal_rows.extend(
            _record(
                node_index=node_index, sample=item, episode_id=episode_id,
                decision_node_id=decision_node_id, operational_stage=operational_stage,
                transform_rule=marginal.transform_rule,
                source_scenario_hash=marginal.source_scenario_hash,
                representation_hash=marginal_hash,
            )
            for item in marginal.samples
        )
        point_rows.append(_record(
            node_index=node_index, sample=point_sample, episode_id=episode_id,
            decision_node_id=decision_node_id, operational_stage=operational_stage,
            transform_rule=point.transform_rule,
            source_scenario_hash=point.source_scenario_hash,
            representation_hash=point_hash,
        ))

    _require(len(point_rows) == len(node_range), "EXP2A_REFACTOR_POINT_ROW_COUNT_INVALID")
    materialized_row_count = len(node_range) * 250
    _require(
        len(joint_rows) == materialized_row_count
        and len(marginal_rows) == materialized_row_count,
        "EXP2A_REFACTOR_ROW_COUNT_INVALID",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    for name, frame in (
        ("EXP2A_POINT_RECORDS_DEVELOPMENT_ONLY", pd.DataFrame(point_rows)),
        ("EXP2A_MARGINAL_RECORDS_DEVELOPMENT_ONLY", pd.DataFrame(marginal_rows)),
        ("EXP2A_JOINT_RECORDS_DEVELOPMENT_ONLY", pd.DataFrame(joint_rows)),
    ):
        frame.to_csv(output_root / f"{name}.csv", index=False)
        frame.to_parquet(output_root / f"{name}.parquet", index=False)

    adapter_hash = file_sha256(root / "exp/exp2/representation.py")
    summary = {
        "schema_version": SCHEMA_VERSION,
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "freeze_refs": {
            "F1": "PRIMITIVE_MEDOID_COORDINATES_R_IB_D_OB_D_TX_D_TO_IDENTITY_ONLY",
            "F2": "PARTIAL_Q_SERIES_NOT_IMPLEMENTED",
        },
        "source_artifact": str(SCENARIOS).replace("\\", "/"),
        "source_artifact_hash": scenario_hash,
        "source_manifest_hash": manifest["manifest_hash"],
        "scenario_seed": scenario_seed,
        "node_count": len(node_range),
        "materialized_node_count": len(node_range),
        "row_count_per_variant": materialized_row_count,
        "cohort_hash": manifest["cohort_hash"],
        "frozen_hashes": manifest["frozen_hashes"],
        "adapter_module_hash": adapter_hash,
        "adapter_artifact_version": ARTIFACT_VERSION,
        "transform_rules": {
            "POINT": "WEIGHTED_JOINT_SCENARIO_MEDOID_PRIMITIVES",
            "MARGINAL": "DETERMINISTIC_WITHIN_WEIGHT_STRATUM_INDEPENDENT_FIELD_PERMUTATION",
            "JOINT": "IDENTITY_PRESERVE_FROZEN_JOINT_SAMPLES",
        },
        "validation": {
            "node_count": len(node_range),
            "point_row_count": len(point_rows),
            "marginal_row_count": len(marginal_rows),
            "joint_row_count": len(joint_rows),
            "primitive_marginal_check_nodes": marginal_check_nodes,
            "status": "PASS",
        },
        "superseded": {
            "records": [str(item).replace("\\", "/") for item in SUPERSEDED_RECORDS],
            "reason": "PREVIOUS_ADAPTER_INCLUDED_D_TO_IN_MEDOID_DISTANCE_AND_MISSING_R_IB",
            "policy": "RETAINED_UNMODIFIED",
        },
        "outputs": [
            f"{name}.csv" for name in (
                "EXP2A_POINT_RECORDS_DEVELOPMENT_ONLY",
                "EXP2A_MARGINAL_RECORDS_DEVELOPMENT_ONLY",
                "EXP2A_JOINT_RECORDS_DEVELOPMENT_ONLY",
            )
        ],
        "safety": SAFETY,
    }
    write_json(output_root / "EXP2A_REPRESENTATION_REFACTOR_MANIFEST.json", summary)
    readme = output_root / "README.md"
    readme.write_text(
        "\n".join(
            (
                "# Exp2A Representation Refactor 2026-08-25 (DEVELOPMENT_ONLY)",
                "",
                "Re-materialized POINT / MARGINAL / JOINT scenario representations from the",
                "frozen full-Development M1 artifact with the freeze-F1 adapter: medoid",
                "coordinates are the manuscript primitive triple (R_IB, D_OB, D_TX); D_TO is",
                "a derived identity check only and never enters the distance.  Partial-q",
                "series are not implemented (freeze F2).",
                "",
                "The earlier real-fast representation records (`artifacts/real_fast/exp2/",
                "exp2_exp2a_*.json`) were produced by the previous adapter (D_TO inside the",
                "medoid distance, no R_IB) and are **SUPERSEDED**; the files are retained",
                "unmodified.",
                "",
                f"- scenario_seed: {scenario_seed}",
                f"- node_count: {node_count}",
                f"- source_artifact_hash: {scenario_hash}",
                f"- FINAL_TEST_ACCESS_COUNT: 0",
                f"- PAPER_FULL_RUN: FALSE",
                "",
            )
        ),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exp2A representation refactor (DEVELOPMENT_ONLY)")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--node-limit", type=int, default=None)
    args = parser.parse_args(argv)
    root = ROOT
    output_root = (args.output_root or ROOT / OUTPUT_ROOT).resolve()
    summary = materialize(root=root, output_root=output_root, node_limit=args.node_limit)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
