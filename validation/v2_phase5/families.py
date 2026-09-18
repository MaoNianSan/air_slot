"""Phase 5 Development families (state families and representation families).

Family A compares the three Development-only state families on the *frozen*
Development split:

- ``HISTORY_H16_PRIMARY`` (History + Joint, the frozen primary),
- ``CURRENT_H16_COMPARATOR`` (current-observation comparator),
- ``HISTORY_H8_SENSITIVITY`` (Phase-5 matched lower-capacity sensitivity).

Family B rebuilds the frozen H16 Joint source and derives the Point and Marginal
representations from it, then reports distributional and consequence-level
distortion against that source.

Neither family performs model selection or ranking: the reports carry
``directional_claims: NONE`` and never use ``L_att``/``L_rec``. All consequence
quantities are evaluated on M2 comparison support with typed abstentions, so
missing, unsupported and supported zero stay distinct.

Nothing here reads ``artifacts/experiment/final_test``.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import torch

from exp.exp1.metrics import (
    energy_score,
    marginal_variogram_score,
    variogram_score,
    weighted_crps,
)
from model.M1.pipeline import M1Pipeline
from model.M1.state_representation import (
    MARGINAL_IDENTITY_NOTE,
    build_joint_representation,
    build_marginal_representation,
    build_point_representation,
)
from model.M2.consequence_service import M2ConsequenceService
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    StateRepresentationSpec,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage
from model.common.errors import ContractError
from model.common.identity import content_id

from .common import (
    COMMON_SUPPORT_THRESHOLD,
    CURRENT_CHECKPOINT,
    CURRENT_MANIFEST,
    H16_CHECKPOINT,
    H16_MANIFEST,
    H8_CHECKPOINT,
    H8_MANIFEST,
    INERT_BINDING_FIELDS,
    JOINT_SOURCE_PATH,
    PHASE_DIR,
    Authorities,
    Phase5GuardError,
    build_node_binding,
    chain_id_for_episode,
    comparison_support_for,
    consequence_set,
    expected_cu_for_support,
    file_hash,
    read_json,
    representation_spec,
    state_set_from_m1_scenarios,
    state_set_from_source_rows,
    write_json,
)


COORDINATES: tuple[str, ...] = ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes")
OBSERVATION_TARGETS: Mapping[str, str] = {
    "t_ib_minutes": "T_IB_REMAINING_HAZARD",
    "d_ob_minutes": "D_OB",
    "d_tx_minutes": "D_TX",
}
SCENARIO_COUNT = 64
VARIogram_P = 0.5
REPRESENTATION_KEYS: tuple[tuple[str, str], ...] = (
    ("JOINT", "joint"),
    ("POINT", "point"),
    ("MARGINAL", "marginal"),
)
FAMILY_A_METRICS_NAME = "FAMILY_A_STATE_METRICS.npz"
FAMILY_A_SUMMARY_NAME = "FAMILY_A_STATE_FAMILIES.json"
FAMILY_B_METRICS_NAME = "FAMILY_B_REPRESENTATION_METRICS.npz"
FAMILY_B_ROWS_NAME = "FAMILY_B_VARIogram_ROWS.npz"
FAMILY_B_SUMMARY_NAME = "FAMILY_B_REPRESENTATION_FAMILIES.json"
REFERENCE_BINDING_AUDIT_NAME = "REFERENCE_BINDING_AUDIT.json"

HISTORY_MODE_HISTORY = "FULL_ADAPTIVE_CAUSAL_PREFIX"
HISTORY_MODE_CURRENT = "NO_HISTORY_CURRENT_OBSERVATION"


@dataclass(frozen=True)
class ModelSpec:
    """One Development state family and its frozen producer artifact."""

    key: str
    short_key: str
    role: str
    checkpoint: Path
    manifest: Path
    history_mode: str
    temporal: TemporalKind
    history_capacity: int | None

    def state_spec(self) -> StateRepresentationSpec:
        return representation_spec(
            self.temporal,
            UncertaintyKind.JOINT,
            history_capacity=self.history_capacity,
        )


@dataclass(frozen=True)
class ConsequenceLayer:
    """Node-keyed M2 consequence callback plus its reference audit."""

    service: M2ConsequenceService
    bindings: Mapping[str, Any]
    audit: Mapping[str, Any]
    artifact: Mapping[str, Any]


def _manifest_for(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise Phase5GuardError(f"PHASE5_FAMILY_MANIFEST_MISSING:{path}")
    return read_json(path)


def _model_specs() -> tuple[ModelSpec, ...]:
    """Resolve the three Development state families; the H8 artifact must exist."""

    specs = [
        ModelSpec(
            key="HISTORY_H16_PRIMARY",
            short_key="h16",
            role="PRIMARY",
            checkpoint=H16_CHECKPOINT,
            manifest=H16_MANIFEST,
            history_mode=HISTORY_MODE_HISTORY,
            temporal=TemporalKind.HISTORY,
            history_capacity=16,
        ),
        ModelSpec(
            key="CURRENT_H16_COMPARATOR",
            short_key="current",
            role="CURRENT_OBSERVATION_COMPARATOR",
            checkpoint=CURRENT_CHECKPOINT,
            manifest=CURRENT_MANIFEST,
            history_mode=HISTORY_MODE_CURRENT,
            temporal=TemporalKind.CURRENT,
            history_capacity=None,
        ),
    ]
    h8_manifest = _manifest_for(H8_MANIFEST)
    if not H8_CHECKPOINT.is_file():
        raise Phase5GuardError("PHASE5_H8_SENSITIVITY_ARTIFACT_MISSING")
    specs.append(
        ModelSpec(
            key="HISTORY_H8_SENSITIVITY",
            short_key="h8",
            role="LOWER_CAPACITY_SENSITIVITY",
            checkpoint=H8_CHECKPOINT,
            manifest=H8_MANIFEST,
            history_mode=str(h8_manifest["history_mode"]),
            temporal=TemporalKind.HISTORY,
            history_capacity=int(h8_manifest["hidden_size"]),
        )
    )
    for spec in specs:
        manifest = _manifest_for(spec.manifest)
        if manifest.get("history_mode") != spec.history_mode:
            raise Phase5GuardError(f"PHASE5_FAMILY_HISTORY_MODE_MISMATCH:{spec.key}")
        if file_hash(spec.checkpoint) != manifest.get("checkpoint_hash"):
            raise Phase5GuardError(f"PHASE5_FAMILY_CHECKPOINT_HASH_MISMATCH:{spec.key}")
        if int(manifest.get("final_test_access_count", -1)) != 0:
            raise Phase5GuardError(f"PHASE5_FAMILY_FINAL_TEST_ACCESS:{spec.key}")
    return tuple(specs)


def build_consequence_service(
    *,
    authorities: Authorities,
    bridge: Mapping[str, Any],
    output_dir: Path = PHASE_DIR,
) -> ConsequenceLayer:
    """Resolve every Development node binding once and persist the audit."""

    if authorities.registry.final_test_access_count != 0:
        raise Phase5GuardError("PHASE5_FAMILY_REGISTRY_FINAL_TEST_ACCESS")
    bindings: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    unsupported: dict[str, Any] = {}
    for example, episode, prefix in bridge["rows"]:
        state = prefix[-1]
        node = state.decision_node
        route = state.successor_state.get("route_context")
        route_value = None if route is None else route.value
        if not isinstance(route_value, dict) or not route_value.get(
            "destination_airport_id"
        ):
            raise ContractError(f"PHASE5_ROUTE_CONTEXT_MISSING:{node.decision_node_id}")
        resolved = build_node_binding(
            node_id=node.decision_node_id,
            episode_id=node.episode_id,
            chain_id=chain_id_for_episode(episode.episode),
            connection_airport_id=episode.episode.connection_airport_id,
            destination_airport_id=str(route_value["destination_airport_id"]),
            decision_time=node.decision_time,
            bundle=authorities.reference_bundle,
        )
        record = dict(resolved.audit)
        record["operational_stage"] = node.operational_stage.value
        records.append(record)
        if resolved.binding is None:
            unsupported[node.decision_node_id] = {
                "status": record.get("status"),
                "reason_codes": list(record.get("reason_codes", ())),
                "reference_support": dict(record.get("reference_support", {})),
            }
            continue
        bindings[node.decision_node_id] = resolved.binding
    service = M2ConsequenceService(authorities.registry, bindings)
    records.sort(key=lambda item: str(item["node_id"]))
    audit_payload = {
        "schema_version": "V2_PHASE5_REFERENCE_BINDING_AUDIT_V1",
        "status": "PASS",
        "artifact_scope": "DEVELOPMENT_ONLY",
        "registry_id": service.registry_id,
        "registry_hash": service.registry_hash,
        "inert_binding_fields": list(INERT_BINDING_FIELDS),
        "bound_node_count": len(bindings),
        "unsupported_node_count": len(unsupported),
        "unsupported_nodes": unsupported,
        "nodes": records,
        "final_test_access_count": 0,
    }
    audit_payload["artifact_hash"] = content_id(audit_payload)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / REFERENCE_BINDING_AUDIT_NAME
    write_json(artifact_path, audit_payload)
    audit = {
        "registry_id": service.registry_id,
        "registry_hash": service.registry_hash,
        "bound_node_count": len(bindings),
        "unsupported_node_count": len(unsupported),
        "unsupported_nodes": unsupported,
        "inert_binding_fields": list(INERT_BINDING_FIELDS),
        "audit_artifact": {
            "path": str(artifact_path),
            "hash": file_hash(artifact_path),
            "payload_hash": audit_payload["artifact_hash"],
        },
    }
    return ConsequenceLayer(
        service=service,
        bindings=bindings,
        audit=audit,
        artifact={"path": str(artifact_path), "hash": file_hash(artifact_path)},
    )


def _observations(example: Any) -> tuple[dict[str, float | None], dict[str, bool]]:
    values: dict[str, float | None] = {}
    active: dict[str, bool] = {}
    for coordinate, target in OBSERVATION_TARGETS.items():
        raw = example.targets.get(target)
        values[coordinate] = None if raw is None else float(raw)
        active[coordinate] = bool(example.active.get(target, False)) and raw is not None
    return values, active


def _weighted_quantile(
    values: Sequence[float], weights: Sequence[float], q: float
) -> float:
    pairs = sorted(zip((float(v) for v in values), (float(w) for w in weights)))
    total = sum(weight for _, weight in pairs)
    if total <= 0.0:
        raise ContractError("PHASE5_METRIC_WEIGHT_SUM_NOT_POSITIVE")
    threshold = q * total
    accumulated = 0.0
    for value, weight in pairs:
        accumulated += weight
        if accumulated >= threshold - 1e-12:
            return value
    return pairs[-1][0]


def _coordinate_columns(
    state_set: StateScenarioSet,
) -> tuple[dict[str, tuple[float, ...] | None], tuple[float, ...]]:
    weights = tuple(float(item.scenario_weight) for item in state_set.scenarios)
    columns: dict[str, tuple[float, ...] | None] = {}
    for coordinate in COORDINATES:
        resolved: list[float] = []
        for scenario in state_set.scenarios:
            value = getattr(scenario, coordinate)
            if value is None:
                resolved = []
                break
            resolved.append(float(value))
        columns[coordinate] = None if not resolved else tuple(resolved)
    return columns, weights


def _coordinate_metrics(
    values: Sequence[float], weights: Sequence[float], observation: float
) -> dict[str, float]:
    lower = _weighted_quantile(values, weights, 0.05)
    upper = _weighted_quantile(values, weights, 0.95)
    median = _weighted_quantile(values, weights, 0.5)
    return {
        "crps": float(weighted_crps(values, weights, observation)),
        "mae_median": abs(median - observation),
        "coverage_90": 1.0 if lower <= observation <= upper else 0.0,
        "interval_width_90": upper - lower,
    }


def _variogram_rows(
    state_set: StateScenarioSet,
) -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]:
    rows: list[tuple[float, ...]] = []
    weights: list[float] = []
    for scenario in state_set.scenarios:
        if (
            scenario.t_ib_minutes is None
            or scenario.d_ob_minutes is None
            or scenario.d_tx_minutes is None
        ):
            raise ContractError("PHASE5_VARIogram_ROWS_INCOMPLETE")
        rows.append(
            (
                float(scenario.t_ib_minutes),
                float(scenario.d_ob_minutes),
                float(scenario.d_tx_minutes),
            )
        )
        weights.append(float(scenario.scenario_weight))
    return tuple(rows), tuple(weights)


def _node_consequence(
    layer: ConsequenceLayer,
    state_set: StateScenarioSet,
) -> tuple[float, bool, dict[str, float] | None, tuple[str, ...]]:
    """Common-support expectation plus typed support diagnostics for one node."""

    if state_set.node_id not in layer.bindings:
        return (
            float("nan"),
            False,
            None,
            ("PHASE5_REFERENCE_UNSUPPORTED",),
        )
    consequences = consequence_set(layer.service, state_set)
    support = comparison_support_for(state_set, consequences)
    if not support.included:
        return support.supported_mass, False, None, tuple(support.reason_codes)
    return (
        support.supported_mass,
        True,
        expected_cu_for_support(consequences, support),
        tuple(support.reason_codes),
    )


def _zero_metric_arrays(count: int, key: str) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {
        f"supported_mass__{key}": np.full(count, np.nan, dtype=np.float32),
        f"included__{key}": np.zeros(count, dtype=bool),
    }
    for coordinate in COORDINATES:
        for metric in ("crps", "mae", "coverage", "width"):
            arrays[f"{metric}__{key}__{coordinate}"] = np.full(
                count, np.nan, dtype=np.float32
            )
    for component in CONSEQUENCE_COMPONENTS:
        arrays[f"expected_cu__{key}__{component}"] = np.full(
            count, np.nan, dtype=np.float32
        )
    return arrays


def _aggregate_metric(array: np.ndarray, label: str) -> dict[str, Any]:
    mask = ~np.isnan(array)
    if not mask.any():
        return {"mean": None, "sd": None, "n": 0, "label": label}
    values = array[mask]
    return {
        "mean": float(values.mean()),
        "sd": None if int(mask.sum()) < 2 else float(values.std(ddof=1)),
        "n": int(mask.sum()),
        "label": label,
    }


def _paired_gap(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    mask = ~np.isnan(left) & ~np.isnan(right)
    if not mask.any():
        return {"mean_absolute_gap": None, "max_absolute_gap": None, "paired_nodes": 0}
    gap = np.abs(left[mask] - right[mask])
    return {
        "mean_absolute_gap": float(gap.mean()),
        "max_absolute_gap": float(gap.max()),
        "paired_nodes": int(mask.sum()),
    }


def _reason_counts(reasons: Sequence[Sequence[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for codes in reasons:
        for code in codes:
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _array_hash(array: np.ndarray) -> str:
    return f"sha256:{sha256(np.ascontiguousarray(array).tobytes()).hexdigest()}"


def _write_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    return {
        "path": str(path),
        "hash": file_hash(path),
        "array_count": len(arrays),
        "arrays": sorted(arrays),
    }


def _state_metric_block(arrays: Mapping[str, np.ndarray], key: str) -> dict[str, Any]:
    return {
        coordinate: {
            "crps": _aggregate_metric(
                arrays[f"crps__{key}__{coordinate}"], coordinate
            ),
            "mae_median": _aggregate_metric(
                arrays[f"mae__{key}__{coordinate}"], coordinate
            ),
            "coverage_90": _aggregate_metric(
                arrays[f"coverage__{key}__{coordinate}"], coordinate
            ),
            "interval_width_90": _aggregate_metric(
                arrays[f"width__{key}__{coordinate}"], coordinate
            ),
        }
        for coordinate in COORDINATES
    }


def _expected_cu_block(arrays: Mapping[str, np.ndarray], key: str) -> dict[str, Any]:
    return {
        component: _aggregate_metric(
            arrays[f"expected_cu__{key}__{component}"], component
        )
        for component in CONSEQUENCE_COMPONENTS
    }


def materialize_family_a(
    *,
    authorities: Authorities,
    bridge: Mapping[str, Any],
    tails: Mapping[str, Any],
    layer: ConsequenceLayer,
    output_dir: Path = PHASE_DIR,
    node_limit: int | None = None,
) -> dict[str, Any]:
    """Materialize Development state-family metrics and consequence transfer."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = bridge["rows"] if node_limit is None else bridge["rows"][: int(node_limit)]
    cache = bridge["cache"]
    specs = _model_specs()
    current_rows = {
        row.decision_node_id: row
        for row in cache.partition("development", representation="CURRENT")
    }
    from exp.exp2.development_inputs import _observed

    count = len(rows)
    node_ids = np.asarray(
        [item[2][-1].decision_node.decision_node_id for item in rows], dtype=str
    )
    arrays: dict[str, np.ndarray] = {"node_id": node_ids}
    observation_table: dict[str, np.ndarray] = {}
    active_table: dict[str, np.ndarray] = {}
    for coordinate in COORDINATES:
        observation_table[coordinate] = np.full(count, np.nan, dtype=np.float32)
        active_table[coordinate] = np.zeros(count, dtype=bool)
    for index, (example, _, _) in enumerate(rows):
        values, active = _observations(example)
        for coordinate in COORDINATES:
            active_table[coordinate][index] = active[coordinate]
            if values[coordinate] is not None:
                observation_table[coordinate][index] = float(values[coordinate])
    for coordinate in COORDINATES:
        arrays[f"observed__{coordinate}"] = observation_table[coordinate]
        arrays[f"observed_active__{coordinate}"] = active_table[coordinate]

    metrics_by_model: dict[str, Any] = {}
    for spec in specs:
        pipeline = M1Pipeline.load(spec.checkpoint)
        pipeline.tail_continuations = tails
        manifest = _manifest_for(spec.manifest)
        seed = int(manifest["training_seed"])
        state_spec = spec.state_spec()
        model_arrays = _zero_metric_arrays(count, spec.short_key)
        reasons: list[tuple[str, ...]] = []
        coordinate_abstain = {coordinate: 0 for coordinate in COORDINATES}
        for index, (example, episode, prefix) in enumerate(rows):
            state = prefix[-1]
            node = state.decision_node
            node_id = node.decision_node_id
            if spec.temporal is TemporalKind.CURRENT:
                source = current_rows.get(example.decision_node_id)
                if source is None:
                    raise Phase5GuardError(
                        "PHASE5_FAMILY_CURRENT_ROW_MISSING:"
                        f"{example.decision_node_id}"
                    )
                values = source.values
            else:
                values = example.values
            scenarios = pipeline.sample_from_pre(
                state,
                values.unsqueeze(0),
                torch.tensor([len(values)]),
                observed=_observed(state, bridge["taxi_reference"]),
                count=SCENARIO_COUNT,
                seed=seed,
                taxi_reference=bridge["taxi_reference"],
                tail_continuations=tails,
            )
            if len(scenarios) != SCENARIO_COUNT:
                raise ContractError(
                    f"PHASE5_FAMILY_SCENARIO_COUNT_MISMATCH:{spec.key}:{node_id}"
                )
            state_set = state_set_from_m1_scenarios(
                scenarios,
                episode_id=node.episode_id,
                chain_id=chain_id_for_episode(episode.episode),
                node_id=node_id,
                stage=node.operational_stage,
                representation=state_spec,
            )
            columns, weights = _coordinate_columns(state_set)
            observations, active = _observations(example)
            for coordinate in COORDINATES:
                column = columns[coordinate]
                if column is None:
                    coordinate_abstain[coordinate] += 1
                    continue
                if not active[coordinate]:
                    continue
                metrics = _coordinate_metrics(
                    column, weights, float(observations[coordinate])
                )
                model_arrays[f"crps__{spec.short_key}__{coordinate}"][index] = metrics[
                    "crps"
                ]
                model_arrays[f"mae__{spec.short_key}__{coordinate}"][index] = metrics[
                    "mae_median"
                ]
                model_arrays[f"coverage__{spec.short_key}__{coordinate}"][index] = (
                    metrics["coverage_90"]
                )
                model_arrays[f"width__{spec.short_key}__{coordinate}"][index] = metrics[
                    "interval_width_90"
                ]
            mass, included, expected, node_reasons = _node_consequence(layer, state_set)
            model_arrays[f"supported_mass__{spec.short_key}"][index] = mass
            model_arrays[f"included__{spec.short_key}"][index] = bool(included)
            reasons.append(tuple(node_reasons))
            if expected is not None:
                for component, value in expected.items():
                    model_arrays[f"expected_cu__{spec.short_key}__{component}"][
                        index
                    ] = float(value)
        arrays.update(model_arrays)
        masses = model_arrays[f"supported_mass__{spec.short_key}"]
        metrics_by_model[spec.key] = {
            "short_key": spec.short_key,
            "role": spec.role,
            "checkpoint_hash": manifest.get("checkpoint_hash"),
            "manifest_hash": file_hash(spec.manifest),
            "history_mode": spec.history_mode,
            "representation_id": state_spec.representation_id,
            "scenario_count": SCENARIO_COUNT,
            "scenario_generator_seed": seed,
            "state_metrics": _state_metric_block(model_arrays, spec.short_key),
            "coordinate_abstain_nodes": dict(coordinate_abstain),
            "consequence_transmission": {
                "included_nodes": int(model_arrays[f"included__{spec.short_key}"].sum()),
                "typed_excluded_nodes": int(
                    count - int(model_arrays[f"included__{spec.short_key}"].sum())
                ),
                "below_nominal_mass_nodes": int(
                    (masses < COMMON_SUPPORT_THRESHOLD - 1e-9).sum()
                ),
                "supported_mass_mean": float(np.nanmean(masses)),
                "supported_mass_min": float(np.nanmin(masses)),
                "exclusion_reason_counts": _reason_counts(reasons),
                "expected_cu": _expected_cu_block(model_arrays, spec.short_key),
            },
        }
    paired: dict[str, Any] = {}
    for spec in specs:
        if spec.short_key == "h16":
            continue
        paired[spec.key] = {
            "versus": "HISTORY_H16_PRIMARY",
            "interpretation": "METRIC_DISTANCE_ONLY_NO_SUPERIORITY_CLAIM",
            "common_support": "PAIRED_NODES_WITH_BOTH_EXPECTATIONS_DEFINED",
            **{
                component: _paired_gap(
                    arrays[f"expected_cu__h16__{component}"],
                    arrays[f"expected_cu__{spec.short_key}__{component}"],
                )
                for component in CONSEQUENCE_COMPONENTS
            },
        }
    artifact = _write_npz(output_dir / FAMILY_A_METRICS_NAME, arrays)
    payload = {
        "schema_version": "V2_PHASE5_FAMILY_A_V1",
        "status": "PASS",
        "artifact_scope": "DEVELOPMENT_ONLY",
        "family": "A_STATE_FAMILIES",
        "purpose": (
            "Development state reconstruction, distributional calibration and "
            "consequence transmission for the frozen primary, the current "
            "comparator and the matched lower-capacity sensitivity"
        ),
        "selection_use": "NOT_USED_FOR_HISTORY_PRIMARY_SELECTION",
        "directional_claims": "NONE",
        "ranking_performed": False,
        "loss_metrics_used": {"L_att": False, "L_rec": False, "L_total": False},
        "node_count": count,
        "episode_count": len({item[0].episode_id for item in rows}),
        "observation_coverage": {
            coordinate: {
                "active_nodes": int(active_table[coordinate].sum()),
                "resolved_nodes": int(np.isfinite(observation_table[coordinate]).sum()),
            }
            for coordinate in COORDINATES
        },
        "consequence_layer": layer.audit,
        "models": metrics_by_model,
        "paired_distances_versus_primary": paired,
        "node_metrics_artifact": artifact,
        "final_test_access_count": 0,
        "no_final_test_family_branch": True,
    }
    payload["artifact_hash"] = content_id(payload)
    write_json(output_dir / FAMILY_A_SUMMARY_NAME, payload)
    return payload


def _representation_sets(
    joint_set: StateScenarioSet,
) -> dict[str, StateScenarioSet]:
    return {
        "JOINT": build_joint_representation(joint_set),
        "POINT": build_point_representation(joint_set),
        "MARGINAL": build_marginal_representation(joint_set),
    }


def _representation_variogram(
    name: str,
    rows: Sequence[tuple[float, ...]],
    weights: Sequence[float],
    observation: Sequence[float],
) -> float:
    """Representation-specific variogram; Marginal uses exact product mass."""

    if name == "MARGINAL":
        marginal_values = [
            [row[position] for row in rows] for position in range(len(COORDINATES))
        ]
        marginal_weights = [[float(weight) for weight in weights] for _ in COORDINATES]
        return float(
            marginal_variogram_score(
                marginal_values, marginal_weights, observation, p=VARIogram_P
            )
        )
    return float(variogram_score(rows, weights, observation, p=VARIogram_P))


def materialize_family_b(
    *,
    authorities: Authorities,
    bridge: Mapping[str, Any],
    layer: ConsequenceLayer,
    output_dir: Path = PHASE_DIR,
    node_limit: int | None = None,
) -> dict[str, Any]:
    """Materialize representation-family metrics from the frozen Joint source."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(JOINT_SOURCE_PATH)
    frame = frame.sort_values(["decision_node_id", "scenario_id"], kind="stable")
    frame = frame.reset_index(drop=True)
    identity_gap = float((frame["D_OB"] + frame["D_TX"] - frame["D_TO"]).abs().max())
    if identity_gap > 1e-6:
        raise ContractError("PHASE5_FAMILY_B_SOURCE_D_TO_IDENTITY_VIOLATION")
    observation_by_node: dict[str, tuple[dict[str, float | None], dict[str, bool]]] = {}
    stage_by_node: dict[str, OperationalStage] = {}
    episode_by_node: dict[str, str] = {}
    chain_by_node: dict[str, str] = {}
    for example, episode, prefix in bridge["rows"]:
        node = prefix[-1].decision_node
        node_id = node.decision_node_id
        observation_by_node[node_id] = _observations(example)
        stage_by_node[node_id] = node.operational_stage
        episode_by_node[node_id] = node.episode_id
        chain_by_node[node_id] = chain_id_for_episode(episode.episode)
    source_nodes = {str(value) for value in frame["decision_node_id"].unique()}
    if source_nodes != set(observation_by_node):
        missing = sorted(source_nodes - set(observation_by_node))[:5]
        extra = sorted(set(observation_by_node) - source_nodes)[:5]
        raise Phase5GuardError(f"PHASE5_FAMILY_B_NODE_MISMATCH:{missing}:{extra}")
    groups = list(frame.groupby("decision_node_id", sort=True))
    if node_limit is not None:
        groups = groups[: int(node_limit)]
    count = len(groups)
    arrays: dict[str, np.ndarray] = {
        "node_id": np.asarray([str(node_id) for node_id, _ in groups], dtype=str)
    }
    observation_table: dict[str, np.ndarray] = {}
    active_table: dict[str, np.ndarray] = {}
    for coordinate in COORDINATES:
        observation_table[coordinate] = np.full(count, np.nan, dtype=np.float32)
        active_table[coordinate] = np.zeros(count, dtype=bool)
    metrics_arrays: dict[str, dict[str, np.ndarray]] = {}
    for _, short_key in REPRESENTATION_KEYS:
        metrics_arrays[short_key] = _zero_metric_arrays(count, short_key)
        metrics_arrays[short_key][f"energy__{short_key}"] = np.full(
            count, np.nan, dtype=np.float32
        )
        metrics_arrays[short_key][f"variogram__{short_key}"] = np.full(
            count, np.nan, dtype=np.float32
        )
    collected_rows: dict[str, list[np.ndarray]] = {
        name: [] for name, _ in REPRESENTATION_KEYS
    }
    collected_weights: dict[str, list[np.ndarray]] = {
        name: [] for name, _ in REPRESENTATION_KEYS
    }
    representation_ids: dict[str, str] = {}
    coordinate_abstain = {
        short_key: {coordinate: 0 for coordinate in COORDINATES}
        for _, short_key in REPRESENTATION_KEYS
    }
    reasons: list[tuple[str, ...]] = []
    for index, (node_id, group) in enumerate(groups):
        node_id = str(node_id)
        joint_set = state_set_from_source_rows(
            group.to_dict("records"),
            episode_id=episode_by_node[node_id],
            chain_id=chain_by_node[node_id],
            node_id=node_id,
            stage=stage_by_node[node_id],
            representation=representation_spec(
                TemporalKind.HISTORY, UncertaintyKind.JOINT, history_capacity=16
            ),
        )
        representations = _representation_sets(joint_set)
        observations, active = observation_by_node[node_id]
        for coordinate in COORDINATES:
            active_table[coordinate][index] = active[coordinate]
            if observations[coordinate] is not None:
                observation_table[coordinate][index] = float(observations[coordinate])
        observation_vector = tuple(
            float(observations[coordinate])
            if active[coordinate]
            else float("nan")
            for coordinate in COORDINATES
        )
        vector_usable = all(active[coordinate] for coordinate in COORDINATES)
        for name, state_set in representations.items():
            short_key = name.lower()
            representation_ids.setdefault(
                name, state_set.representation.representation_id
            )
            columns, weights = _coordinate_columns(state_set)
            for coordinate in COORDINATES:
                column = columns[coordinate]
                if column is None:
                    coordinate_abstain[short_key][coordinate] += 1
                    continue
                if not active[coordinate]:
                    continue
                metrics = _coordinate_metrics(
                    column, weights, float(observations[coordinate])
                )
                metrics_arrays[short_key][f"crps__{short_key}__{coordinate}"][index] = (
                    metrics["crps"]
                )
                metrics_arrays[short_key][f"mae__{short_key}__{coordinate}"][index] = (
                    metrics["mae_median"]
                )
                metrics_arrays[short_key][f"coverage__{short_key}__{coordinate}"][
                    index
                ] = metrics["coverage_90"]
                metrics_arrays[short_key][f"width__{short_key}__{coordinate}"][index] = (
                    metrics["interval_width_90"]
                )
            rows, row_weights = _variogram_rows(state_set)
            collected_rows[name].append(np.asarray(rows, dtype=np.float32))
            collected_weights[name].append(np.asarray(row_weights, dtype=np.float32))
            if vector_usable:
                metrics_arrays[short_key][f"variogram__{short_key}"][index] = (
                    _representation_variogram(
                        name, rows, row_weights, observation_vector
                    )
                )
                metrics_arrays[short_key][f"energy__{short_key}"][index] = float(
                    energy_score(rows, row_weights, observation_vector)
                )
            mass, included, expected, node_reasons = _node_consequence(layer, state_set)
            metrics_arrays[short_key][f"supported_mass__{short_key}"][index] = mass
            metrics_arrays[short_key][f"included__{short_key}"][index] = bool(included)
            reasons.append(tuple(node_reasons))
            if expected is not None:
                for component, value in expected.items():
                    metrics_arrays[short_key][
                        f"expected_cu__{short_key}__{component}"
                    ][index] = float(value)
    rows_by_key: dict[str, np.ndarray] = {}
    weights_by_key: dict[str, np.ndarray] = {}
    for name, short_key in REPRESENTATION_KEYS:
        widths = {item.shape[1] for item in collected_rows[name]}
        if len(widths) != 1:
            raise ContractError(f"PHASE5_FAMILY_B_RAGGED_ROWS:{name}")
        rows_by_key[short_key] = np.stack(collected_rows[name]).astype(np.float32)
        weights_by_key[short_key] = np.stack(collected_weights[name]).astype(np.float32)
        arrays[f"{short_key}_variogram_rows"] = rows_by_key[short_key]
        arrays[f"{short_key}_variogram_weights"] = weights_by_key[short_key]
        arrays.update(metrics_arrays[short_key])
    for coordinate in COORDINATES:
        arrays[f"observed__{coordinate}"] = observation_table[coordinate]
        arrays[f"observed_active__{coordinate}"] = active_table[coordinate]
    for _, left in REPRESENTATION_KEYS:
        for _, right in REPRESENTATION_KEYS:
            if left >= right:
                continue
            if np.shares_memory(
                arrays[f"{left}_variogram_rows"], arrays[f"{right}_variogram_rows"]
            ):
                raise ContractError("PHASE5_FAMILY_B_VARIogram_ROWS_SHARED")
    row_hashes = {
        short_key: _array_hash(rows_by_key[short_key])
        for _, short_key in REPRESENTATION_KEYS
    }
    metrics_artifact = _write_npz(output_dir / FAMILY_B_METRICS_NAME, arrays)
    rows_artifact = _write_npz(
        output_dir / FAMILY_B_ROWS_NAME,
        {
            f"{short_key}_variogram_rows": rows_by_key[short_key]
            for _, short_key in REPRESENTATION_KEYS
        }
        | {
            f"{short_key}_variogram_weights": weights_by_key[short_key]
            for _, short_key in REPRESENTATION_KEYS
        },
    )
    representation_block: dict[str, Any] = {}
    for name, short_key in REPRESENTATION_KEYS:
        masses = metrics_arrays[short_key][f"supported_mass__{short_key}"]
        representation_block[name] = {
            "short_key": short_key,
            "representation_id": representation_ids.get(name),
            "source": "EXP2_COMMON_SUPPORT.parquet:frozen_H16_joint_source",
            "scenario_count_max": int(rows_by_key[short_key].shape[1]),
            "marginal_identity_note": (
                MARGINAL_IDENTITY_NOTE if name == "MARGINAL" else None
            ),
            "state_metrics": _state_metric_block(metrics_arrays[short_key], short_key),
            "energy_score": _aggregate_metric(
                metrics_arrays[short_key][f"energy__{short_key}"], "joint_vector"
            ),
            "variogram_score": {
                "p": VARIogram_P,
                "expectation_rule": (
                    "PRODUCT_OF_MARGINALS_EXACT"
                    if name == "MARGINAL"
                    else "ALIGNED_REPRESENTATION_ROWS"
                ),
                "rows_hash": row_hashes[short_key],
                **_aggregate_metric(
                    metrics_arrays[short_key][f"variogram__{short_key}"], "joint_vector"
                ),
            },
            "coordinate_abstain_nodes": dict(coordinate_abstain[short_key]),
            "consequence_transmission": {
                "included_nodes": int(
                    metrics_arrays[short_key][f"included__{short_key}"].sum()
                ),
                "below_nominal_mass_nodes": int(
                    (masses < COMMON_SUPPORT_THRESHOLD - 1e-9).sum()
                ),
                "supported_mass_mean": float(np.nanmean(masses)),
                "supported_mass_min": float(np.nanmin(masses)),
                "expected_cu": _expected_cu_block(metrics_arrays[short_key], short_key),
            },
        }
    distortion = {
        "reference": "JOINT",
        "interpretation": "DISTORTION_VERSUS_JOINT_SOURCE_NO_SUPERIORITY_CLAIM",
        **{
            name: {
                component: _paired_gap(
                    metrics_arrays["joint"][f"expected_cu__joint__{component}"],
                    metrics_arrays[short_key][
                        f"expected_cu__{short_key}__{component}"
                    ],
                )
                for component in CONSEQUENCE_COMPONENTS
            }
            for name, short_key in (("POINT", "point"), ("MARGINAL", "marginal"))
        },
    }
    payload = {
        "schema_version": "V2_PHASE5_FAMILY_B_V1",
        "status": "PASS",
        "artifact_scope": "DEVELOPMENT_ONLY",
        "family": "B_REPRESENTATION_FAMILIES",
        "purpose": (
            "Development representation metrics and consequence distortion for "
            "Point, Marginal and Joint derived from one frozen H16 Joint source"
        ),
        "selection_use": "NOT_USED_FOR_HISTORY_PRIMARY_SELECTION",
        "directional_claims": "NONE",
        "ranking_performed": False,
        "loss_metrics_used": {"L_att": False, "L_rec": False, "L_total": False},
        "source": {
            "path": str(JOINT_SOURCE_PATH),
            "hash": file_hash(JOINT_SOURCE_PATH),
            "node_count": len(source_nodes),
            "scenario_count": SCENARIO_COUNT,
            "joint_source_readonly": True,
            "d_to_identity_max_abs_gap": identity_gap,
            "weights_sum_one_all_nodes": True,
        },
        "node_count": count,
        "observation_coverage": {
            coordinate: {
                "active_nodes": int(active_table[coordinate].sum()),
                "resolved_nodes": int(np.isfinite(observation_table[coordinate]).sum()),
            }
            for coordinate in COORDINATES
        },
        "consequence_layer": layer.audit,
        "representations": representation_block,
        "distortion_versus_joint": distortion,
        "node_metrics_artifact": metrics_artifact,
        "variogram_rows_artifact": {
            **rows_artifact,
            "rows_hashes": row_hashes,
            "cross_representation_sharing": False,
            "note": "VARIogram_ROWS_ARE_REPRESENTATION_SPECIFIC",
        },
        "final_test_access_count": 0,
        "no_final_test_family_branch": True,
    }
    payload["artifact_hash"] = content_id(payload)
    write_json(output_dir / FAMILY_B_SUMMARY_NAME, payload)
    return payload


__all__ = [
    "COORDINATES",
    "ConsequenceLayer",
    "FAMILY_A_METRICS_NAME",
    "FAMILY_A_SUMMARY_NAME",
    "FAMILY_B_METRICS_NAME",
    "FAMILY_B_ROWS_NAME",
    "FAMILY_B_SUMMARY_NAME",
    "ModelSpec",
    "REFERENCE_BINDING_AUDIT_NAME",
    "REPRESENTATION_KEYS",
    "VARIogram_P",
    "build_consequence_service",
    "materialize_family_a",
    "materialize_family_b",
]
