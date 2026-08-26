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

from exp.common.metrics_v2 import variogram_score
from exp.exp2.tail_aware_brier import _event, _observed, _point_index, _source_pairs
from exp.exp2.tail_scores import (
    Q_MAX_MINUTES,
    build_node_target_distribution,
    node_scalar_tail_scores,
    pooled_tail_sigma,
)
from exp.workflows.m2_v2_current_stage_consequence_materialization import (
    M2_DESIGN,
    M2_REGISTRY,
    REFERENCE_FILES,
    REFERENCE_ROOT,
    _compact,
    _m2_input,
    _node_airports,
    load_assumption_freeze_id,
)
from model.M2.context import (
    build_assumption_grounded_context,
    build_m2_frozen_scope,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.M2.freeze import FrozenData2CUNormalizationRegistry, load_m2_registry
from model.M2.mapper import M2Mapper
from model.common.identity import content_id


SCENARIO_ROOT = Path("artifacts/experiments/exp2/full_development_scenarios_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
DEFAULT_OUTPUT = Path("artifacts/experiments/exp2/full_development_v1")
VARIANTS = ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")
FIVE_ANCHOR_COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating",
)
PENDING_MONETARY_COMPONENTS = ("P_itinerary", "P_service")
EUR_MAPPING_REGISTRY = Path("registries/m4_eur_mapping_assumption_grounded_v1.json")

# Fixed consequence schema: value columns are double (nullable) so that
# all-ABSTAIN node batches (null columns) stay schema-consistent with
# supported batches. Writer schema is pinned to this contract.
CONSEQUENCE_SCHEMA = pa.schema([
    pa.field("episode_id", pa.string()),
    pa.field("decision_node_id", pa.string()),
    pa.field("scenario_id", pa.int64()),
    pa.field("scenario_weight", pa.float64()),
    pa.field("components_json", pa.string()),
    pa.field("channels_json", pa.string()),
    pa.field("formal_five_component_value_cu", pa.float64()),
    pa.field("formal_five_component_status", pa.string()),
    pa.field("formal_five_component_reason", pa.string()),
    pa.field("seven_component_value_cu", pa.float64()),
    pa.field("seven_component_status", pa.string()),
    pa.field("seven_component_reason", pa.string()),
    pa.field("consequence_artifact_id", pa.string()),
    pa.field("m1_scenario_seed_key", pa.string()),
])
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


def _annotated_components_json(components: list[dict[str, Any]]) -> str:
    """Serialize component rows with event-level NOT_ANCHORED monetary labels.

    P_itinerary/P_service carry event counts (CU = events) but their per-event
    monetary anchors are HUMAN_DECISION_REQUIRED (D2 decision 2026-08-24):
    each such component row is annotated monetary=NOT_ANCHORED.
    """
    annotated = []
    for item in components:
        row = dict(item)
        if row.get("component_id") in PENDING_MONETARY_COMPONENTS:
            row["monetary_status"] = "NOT_ANCHORED"
        annotated.append(row)
    return json.dumps(annotated, sort_keys=True)


def _ranking_metrics_entry(mapping_registry: Path = EUR_MAPPING_REGISTRY) -> dict[str, Any]:
    """Return the explicit five-component monetary contract for this run."""
    registry = json.loads(mapping_registry.read_text(encoding="utf-8"))
    is_rmb = registry.get("monetary_system") == "RMB"
    if is_rmb:
        component_rules = {item["component_id"]: item for item in registry["components"]}
        rates = {
            component: component_rules[component]["beta_k_rmb"]
            for component in FIVE_ANCHOR_COMPONENTS
        }
        units = "RMB"
        reason = "RMB_FIVE_COMPONENT_REPORTING_MAPPING_READY"
        semantics = "FROZEN_REPORTING_MEASUREMENT_MAPPING_NO_CURRENCY_CONVERSION"
    else:
        rates = {
            item["component_id"]: {
                band["band_id"]: band["per_cu_money"] for band in item["bands"]
            }
            for item in registry["ops_components"]
        }
        units = "constructed_EUR"
        reason = "FIVE_ANCHOR_SUBSET_RANKING_CONTRACT_READY_VALUE_MATERIALIZED_AT_FULL_CHAIN_EXECUTION"
        semantics = "CONSTRUCTED_INTERNAL_LOSS_NOT_CAUSAL_NOT_REGRET_NOT_OPTIMAL"
    return {
        "support_status": "ASSUMPTION_GROUNDED",
        "reason": reason,
        "subset": "5-ANCHOR SUBSET",
        "components": list(FIVE_ANCHOR_COMPONENTS),
        "units": units,
        "registry": str(mapping_registry).replace("\\", "/"),
        "registry_hash": registry["registry_hash"],
        "base_rates_per_cu": {
            component: rates[component]["BASE"] for component in FIVE_ANCHOR_COMPONENTS
        },
        "sensitivity_bands": {"LOW": 0.5, "BASE": 1.0, "HIGH": 2.0},
        "semantics": semantics,
        "top1_level": "ASSUMPTION_GROUNDED",
        "expost_level": "ASSUMPTION_GROUNDED",
        "formal_recommendation_level": "ASSUMPTION_GROUNDED",
        "excluded_components": list(PENDING_MONETARY_COMPONENTS),
        "excluded_reason": "MONETARY_ANCHOR_HUMAN_DECISION_REQUIRED_EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
    }


def _interpretation_text() -> str:
    return (
        "# Exp2 Development Interpretation\n\n"
        "Tail-aware event metrics evaluate point, marginal, and joint representations on supported nodes. "
        "Scalar CRPS and twCRPS_tail follow the frozen T-A/T-B/T-C assumption-grounded dual scheme "
        "(T-BASE point mass at q_max; T-PARAM GP with moment-estimated sigma, tail >= 30 samples): "
        "they are not empirical tail calibration. Variogram uses finite-support terms only. "
        "The M4_RANKING contract is the frozen five-anchor subset "
        "(F_continuity/F_execution/F_propagation/P_time/R_operating) in constructed EUR "
        "(EUROCONTROL 2004 EUR-basis anchor; LOW/BASE/HIGH = 0.5x/1.0x/2.0x); TOP1/EXPOST/FORMAL "
        "recommendation levels are ASSUMPTION_GROUNDED and never claim causal/regret/optimal semantics. "
        "P_itinerary and P_service event counts (n_pax x 1[D_TO >= tau]) are annotated "
        "monetary=NOT_ANCHORED in the consequences parquet; their per-event monetary anchors remain "
        "HUMAN_DECISION_REQUIRED and the complete seven-component monetary ranking stays NOT_RUN.\n"
    )


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


def _episode_balanced_aggregate(rows, key, scheme=None):
    by_episode: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(key) if scheme is None else row.get("schemes", {}).get(scheme, {}).get(key)
        if value is not None:
            by_episode[row["episode_id"]].append(float(value))
    return None if not by_episode else mean(mean(values) for values in by_episode.values())


def _tail_scalar_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_target[row["target"]].append(row)
    schemes: dict[str, Any] = {}
    for scheme in ("T-BASE", "T-PARAM"):
        per_target: dict[str, Any] = {}
        for target, target_rows in sorted(by_target.items()):
            available = [row for row in target_rows if scheme in row["schemes"]]
            per_target[target] = {
                "crps": _episode_balanced_aggregate(available, "crps", scheme),
                "crps_finite": _episode_balanced_aggregate(available, "crps_finite", scheme),
                "crps_tail": _episode_balanced_aggregate(available, "crps_tail", scheme),
                "twcrps_tail": _episode_balanced_aggregate(available, "twcrps_tail", scheme),
                "j_tail": _episode_balanced_aggregate(available, "j_tail", scheme),
                "supported_nodes": len(available),
                "supported_episodes": len({row["episode_id"] for row in available}),
            }
        schemes[scheme] = per_target
    pit_values = [row["tail_pit"] for row in rows if row.get("tail_pit") is not None]
    pooled_n = rows[0]["tail_pooled_n"] if rows else 0
    pooled_enabled = rows[0]["tail_pooled_enabled"] if rows else False
    return {
        "support_status": "ASSUMPTION_GROUNDED",
        "aggregation": "EPISODE_BALANCED_MEAN_OF_NODE_SCORES",
        "targets": ["D_OB", "D_TX"],
        "schemes": schemes,
        "tail_pooled": {"n_tail_samples": pooled_n, "enabled": pooled_enabled},
        "tail_pit_diagnostic": {
            "count": len(pit_values),
            "mean_pit": None if not pit_values else mean(pit_values),
            "status": "DIAGNOSTIC_ONLY_NOT_A_GATE",
        },
        "claim": "ASSUMPTION_GROUNDED_NOT_EMPIRICAL_TAIL_CALIBRATION",
        "variants_of_record": ["EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT"],
    }


def _variogram_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_episode: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["value"] is not None:
            by_episode[row["episode_id"]].append(float(row["value"]))
    episode_means = [mean(values) for values in by_episode.values()]
    return {
        "value": None if not episode_means else mean(episode_means),
        "support_status": "SUPPORTED_FINITE_TERMS_ONLY",
        "scope": "FINITE_SUPPORT_PREDICTIVE_AND_OBSERVED_TERMS_ONLY",
        "supported_nodes": len(rows),
        "supported_episodes": len(by_episode),
        "abstain_reason": "OBSERVED_OR_PREDICTIVE_TAIL_TERM_ABSTAINED",
    }


def _build_manifest(
    *, root: Path, input_manifest: dict[str, Any], scenario_manifest: dict[str, Any],
    node_count: int, consequence_path: Path, metrics_path: Path, table_path: Path,
    interpretation_path: Path, metrics_payload: dict[str, Any],
    scope: str = "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
    split: str = "DEVELOPMENT",
    mapping_registry: Path = EUR_MAPPING_REGISTRY,
    safety: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_rmb = mapping_registry.name == "m4_rmb_mapping_v1.json"
    manifest = {
        "schema_version": "EXP2_EXECUTION_MANIFEST_V2",
        "status": metrics_payload["status"],
        "scope": scope,
        "dataset": "DATA2", "split": split,
        "episode_count": input_manifest["episode_count"], "node_count": node_count,
        "frozen_hashes": {
            **scenario_manifest["frozen_hashes"],
            "cohort_hash": scenario_manifest["cohort_hash"],
            "scenario_hash": scenario_manifest.get(
                "artifact_hash",
                scenario_manifest.get("models", {}).get("M1_V2_GRU_H32", {}).get("artifact_hash"),
            ),
            "mapping_hash": _sha(root / mapping_registry),
            "mapping_registry": str(mapping_registry).replace("\\", "/"),
        },
        "consequence_annotation": (
            "P_ITINERARY_P_SERVICE_NOT_IN_MAIN_MONETARY_SCOPE"
            if final_rmb else "P_ITINERARY_P_SERVICE_EVENT_COUNTS_MONETARY_NOT_ANCHORED"
        ),
        "outputs": {
            "consequences": str(consequence_path.relative_to(root)).replace("\\", "/"),
            "metrics": str(metrics_path.relative_to(root)).replace("\\", "/"),
            "table": str(table_path.relative_to(root)).replace("\\", "/"),
            "interpretation": str(interpretation_path.relative_to(root)).replace("\\", "/"),
        },
        "artifact_hashes": {"consequences": _sha(consequence_path), "metrics": metrics_payload["artifact_hash"]},
        "safety": dict(SAFETY) if safety is None else dict(safety),
    }
    manifest["artifact_hash"] = content_id(manifest)
    return manifest


def run(
    *, root: Path,
    scenario_root: Path | None = None,
    input_root: Path | None = None,
    output_root: Path | None = None,
    final_test: bool = False,
    monetary_registry: Path | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    scenario_root = (scenario_root or root / SCENARIO_ROOT).resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    if final_test:
        scope = "FINAL_TEST_OUT_OF_TIME_2019_10_12"
        split = "FINAL_TEST"
        scenario_manifest_path = scenario_root / "FINAL_TEST_SCENARIO_MANIFEST.json"
        input_manifest_path = input_root / "FINAL_TEST_INPUT_MANIFEST.json"
        inputs_path = input_root / "M1_V2_FINAL_TEST_INFERENCE_INPUTS.json"
        labels_path = input_root / "M1_V2_FINAL_TEST_LABELS.json"
        consequence_name = "M2_FINAL_TEST_CONSEQUENCES.parquet"
        metrics_name = "EXP2_FINAL_TEST_METRICS.json"
        table_name = "EXP2_FINAL_TEST_TABLE.csv"
        interpretation_name = "EXP2_FINAL_TEST_INTERPRETATION.md"
        manifest_name = "EXP2_FINAL_TEST_EXECUTION_MANIFEST.json"
        mapping_registry = monetary_registry or Path("registries/m4_rmb_mapping_v1.json")
        safety = {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": True,
            "MODEL_RETRAINED": False,
            "PARAMETER_RESELECTED": False,
        }
    else:
        scope = "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST"
        split = "DEVELOPMENT"
        scenario_manifest_path = scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
        input_manifest_path = input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
        inputs_path = input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
        labels_path = input_root / "M1_V2_FULL_DEVELOPMENT_LABELS.json"
        consequence_name = "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
        metrics_name = "EXP2_FULL_DEVELOPMENT_METRICS.json"
        table_name = "EXP2_FULL_DEVELOPMENT_TABLE.csv"
        interpretation_name = "EXP2_FULL_DEVELOPMENT_INTERPRETATION.md"
        manifest_name = "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
        mapping_registry = EUR_MAPPING_REGISTRY
        safety = dict(SAFETY)
    required = (scenario_manifest_path, input_manifest_path, inputs_path, labels_path)
    _require(all(path.is_file() for path in required), "EXP2_GLOBAL_INPUT_MISSING")
    scenario_manifest, input_manifest, pre_inputs, labels = map(_load, required)
    if final_test:
        # This is derived from the four Final Test artifacts read above, not a
        # sentinel.  It records the direct held-out reads performed by Exp2.
        safety["FINAL_TEST_ACCESS_COUNT"] = len(required)
    scenario_entry = scenario_manifest.get("models", {}).get("M1_V2_GRU_H32", {})
    scenario_artifact = scenario_manifest.get("artifact", scenario_entry.get("artifact"))
    scenario_hash = scenario_manifest.get("artifact_hash", scenario_entry.get("artifact_hash"))
    _require(scenario_artifact is not None and scenario_hash is not None, "EXP2_GLOBAL_SCENARIO_BINDING_MISSING")
    scenario_path = root / scenario_artifact
    _require(_sha(scenario_path) == scenario_hash, "EXP2_GLOBAL_SCENARIO_HASH_MISMATCH")
    _require(scenario_manifest["cohort_hash"] == input_manifest["cohort_hash"] == labels["cohort_hash"], "EXP2_GLOBAL_COHORT_HASH_MISMATCH")
    _require(
        (scenario_manifest["safety"].get("FINAL_TEST_ACCESS_COUNT", 0) > 0)
        if final_test
        else scenario_manifest["safety"] == {**scenario_manifest["safety"], "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False},
        "EXP2_GLOBAL_SAFETY_INVALID",
    )
    _require(
        input_manifest.get("scope") == scope if final_test else True,
        "EXP2_GLOBAL_INPUT_SCOPE_INVALID",
    )

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

    tail_excesses: dict[str, list[float]] = {target: [] for target in ("D_OB", "D_TX")}
    for row in labels["labels"]:
        if row["target_name"] not in tail_excesses or row["exact_minutes"] is None:
            continue
        raw = float(row["exact_minutes"])
        if raw >= Q_MAX_MINUTES[row["target_name"]]:
            tail_excesses[row["target_name"]].append(raw - Q_MAX_MINUTES[row["target_name"]])
    pooled_tails = {target: pooled_tail_sigma(values) for target, values in tail_excesses.items()}

    consequence_path = output_root / consequence_name
    temporary = consequence_path.with_suffix(".parquet.tmp")
    output_root.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    component_support: dict[str, Counter[str]] = defaultdict(Counter)
    formal_status: Counter[str] = Counter()
    seven_status: Counter[str] = Counter()
    brier_rows: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}
    crps_rows: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}
    variogram_rows: list[dict[str, Any]] = []
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
            airport_keys = airports[node_id]
            context = build_assumption_grounded_context(
                bundle,
                airport_keys,
                node_specific_exposure=build_node_exposure_references(
                    bundle, airport_keys
                ).airport,
                assumption_freeze_id=load_assumption_freeze_id(root),
            )
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
                    "components_json": _annotated_components_json(compact["components"]),
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
            table = pa.Table.from_pylist(parquet_rows).cast(CONSEQUENCE_SCHEMA)
            if writer is None:
                writer = pq.ParquetWriter(temporary, CONSEQUENCE_SCHEMA, compression="zstd")
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
            label_map = {row["target_name"]: row for row in labels_by_node.get(node_id, [])}
            for variant in VARIANTS:
                selected = source_rows if variant != "EXP2A_POINT" else [source_rows[_point_index(source_rows)]]
                for target in ("D_OB", "D_TX"):
                    envelopes = [
                        next(item for item in row["target_envelopes"] if item["target_name"] == target)
                        for row in selected
                    ]
                    observed_row = label_map.get(target)
                    observation = None if observed_row is None else observed_row.get("exact_minutes")
                    distribution = build_node_target_distribution(
                        envelopes, target=target, q_max=Q_MAX_MINUTES[target],
                    )
                    scores = node_scalar_tail_scores(
                        distribution, observation=observation, pooled=pooled_tails[target],
                    )
                    if scores is not None:
                        crps_rows[variant].append({
                            "episode_id": source_rows[0]["episode_id"],
                            "decision_node_id": node_id,
                            "target": target,
                            **scores,
                        })
            finite_draws = []
            for row in source_rows:
                envs = {item["target_name"]: item for item in row["target_envelopes"]}
                ob_env, tx_env = envs.get("D_OB"), envs.get("D_TX")
                if (
                    ob_env is not None and tx_env is not None
                    and ob_env.get("class_id") != "OVERFLOW_TAIL"
                    and tx_env.get("class_id") != "OVERFLOW_TAIL"
                    and ob_env.get("scalar_minutes") is not None
                    and tx_env.get("scalar_minutes") is not None
                ):
                    finite_draws.append({
                        "D_OB": float(ob_env["scalar_minutes"]),
                        "D_TX": float(tx_env["scalar_minutes"]),
                    })
            ob_observed = label_map.get("D_OB")
            tx_observed = label_map.get("D_TX")
            ob_value = None if ob_observed is None else ob_observed.get("exact_minutes")
            tx_value = None if tx_observed is None else tx_observed.get("exact_minutes")
            if (
                finite_draws and ob_value is not None and tx_value is not None
                and float(ob_value) < Q_MAX_MINUTES["D_OB"]
                and float(tx_value) < Q_MAX_MINUTES["D_TX"]
            ):
                variogram_value = variogram_score(
                    finite_draws, {"D_OB": float(ob_value), "D_TX": float(tx_value)},
                )
            else:
                variogram_value = None
            variogram_rows.append({
                "episode_id": source_rows[0]["episode_id"],
                "decision_node_id": node_id,
                "value": variogram_value,
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
        variogram = _variogram_metrics(variogram_rows)
        metrics[variant] = {
            "tail_aware_brier": None if not episode_means else mean(episode_means),
            "supported_node_count": len(rows),
            "abstain_node_count": node_count - len(rows),
            "supported_episode_count": len(by_episode),
            "calibration": _calibration(rows),
            "state_crps": _tail_scalar_metrics(crps_rows[variant]),
            "variogram_score": variogram,
        }
    metrics.update({
        "EXP2B_SCALAR": {"support_status": "NOT_RUN", "reason": "SEVEN_COMPONENT_AGGREGATE_UNRESOLVED"},
        "EXP2B_3CHANNEL": {"support_status": "NOT_RUN", "reason": "PASSENGER_CHANNEL_INCOMPLETE"},
        "EXP2B_7COMP": {"support_status": "PARTIAL", "reason": "TYPED_VECTOR_READY_WITH_P_ITINERARY_AND_P_SERVICE_ABSTAIN"},
        "M4_RANKING": _ranking_metrics_entry(mapping_registry),
    })
    metrics_payload = {
        "schema_version": "EXP2_METRICS_V2",
        "status": "COMPLETE_WITH_GATED_NOT_RUN_RESULTS",
        "scope": scope,
        "dataset": "DATA2", "split": split,
        "episode_count": input_manifest["episode_count"], "node_count": node_count,
        "metrics": metrics,
        "support_policy": "ABSTAIN_NOT_RUN_NO_ZERO_FILL_NO_SILENT_RENORMALIZATION",
        "safety": safety,
    }
    metrics_payload["artifact_hash"] = content_id(metrics_payload)
    metrics_path = output_root / metrics_name
    _write(metrics_path, metrics_payload)

    table_path = output_root / table_name
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
    interpretation_path = output_root / interpretation_name
    interpretation_path.write_text(
        _interpretation_text().replace("Development", "Final Test") if final_test else _interpretation_text(),
        encoding="utf-8",
    )
    manifest = _build_manifest(
        root=root, input_manifest=input_manifest, scenario_manifest=scenario_manifest,
        node_count=node_count, consequence_path=consequence_path,
        metrics_path=metrics_path, table_path=table_path,
        interpretation_path=interpretation_path, metrics_payload=metrics_payload,
        scope=scope, split=split, mapping_registry=mapping_registry, safety=safety,
    )
    manifest_path = output_root / manifest_name
    _write(manifest_path, manifest)
    return {
        "manifest": manifest_path, "metrics": metrics_path,
        "consequences": consequence_path, "table": table_path,
        "interpretation": interpretation_path,
    }


def annotate_consequences_monetary_status(consequence_path: Path) -> None:
    """Annotate P_itinerary/P_service rows with monetary=NOT_ANCHORED (D2).

    Idempotent display-only pass over the frozen consequences parquet: numeric
    values, consequence_artifact_id and all other columns are preserved; only
    the JSON components annotation gains the monetary-status label for the two
    HUMAN_DECISION_REQUIRED passenger components.
    """
    source = Path(consequence_path)
    _require(source.is_file(), "EXP2_ANNOTATE_CONSEQUENCES_MISSING")
    temporary = source.with_name(source.name + ".annotated.tmp")
    reader = pq.ParquetFile(source)
    writer = pq.ParquetWriter(temporary, CONSEQUENCE_SCHEMA, compression="zstd")
    total = 0
    annotated_rows = 0
    checked_rows = 0
    try:
        for row_group in range(reader.num_row_groups):
            rows = reader.read_row_group(row_group).to_pylist()
            updated = []
            for row in rows:
                components = json.loads(row["components_json"])
                component_ids = {item.get("component_id") for item in components}
                _require(
                    component_ids.issuperset(PENDING_MONETARY_COMPONENTS),
                    "EXP2_ANNOTATE_PENDING_COMPONENT_MISSING",
                )
                checked_rows += 1
                changed = False
                for item in components:
                    if item.get("component_id") in PENDING_MONETARY_COMPONENTS and "monetary_status" not in item:
                        item["monetary_status"] = "NOT_ANCHORED"
                        changed = True
                if changed:
                    row["components_json"] = json.dumps(components, sort_keys=True)
                    annotated_rows += 1
                updated.append(row)
            writer.write_table(pa.Table.from_pylist(updated).cast(CONSEQUENCE_SCHEMA))
            total += len(updated)
    finally:
        writer.close()
        reader.close()
    _require(total == reader.metadata.num_rows, "EXP2_ANNOTATE_ROW_COUNT_DRIFT")
    _require(checked_rows == total, "EXP2_ANNOTATE_MISSING_PENDING_COMPONENTS")
    temporary.replace(source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--annotate-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    scenario_root = (args.scenario_root or root / SCENARIO_ROOT).resolve()
    input_root = (args.input_root or root / INPUT_ROOT).resolve()
    output_root = (args.output_root or root / DEFAULT_OUTPUT).resolve()
    if args.finalize_only:
        scenario_manifest = _load(scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json")
        input_manifest = _load(input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json")
        metrics_path = output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json"
        consequence_path = output_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
        table_path = output_root / "EXP2_FULL_DEVELOPMENT_TABLE.csv"
        interpretation_path = output_root / "EXP2_FULL_DEVELOPMENT_INTERPRETATION.md"
        metrics_payload = _load(metrics_path)
        manifest = _build_manifest(
            root=root, input_manifest=input_manifest, scenario_manifest=scenario_manifest,
            node_count=scenario_manifest["node_count"], consequence_path=consequence_path,
            metrics_path=metrics_path, table_path=table_path,
            interpretation_path=interpretation_path, metrics_payload=metrics_payload,
        )
        manifest_path = output_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
        _write(manifest_path, manifest)
        print(json.dumps({"status": "EXP2_FULL_DEVELOPMENT_FINALIZED", "manifest": str(manifest_path)}, sort_keys=True))
        return 0
    if args.annotate_only:
        consequence_path = output_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
        metrics_path = output_root / "EXP2_FULL_DEVELOPMENT_METRICS.json"
        table_path = output_root / "EXP2_FULL_DEVELOPMENT_TABLE.csv"
        interpretation_path = output_root / "EXP2_FULL_DEVELOPMENT_INTERPRETATION.md"
        manifest_path = output_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
        _require(all(path.is_file() for path in (consequence_path, metrics_path, interpretation_path, manifest_path)), "EXP2_ANNOTATE_INPUT_MISSING")
        annotate_consequences_monetary_status(consequence_path)
        metrics_payload = _load(metrics_path)
        metrics = metrics_payload["metrics"]
        if "RMB_RISK" in metrics:
            del metrics["RMB_RISK"]
        metrics["M4_RANKING"] = _ranking_metrics_entry()
        metrics_payload["artifact_hash"] = content_id(metrics_payload)
        _write(metrics_path, metrics_payload)
        interpretation_path.write_text(_interpretation_text(), encoding="utf-8")
        scenario_manifest = _load(scenario_root / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json")
        input_manifest = _load(input_root / "FULL_DEVELOPMENT_INPUT_MANIFEST.json")
        manifest = _build_manifest(
            root=root, input_manifest=input_manifest, scenario_manifest=scenario_manifest,
            node_count=scenario_manifest["node_count"], consequence_path=consequence_path,
            metrics_path=metrics_path, table_path=table_path,
            interpretation_path=interpretation_path, metrics_payload=metrics_payload,
        )
        _write(manifest_path, manifest)
        print(json.dumps({
            "status": "EXP2_FULL_DEVELOPMENT_ANNOTATED",
            "consequences_hash": _sha(consequence_path),
            "manifest": str(manifest_path),
        }, sort_keys=True))
        return 0
    run(
        root=root, scenario_root=scenario_root,
        input_root=input_root, output_root=output_root,
    )
    print("EXP2_FULL_DEVELOPMENT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
