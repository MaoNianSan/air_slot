"""Official Exp2 execution over the complete frozen Data2 Development cohort."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from exp.exp2.tail_aware_brier import _event, _observed, _source_pairs
from exp.m2_v2_current_stage_consequence_materialization import (
    M2_DESIGN,
    M2_REGISTRY,
    REFERENCE_FILES,
    REFERENCE_ROOT,
    _compact,
    _m2_input,
    _node_airports,
)
from model.M2.context import build_m2_context, build_m2_frozen_scope, load_data2_reference_bundle
from model.M2.freeze import FrozenData2CUNormalizationRegistry, load_m2_registry
from model.M2.mapper import M2Mapper
from model.common.identity import content_id


SCENARIO_ROOT = Path("artifacts/experiments/exp2/full_development_scenarios_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp2/full_development_v1")
VARIANTS = ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")
SAFETY = {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "DEVELOPMENT_TUNING": False}


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


def _scenario_rows(batch: pa.RecordBatch) -> list[dict[str, Any]]:
    rows = batch.to_pylist()
    for row in rows:
        row["target_envelopes"] = json.loads(row.pop("target_envelopes_json"))
        row["lineage"] = json.loads(row.pop("lineage_json"))
    return rows


def _calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bins = []
    gap = 0.0
    for index in range(10):
        selected = [
            row for row in rows
            if min(int(float(row["event_probability"]) * 10), 9) == index
        ]
        if not selected:
            bins.append({"bin": index, "count": 0, "forecast": None, "observed": None, "gap": None})
            continue
        forecast = mean(float(row["event_probability"]) for row in selected)
        observed = mean(float(row["observed_event"]) for row in selected)
        absolute = abs(forecast - observed)
        gap += len(selected) / len(rows) * absolute
        bins.append({"bin": index, "count": len(selected), "forecast": forecast, "observed": observed, "gap": absolute})
    return {"fixed_bin_calibration_gap": None if not rows else gap, "bins": bins}


def run(
    *, root: Path,
    scenario_root: Path | None = None,
    input_root: Path | None = None,
    output_root: Path | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    scenario_root = (scenario_root or root / SCENARIO_ROOT).resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    scenario_manifest_path = scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
    input_manifest_path = input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
    inputs_path = input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
    labels_path = input_root / "M1_V2_FULL_DEVELOPMENT_LABELS.json"
    required = (scenario_manifest_path, input_manifest_path, inputs_path, labels_path)
    _require(all(path.is_file() for path in required), "EXP2_GLOBAL_INPUT_MISSING")
    scenario_manifest, input_manifest, pre_inputs, labels = map(_load, required)
    scenario_path = root / scenario_manifest["artifact"]
    _require(_sha(scenario_path) == scenario_manifest["artifact_hash"], "EXP2_GLOBAL_SCENARIO_HASH_MISMATCH")
    _require(scenario_manifest["cohort_hash"] == input_manifest["cohort_hash"] == labels["cohort_hash"], "EXP2_GLOBAL_COHORT_HASH_MISMATCH")
    _require(scenario_manifest["safety"] == {**scenario_manifest["safety"], "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False}, "EXP2_GLOBAL_SAFETY_INVALID")

    references = {
        name: _load(root / REFERENCE_ROOT / filename)
        for name, filename in REFERENCE_FILES.items()
    }
    bundle = load_data2_reference_bundle(references)
    registry = load_m2_registry(root / M2_REGISTRY)
    design = _load(root / M2_DESIGN)
    _require(design["formal_aggregate_status"] == "FORMAL_AGGREGATE_UNRESOLVED", "EXP2_GLOBAL_M2_DESIGN_DRIFT")
    mapper = M2Mapper(
        FrozenData2CUNormalizationRegistry(registry),
        build_m2_frozen_scope(registry.model_dump()),
    )
    airports = _node_airports(pre_inputs)
    labels_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in labels["labels"]:
        labels_by_node[row["decision_node_id"]].append(row)

    consequence_path = output_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
    temporary = consequence_path.with_suffix(".parquet.tmp")
    output_root.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    component_support: dict[str, Counter[str]] = defaultdict(Counter)
    formal_status: Counter[str] = Counter()
    seven_status: Counter[str] = Counter()
    brier_rows: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}
    node_count = 0
    row_count = 0
    reference_lineage = tuple(bundle.reference_ids.values())
    parquet = pq.ParquetFile(scenario_path)
    per_node = int(scenario_manifest["scenario_count_per_node"])
    try:
        for batch in parquet.iter_batches(batch_size=per_node):
            source_rows = _scenario_rows(batch)
            node_ids = {row["decision_node_id"] for row in source_rows}
            _require(len(source_rows) == per_node and len(node_ids) == 1, "EXP2_GLOBAL_SCENARIO_NODE_BATCH_INVALID")
            node_id = next(iter(node_ids))
            context = build_m2_context(bundle, airports[node_id])
            mapped = mapper.map_m1_scenarios(
                tuple(_m2_input(row, reference_lineage) for row in source_rows), context,
            )
            compact_rows = [_compact(item) for item in mapped]
            parquet_rows = []
            for compact in compact_rows:
                formal_status[compact["formal_five_component_status"]] += 1
                seven_status[compact["seven_component_status"]] += 1
                for component in compact["components"]:
                    component_support[component["component_id"]][component["support_state"]] += 1
                parquet_rows.append({
                    "episode_id": compact["episode_id"],
                    "decision_node_id": compact["decision_node_id"],
                    "scenario_id": compact["scenario_id"],
                    "scenario_weight": compact["scenario_weight"],
                    "components_json": json.dumps(compact["components"], sort_keys=True),
                    "channels_json": json.dumps(compact["channels"], sort_keys=True),
                    "formal_five_component_value_cu": compact["formal_five_component_value_cu"],
                    "formal_five_component_status": compact["formal_five_component_status"],
                    "formal_five_component_reason": compact["formal_five_component_reason"],
                    "seven_component_value_cu": compact["seven_component_value_cu"],
                    "seven_component_status": compact["seven_component_status"],
                    "seven_component_reason": compact["seven_component_reason"],
                    "consequence_artifact_id": compact["consequence_artifact_id"],
                    "m1_scenario_seed_key": compact["m1_scenario_seed_key"],
                })
            table = pa.Table.from_pylist(parquet_rows)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            writer.write_table(table)

            observed = _observed(labels_by_node.get(node_id, []))
            for variant in VARIANTS:
                events = [_event(ob, tx) for ob, tx in _source_pairs(source_rows, variant)]
                unresolved = sum(value is None for value in events)
                if observed is not None and unresolved == 0:
                    probability = mean(float(value) for value in events)
                    brier_rows[variant].append({
                        "episode_id": source_rows[0]["episode_id"],
                        "decision_node_id": node_id,
                        "event_probability": probability,
                        "observed_event": observed,
                        "brier": (probability - float(observed)) ** 2,
                    })
            node_count += 1
            row_count += len(parquet_rows)
    finally:
        if writer is not None:
            writer.close()
    _require(node_count == scenario_manifest["node_count"] and row_count == scenario_manifest["row_count"], "EXP2_GLOBAL_OUTPUT_CARDINALITY_INVALID")
    temporary.replace(consequence_path)

    metrics: dict[str, Any] = {}
    for variant, rows in brier_rows.items():
        by_episode: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            by_episode[row["episode_id"]].append(float(row["brier"]))
        episode_means = [mean(values) for values in by_episode.values()]
        metrics[variant] = {
            "tail_aware_brier": None if not episode_means else mean(episode_means),
            "supported_node_count": len(rows),
            "abstain_node_count": node_count - len(rows),
            "supported_episode_count": len(by_episode),
            "calibration": _calibration(rows),
            "state_crps": {"value": None, "support_status": "NOT_RUN", "reason": "OVERFLOW_CLASS_HAS_NO_SCALAR_MAGNITUDE"},
            "variogram_score": {"value": None, "support_status": "NOT_RUN", "reason": "OVERFLOW_CLASS_HAS_NO_SCALAR_MAGNITUDE"},
        }
    metrics.update({
        "EXP2B_SCALAR": {"support_status": "NOT_RUN", "reason": "SEVEN_COMPONENT_AGGREGATE_UNRESOLVED"},
        "EXP2B_3CHANNEL": {"support_status": "NOT_RUN", "reason": "PASSENGER_CHANNEL_INCOMPLETE"},
        "EXP2B_7COMP": {"support_status": "PARTIAL", "reason": "TYPED_VECTOR_READY_WITH_P_ITINERARY_AND_P_SERVICE_ABSTAIN"},
        "RMB_RISK": {"support_status": "NOT_RUN", "reason": "COMPLETE_SEVEN_COMPONENT_SCALAR_AND_TAIL_MAGNITUDE_UNAVAILABLE"},
    })
    metrics_payload = {
        "schema_version": "EXP2_FULL_DEVELOPMENT_METRICS_V1",
        "status": "COMPLETE_WITH_GATED_NOT_RUN_RESULTS",
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": input_manifest["episode_count"], "node_count": node_count,
        "metrics": metrics,
        "support_policy": "ABSTAIN_NOT_RUN_NO_ZERO_FILL_NO_SILENT_RENORMALIZATION",
        "safety": dict(SAFETY),
    }
    metrics_payload["artifact_hash"] = content_id(metrics_payload)
    metrics_path = output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json"
    _write(metrics_path, metrics_payload)

    table_path = output_root / "EXP2_FULL_DEVELOPMENT_TABLE.csv"
    with table_path.open("w", newline="", encoding="utf-8") as stream:
        writer_csv = csv.DictWriter(stream, fieldnames=("variant", "brier", "calibration_gap", "supported_nodes", "abstain_nodes"))
        writer_csv.writeheader()
        for variant in VARIANTS:
            row = metrics[variant]
            writer_csv.writerow({
                "variant": variant, "brier": row["tail_aware_brier"],
                "calibration_gap": row["calibration"]["fixed_bin_calibration_gap"],
                "supported_nodes": row["supported_node_count"],
                "abstain_nodes": row["abstain_node_count"],
            })
    interpretation_path = output_root / "EXP2_FULL_DEVELOPMENT_INTERPRETATION.md"
    interpretation_path.write_text(
        "# Exp2 Development Interpretation\n\n"
        "Tail-aware event metrics evaluate point, marginal, and joint representations on supported nodes. "
        "Scalar CRPS, complete RMB risk, and authoritative ranking remain NOT_RUN because the explicit overflow class has no scalar magnitude and the two passenger components remain ABSTAIN.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST_V1",
        "status": metrics_payload["status"],
        "dataset": "DATA2", "split": "DEVELOPMENT",
        "episode_count": input_manifest["episode_count"], "node_count": node_count,
        "frozen_hashes": {
            **scenario_manifest["frozen_hashes"],
            "cohort_hash": scenario_manifest["cohort_hash"],
            "scenario_hash": scenario_manifest["artifact_hash"],
            "mapping_hash": _load(root / "registries/m4_v2_monetary_mapping_design.json")["artifact_hash"],
        },
        "outputs": {
            "consequences": str(consequence_path.relative_to(root)).replace("\\", "/"),
            "metrics": str(metrics_path.relative_to(root)).replace("\\", "/"),
            "table": str(table_path.relative_to(root)).replace("\\", "/"),
            "interpretation": str(interpretation_path.relative_to(root)).replace("\\", "/"),
        },
        "artifact_hashes": {"consequences": _sha(consequence_path), "metrics": metrics_payload["artifact_hash"]},
        "safety": dict(SAFETY),
    }
    manifest["artifact_hash"] = content_id(manifest)
    manifest_path = output_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path, "metrics": metrics_path,
        "consequences": consequence_path, "table": table_path,
        "interpretation": interpretation_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run(
        root=Path(__file__).resolve().parents[2], scenario_root=args.scenario_root,
        input_root=args.input_root, output_root=args.output_root,
    )
    print("EXP2_FULL_DEVELOPMENT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
