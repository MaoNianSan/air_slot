"""Development-only Exp2A downstream consequence-distortion materialization.

This is a representation diagnostic.  It maps the same frozen M1 Development
scenario artifact through POINT, MARGINAL, and JOINT representations, then
compares component distributions.  It does not rank actions or emit an
operational recommendation.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from exp.exp2.representation import ScenarioRepresentationAdapter
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
DEFAULT_OUTPUT = Path("artifacts/experiment/exp2/exp2_downstream_consequence_distortion_20260826")
M1_ARTIFACT = "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
M1_MANIFEST = "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
PRE_INPUTS = "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation", "P_time",
    "P_itinerary", "P_service", "R_operating",
)
COMPONENT_CHANNELS = {
    "F_continuity": "Flight", "F_execution": "Flight", "F_propagation": "Flight",
    "P_time": "Passenger", "P_itinerary": "Passenger", "P_service": "Passenger",
    "R_operating": "Resource",
}
VARIANTS = ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")
COMPARISONS = (("EXP2A_POINT", "POINT_MINUS_JOINT"), ("EXP2A_MARGINAL", "MARGINAL_MINUS_JOINT"))
ALPHA = 0.90
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20260825
SAFETY = {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "DEVELOPMENT_TUNING": False}
_WORKER_STATE: dict[str, Any] | None = None


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _valid_distribution(values: Iterable[Any], weights: Iterable[Any]) -> tuple[np.ndarray, np.ndarray]:
    value_array = np.asarray(tuple(values), dtype=float)
    weight_array = np.asarray(tuple(weights), dtype=float)
    _require(len(value_array) > 0 and len(value_array) == len(weight_array), "SCENARIO_DISTRIBUTION_EMPTY")
    _require(np.isfinite(value_array).all(), "NONFINITE_COMPONENT_VALUE")
    _require(np.isfinite(weight_array).all() and (weight_array >= 0).all(), "SCENARIO_WEIGHT_INVALID")
    _require(abs(float(weight_array.sum()) - 1.0) <= 1e-9, "SCENARIO_WEIGHT_INVALID")
    return value_array, weight_array


def weighted_mean(values: Iterable[Any], weights: Iterable[Any]) -> float:
    """Strict weighted mean: invalid distributions are never re-normalized."""
    value_array, weight_array = _valid_distribution(values, weights)
    return float(np.dot(value_array, weight_array))


def weighted_cvar(values: Iterable[Any], weights: Iterable[Any], alpha: float = ALPHA) -> float:
    """Upper-tail weighted CVaR with exact boundary-mass splitting."""
    _require(0.0 < alpha < 1.0, "CVAR_ALPHA_INVALID")
    value_array, weight_array = _valid_distribution(values, weights)
    order = np.argsort(value_array, kind="stable")
    remaining = 1.0 - alpha
    total = 0.0
    for index in order[::-1]:
        if remaining <= 1e-12:
            break
        mass = min(float(weight_array[index]), remaining)
        total += mass * float(value_array[index])
        remaining -= mass
    _require(remaining <= 1e-9, "SCENARIO_WEIGHT_INVALID")
    return total / (1.0 - alpha)


def episode_aggregate(node_records: pd.DataFrame) -> pd.DataFrame:
    """Aggregate node-level distortions inside episode before any bootstrap."""
    columns = [
        "episode_id", "component", "channel", "comparison",
        "absolute_mean_distortion", "absolute_tail_distortion",
    ]
    if node_records.empty:
        return pd.DataFrame(columns=columns + ["n_nodes"])
    result = node_records.groupby(columns[:4], as_index=False).agg(
        absolute_mean_distortion=("absolute_mean_distortion", "mean"),
        absolute_tail_distortion=("absolute_tail_distortion", "mean"),
        n_nodes=("decision_node_id", "nunique"),
    )
    return result.sort_values(columns[:4], kind="stable").reset_index(drop=True)


def bootstrap_summary(
    episode_values: pd.DataFrame, *, reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED, excluded_counts: dict[str, int] | None = None,
) -> pd.DataFrame:
    columns = [
        "component", "channel", "comparison", "mean_distortion", "mean_ci_lower", "mean_ci_upper",
        "tail_distortion", "tail_ci_lower", "tail_ci_upper", "N_episode", "N_node",
        "excluded_node_count", "bootstrap_reps", "bootstrap_seed",
    ]
    if episode_values.empty:
        return pd.DataFrame(columns=columns)
    rng = np.random.default_rng(seed)
    records: list[dict[str, Any]] = []
    for keys, group in episode_values.groupby(["component", "channel", "comparison"], sort=True):
        means = group["absolute_mean_distortion"].to_numpy(dtype=float)
        cvars = group["absolute_tail_distortion"].to_numpy(dtype=float)
        draws = rng.integers(0, len(group), size=(reps, len(group)))
        mean_boot = means[draws].mean(axis=1)
        cvar_boot = cvars[draws].mean(axis=1)
        records.append({
            "component": keys[0], "channel": keys[1], "comparison": keys[2],
            "mean_distortion": float(means.mean()),
            "mean_ci_lower": float(np.quantile(mean_boot, 0.025)),
            "mean_ci_upper": float(np.quantile(mean_boot, 0.975)),
            "tail_distortion": float(cvars.mean()),
            "tail_ci_lower": float(np.quantile(cvar_boot, 0.025)),
            "tail_ci_upper": float(np.quantile(cvar_boot, 0.975)),
            "N_episode": int(group["episode_id"].nunique()),
            "N_node": int(group["n_nodes"].sum()),
            "excluded_node_count": int((excluded_counts or {}).get(keys[0], 0)),
            "bootstrap_reps": reps, "bootstrap_seed": seed,
        })
    present = {(item["component"], item["comparison"]) for item in records}
    for component in COMPONENTS:
        for _, comparison in COMPARISONS:
            if (component, comparison) in present:
                continue
            records.append({
                "component": component, "channel": COMPONENT_CHANNELS[component],
                "comparison": comparison, "mean_distortion": None,
                "mean_ci_lower": None, "mean_ci_upper": None, "tail_distortion": None,
                "tail_ci_lower": None, "tail_ci_upper": None, "N_episode": 0, "N_node": 0,
                "excluded_node_count": int((excluded_counts or {}).get(component, 0)),
                "bootstrap_reps": reps, "bootstrap_seed": seed,
            })
    return pd.DataFrame(records, columns=columns).sort_values(
        ["component", "comparison"], kind="stable"
    ).reset_index(drop=True)


def _component_distribution(compact_rows: list[dict[str, Any]], component_id: str) -> tuple[dict[str, float] | None, str | None]:
    values: list[float] = []
    weights: list[float] = []
    for row in compact_rows:
        matching = [item for item in row["components"] if item["component_id"] == component_id]
        if len(matching) != 1 or matching[0].get("support_state") != "SUPPORTED":
            return None, "COMPONENT_ABSTAIN"
        value = matching[0].get("constructed_value_cu")
        if value is None or not math.isfinite(float(value)):
            return None, "NONFINITE_COMPONENT_VALUE"
        values.append(float(value))
        weights.append(float(row["scenario_weight"]))
    try:
        return {"mean": weighted_mean(values, weights), "cvar": weighted_cvar(values, weights)}, None
    except RuntimeError as error:
        return None, str(error)


def _field_source_note(sample: Any) -> str:
    return content_id({"field_source_scenario_ids": sample.field_source_scenario_ids})


def adapted_m2_row(base: dict[str, Any], sample: Any, *, variant_id: str, representation_hash: str) -> dict[str, Any]:
    """Clone one frozen source row while retaining all actual source lineage."""
    source_id = sample.field_source_scenario_ids["D_OB"] if str(sample.scenario_id).startswith("POINT:") else sample.scenario_id
    result = dict(base)
    result["scenario_id"] = int(source_id)
    result["scenario_weight"] = float(sample.scenario_weight)
    result["T_IB_A00"] = sample.R_IB
    result["D_OB"] = sample.D_OB
    result["D_TX"] = sample.D_TX
    result["D_TO"] = sample.D_TO
    envelopes = []
    replacements = {"T_IB_A00": sample.R_IB, "D_OB": sample.D_OB, "D_TX": sample.D_TX}
    for item in base["target_envelopes"]:
        copied = dict(item)
        if copied["target_name"] in replacements:
            copied["scalar_minutes"] = replacements[copied["target_name"]]
            copied["scalar_support_state"] = (
                "SUPPORTED" if replacements[copied["target_name"]] is not None
                else "ABSTAIN_TAIL_CLASS"
            )
        envelopes.append(copied)
    result["target_envelopes"] = envelopes
    result["lineage"] = tuple(base["lineage"]) + (
        f"EXP2A_VARIANT:{variant_id}", f"EXP2A_REPRESENTATION:{representation_hash}",
        f"EXP2A_FIELD_SOURCE_LINEAGE:{_field_source_note(sample)}",
    )
    return result


def _scenario_rows(batch: Any) -> list[dict[str, Any]]:
    records = []
    raw_records = batch.to_pylist() if hasattr(batch, "to_pylist") else batch.to_dict(orient="records")
    for item in raw_records:
        item["target_envelopes"] = json.loads(item.pop("target_envelopes_json"))
        item["lineage"] = tuple(json.loads(item.pop("lineage_json")))
        records.append(item)
    return records


def _map_variant(
    *, rows: list[dict[str, Any]], variant_id: str, source_hash: str, artifact_version: str,
    mapper: M2Mapper, bundle: Any, airports: dict[str, Any], assumption_freeze_id: str,
) -> tuple[list[dict[str, Any]], str]:
    adapter = ScenarioRepresentationAdapter(rows, artifact_version=artifact_version, scenario_hash=source_hash)
    representation = adapter.transform(variant_id)
    by_id = {int(row["scenario_id"]): row for row in rows}
    adapted = []
    for sample in representation.samples:
        source_id = sample.field_source_scenario_ids["D_OB"] if str(sample.scenario_id).startswith("POINT:") else sample.scenario_id
        adapted.append(adapted_m2_row(by_id[int(source_id)], sample, variant_id=variant_id, representation_hash=representation.representation_hash))
    node_id = str(rows[0]["decision_node_id"])
    airport = airports[node_id]
    context = build_assumption_grounded_context(
        bundle,
        airport,
        node_specific_exposure=build_node_exposure_references(bundle, airport).airport,
        assumption_freeze_id=assumption_freeze_id,
    )
    reference_lineage = tuple(bundle.reference_ids.values())
    mapped = mapper.map_m1_scenarios(
        tuple(_m2_input(row, reference_lineage) for row in adapted), context,
    )
    return [_compact(item) for item in mapped], representation.representation_hash


def _build_mapping_state(root: Path) -> dict[str, Any]:
    manifest = _load(root / SCENARIO_ROOT / M1_MANIFEST)
    pre_inputs = _load(root / INPUT_ROOT / PRE_INPUTS)
    bundle = load_data2_reference_bundle({
        name: _load(root / REFERENCE_ROOT / filename)
        for name, filename in REFERENCE_FILES.items()
    })
    registry = load_m2_registry(root / M2_REGISTRY)
    return {
        "root": root,
        "artifact_version": str(manifest.get("schema_version", "M1_V2")),
        "source_hash": _sha(root / SCENARIO_ROOT / M1_ARTIFACT),
        "bundle": bundle,
        "mapper": M2Mapper(
            FrozenData2CUNormalizationRegistry(registry),
            build_m2_frozen_scope(registry.model_dump()),
        ),
        "airports": _node_airports(pre_inputs),
        "assumption_freeze_id": load_assumption_freeze_id(root),
    }


def _initialize_worker(root_text: str) -> None:
    global _WORKER_STATE
    _WORKER_STATE = _build_mapping_state(Path(root_text))


def _process_node(rows: list[dict[str, Any]], state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    _require(len(rows) == 250 and len({row["decision_node_id"] for row in rows}) == 1, "EXP2A_DOWNSTREAM_NODE_BATCH_INVALID")
    node_records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    hashes: list[str] = []
    mapped: dict[str, list[dict[str, Any]]] = {}
    mapping_errors: dict[str, tuple[str, str]] = {}
    for variant_id in VARIANTS:
        try:
            mapped[variant_id], rep_hash = _map_variant(
                rows=rows, variant_id=variant_id,
                source_hash=state["source_hash"], artifact_version=state["artifact_version"],
                mapper=state["mapper"], bundle=state["bundle"], airports=state["airports"],
                assumption_freeze_id=state["assumption_freeze_id"],
            )
            hashes.append(rep_hash)
        except Exception as error:  # Typed exclusion; never silently substitute a representation.
            code = "M2_CONTEXT_UNAVAILABLE" if "CONTEXT" in str(error) else "REPRESENTATION_MAPPING_INVALID"
            mapping_errors[variant_id] = (code, str(error))
    for component_id in COMPONENTS:
        distributions: dict[str, dict[str, float]] = {}
        failures: dict[str, str] = {}
        for variant_id in VARIANTS:
            if variant_id not in mapped:
                failures[variant_id] = mapping_errors.get(
                    variant_id, ("REPRESENTATION_MAPPING_INVALID", "mapping output unavailable")
                )[0]
                continue
            distribution, reason = _component_distribution(mapped[variant_id], component_id)
            if reason:
                failures[variant_id] = reason
            else:
                distributions[variant_id] = distribution  # type: ignore[assignment]
        if failures:
            for variant_id, reason in failures.items():
                exclusions.append({
                    "episode_id": rows[0]["episode_id"], "decision_node_id": rows[0]["decision_node_id"],
                    "component_id": component_id, "variant_id": variant_id, "reason_code": reason,
                    "detail": mapping_errors.get(
                        variant_id,
                        (reason, "all scenarios required; no drop, reweight, or zero-fill"),
                    )[1],
                })
            continue
        channel = next(
            item["aspect"] for item in mapped["EXP2A_JOINT"][0]["components"]
            if item["component_id"] == component_id
        )
        for variant_id, comparison in COMPARISONS:
            node_records.append({
                "episode_id": rows[0]["episode_id"], "decision_node_id": rows[0]["decision_node_id"],
                    "operational_stage": rows[0]["operational_stage"], "component": component_id,
                    "channel": channel, "comparison": comparison, "comparison_variant": variant_id,
                    "variant_mean": distributions[variant_id]["mean"],
                    "joint_mean": distributions["EXP2A_JOINT"]["mean"],
                    "signed_mean_difference": distributions[variant_id]["mean"] - distributions["EXP2A_JOINT"]["mean"],
                    "absolute_mean_distortion": abs(distributions[variant_id]["mean"] - distributions["EXP2A_JOINT"]["mean"]),
                    "variant_cvar_90": distributions[variant_id]["cvar"],
                    "joint_cvar_90": distributions["EXP2A_JOINT"]["cvar"],
                    "signed_tail_difference": distributions[variant_id]["cvar"] - distributions["EXP2A_JOINT"]["cvar"],
                    "absolute_tail_distortion": abs(distributions[variant_id]["cvar"] - distributions["EXP2A_JOINT"]["cvar"]),
                    "common_support": True,
            })
    return node_records, exclusions, hashes


def _process_node_worker(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    _require(_WORKER_STATE is not None, "EXP2A_DOWNSTREAM_WORKER_NOT_INITIALIZED")
    return _process_node(rows, _WORKER_STATE)


def materialize(*, root: Path, output_root: Path | None = None, workers: int | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output = (root / DEFAULT_OUTPUT if output_root is None else Path(output_root)).resolve()
    paths = {
        "m1_artifact": root / SCENARIO_ROOT / M1_ARTIFACT,
        "m1_manifest": root / SCENARIO_ROOT / M1_MANIFEST,
        "pre_inputs": root / INPUT_ROOT / PRE_INPUTS,
        "m2_registry": root / M2_REGISTRY, "m2_design": root / M2_DESIGN,
        **{name: root / REFERENCE_ROOT / filename for name, filename in REFERENCE_FILES.items()},
    }
    _require(all(path.is_file() for path in paths.values()), "EXP2A_DOWNSTREAM_INPUT_MISSING")
    manifest = _load(paths["m1_manifest"])
    _require("DEVELOPMENT" in str(manifest.get("scope", "")), "EXP2A_DOWNSTREAM_NOT_DEVELOPMENT")
    _require(manifest.get("safety", {}).get("FINAL_TEST_ACCESS_COUNT", 0) == 0, "EXP2A_DOWNSTREAM_FINAL_TEST_FORBIDDEN")
    design = _load(paths["m2_design"])
    _require(design["formal_aggregate_status"] == "FORMAL_AGGREGATE_UNRESOLVED", "EXP2A_DOWNSTREAM_M2_DESIGN_DRIFT")
    source_hash = _sha(paths["m1_artifact"])
    node_records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    representation_hashes: set[str] = set()
    table = pq.ParquetFile(paths["m1_artifact"])
    worker_count = max(1, workers if workers is not None else min(12, os.cpu_count() or 1))

    def collect(result: tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]) -> None:
        records, rejected, hashes = result
        node_records.extend(records)
        exclusions.extend(rejected)
        representation_hashes.update(hashes)

    batches = (_scenario_rows(batch) for batch in table.iter_batches(batch_size=250))
    processed = 0
    if worker_count == 1:
        state = _build_mapping_state(root)
        for rows in batches:
            collect(_process_node(rows, state))
            processed += 1
            if processed % 100 == 0:
                print(f"EXP2A_DOWNSTREAM_PROGRESS={processed}/{manifest['node_count']}", flush=True)
    else:
        with ProcessPoolExecutor(
            max_workers=worker_count, initializer=_initialize_worker, initargs=(str(root),),
        ) as executor:
            while True:
                group: list[list[dict[str, Any]]] = []
                for _ in range(worker_count * 2):
                    try:
                        group.append(next(batches))
                    except StopIteration:
                        break
                if not group:
                    break
                for result in executor.map(_process_node_worker, group, chunksize=1):
                    collect(result)
                    processed += 1
                if processed % 100 < worker_count * 2:
                    print(f"EXP2A_DOWNSTREAM_PROGRESS={processed}/{manifest['node_count']}", flush=True)
    node_frame = pd.DataFrame(node_records)
    episode_frame = episode_aggregate(node_frame)
    excluded_counts = (
        pd.DataFrame(exclusions).groupby("component_id")["decision_node_id"].nunique().to_dict()
        if exclusions else {}
    )
    summary_frame = bootstrap_summary(episode_frame, excluded_counts=excluded_counts)
    stage_frame = (node_frame.groupby(["operational_stage", "component", "channel", "comparison"], as_index=False).agg(
        n_nodes=("decision_node_id", "nunique"),
        mean_absolute_mean_distortion=("absolute_mean_distortion", "mean"),
        mean_absolute_tail_distortion=("absolute_tail_distortion", "mean"),
    ) if not node_frame.empty else pd.DataFrame())
    output.mkdir(parents=True, exist_ok=True)
    names = {
        "node_parquet": "EXP2A_DOWNSTREAM_COMPONENT_NODE_RECORDS_DEVELOPMENT_ONLY.parquet",
        "node_csv": "EXP2A_DOWNSTREAM_COMPONENT_NODE_RECORDS_DEVELOPMENT_ONLY.csv",
        "episode_csv": "EXP2A_DOWNSTREAM_COMPONENT_EPISODE_VALUES_DEVELOPMENT_ONLY.csv",
        "summary_csv": "EXP2A_DOWNSTREAM_COMPONENT_SUMMARY_DEVELOPMENT_ONLY.csv",
        "stage_csv": "EXP2A_DOWNSTREAM_STAGE_SUMMARY_DEVELOPMENT_ONLY.csv",
        "exclusions_csv": "EXP2A_DOWNSTREAM_EXCLUSIONS_DEVELOPMENT_ONLY.csv",
        "manifest": "EXP2A_DOWNSTREAM_CONSEQUENCE_DISTORTION_MANIFEST.json",
        "readme": "README.md",
    }
    node_frame.to_parquet(output / names["node_parquet"], index=False)
    node_frame.to_csv(output / names["node_csv"], index=False)
    episode_frame.to_csv(output / names["episode_csv"], index=False)
    summary_frame.to_csv(output / names["summary_csv"], index=False)
    stage_frame.to_csv(output / names["stage_csv"], index=False)
    pd.DataFrame(exclusions, columns=["episode_id", "decision_node_id", "component_id", "variant_id", "reason_code", "detail"]).to_csv(output / names["exclusions_csv"], index=False)
    materialization_manifest = {
        "schema_version": "EXP2A_DOWNSTREAM_CONSEQUENCE_DISTORTION_V1_20260826",
        "scope": "DEVELOPMENT_ONLY", "paper_result": False, "operational_recommendation": False,
        "interpretation": "REPRESENTATION_DIAGNOSTIC_NOT_ACTION_RANKING_OR_OPERATIONAL_RECOMMENDATION",
        "source_artifact": str(paths["m1_artifact"].relative_to(root)), "source_artifact_sha256": source_hash,
        "source_manifest": str(paths["m1_manifest"].relative_to(root)), "m2_registry_sha256": _sha(paths["m2_registry"]),
        "m2_design_sha256": _sha(paths["m2_design"]), "adapter_sha256": _sha(root / "exp/exp2/representation.py"),
        "reference_artifact_hashes": {name: _sha(paths[name]) for name in REFERENCE_FILES},
        "components": list(COMPONENTS), "variants": list(VARIANTS), "comparisons": [item[1] for item in COMPARISONS],
        "cvar_alpha": ALPHA, "bootstrap": {"reps": BOOTSTRAP_REPS, "seed": BOOTSTRAP_SEED, "unit": "episode"},
        "common_support_rule": "ALL_THREE_REPRESENTATIONS_ALL_SCENARIOS_FINITE_SUPPORTED_NO_RENORMALIZATION",
        "node_count": int(node_frame["decision_node_id"].nunique()) if not node_frame.empty else 0,
        "included_node_component_comparisons": int(len(node_frame)), "exclusion_counts": dict(Counter(item["reason_code"] for item in exclusions)),
        "common_support_node_counts_by_component": (
            {
                component: int(
                    node_frame.loc[node_frame["component"] == component, "decision_node_id"].nunique()
                )
                for component in COMPONENTS
            }
            if not node_frame.empty else {}
        ),
        "representation_hash_count": len(representation_hashes), "safety": SAFETY,
        "execution_workers": worker_count,
    }
    _write_json(output / names["manifest"], materialization_manifest)
    (output / names["readme"]).write_text(
        "# Exp2A downstream consequence distortion\n\n"
        "Development-only representation diagnostic. POINT and MARGINAL are compared with frozen JOINT M1 scenarios after M2 mapping. "
        "This output is not an action ranking, operational recommendation, or empirical effectiveness claim.\n",
        encoding="utf-8",
    )
    return {key: output / value for key, value in names.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--workers", type=int)
    args = parser.parse_args()
    paths = materialize(root=args.root, output_root=args.output_root, workers=args.workers)
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
