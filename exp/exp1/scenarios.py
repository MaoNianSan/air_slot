"""Exp1B analysis over the frozen M1 -> M2 Development scenario artifact."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from exp.exp2 import development_inputs as exp2_inputs
from model.M2.contracts import M2ScenarioInput
from model.M2.consequences.engine import native_quantities
from model.common.enums import SupportState

from .analysis import consequence_wasserstein, state_variogram_contrasts
from .representations import build_marginal, build_point, from_mapping_rows


SCENARIO_PATH = (
    exp2_inputs.OUTPUT / "data" / "EXP2_COMMON_SUPPORT.parquet"
)
COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)
SCENARIO_FIELDS = {
    "R_IB",
    "R_IB_support",
    "D_OB",
    "D_OB_support",
    "D_TX",
    "D_TX_support",
    "common_supported",
    "scenario_weight",
    "scenario_id",
    "episode_id",
    "decision_node_id",
    "pre_decision_node_id",
    *(f"{component}_native" for component in COMPONENTS),
}


def _target_observation(prepared, state, taxi_reference) -> dict[str, float | None]:
    lookup = taxi_reference.lookup(prepared.episode.connection_airport_id)
    taxi_minutes = (
        float(lookup.value)
        if getattr(lookup, "value", None) is not None
        and getattr(getattr(lookup, "support_state", None), "value", None)
        == "SUPPORTED"
        else None
    )
    return {
        "R_IB": (
            None
            if prepared.predecessor_outcome.cancelled
            or prepared.predecessor_outcome.diverted
            or prepared.predecessor_outcome.actual_arrival_utc is None
            else max(
                0.0,
                (prepared.predecessor_outcome.actual_arrival_utc - state.decision_node.decision_time).total_seconds()
                / 60.0,
            )
        ),
        "D_OB": (
            None
            if prepared.successor_outcome.cancelled
            or prepared.successor_outcome.diverted
            or prepared.successor_outcome.actual_departure_utc is None
            or prepared.successor_schedule.scheduled_departure_utc is None
            else max(
                0.0,
                (prepared.successor_outcome.actual_departure_utc - prepared.successor_schedule.scheduled_departure_utc).total_seconds()
                / 60.0,
            )
        ),
        "D_TX": (
            None
            if prepared.successor_outcome.cancelled
            or prepared.successor_outcome.diverted
            or prepared.successor_outcome.taxi_out_minutes is None
            or taxi_minutes is None
            else max(
                0.0,
                float(prepared.successor_outcome.taxi_out_minutes) - taxi_minutes,
            )
        ),
    }


def load_scenario_artifact(
    exact_rows: list[tuple[object, object, object]],
    *,
    allow_materialize: bool = False,
) -> pd.DataFrame:
    """Load and identity-check the node/scenario artifact used by Exp1B.

    The artifact is produced by the existing Exp2 M1->M2 materializer.  A
    materialization request is explicit because it can take substantial time;
    no rows are synthesized here.
    """
    if not SCENARIO_PATH.is_file() or not SCENARIO_FIELDS <= set(
        pd.read_parquet(SCENARIO_PATH, engine="pyarrow", columns=None).columns
    ):
        if not allow_materialize:
            raise RuntimeError("EXP1B_SCENARIO_ARTIFACT_MISSING_REQUIRED_FIELDS")
        exp2_inputs.materialize_h16_development_inputs(output=exp2_inputs.OUTPUT)
    frame = pd.read_parquet(SCENARIO_PATH)
    missing = sorted(SCENARIO_FIELDS - set(frame.columns))
    if missing:
        raise RuntimeError(f"EXP1B_SCENARIO_COLUMNS_MISSING:{missing}")

    canonical_map = {}
    for example, prepared, prefix in exact_rows:
        state = prefix[-1]
        key = (str(example.episode_id), str(state.decision_node.decision_node_id))
        canonical_map[key] = str(example.decision_node_id)
    if len(canonical_map) != len(exact_rows):
        raise RuntimeError("EXP1B_EXACT_PRE_NODE_MAP_NOT_UNIQUE")

    frame["episode_id"] = frame["episode_id"].astype(str)
    frame["decision_node_id"] = frame["decision_node_id"].astype(str)
    frame["pre_decision_node_id"] = frame["pre_decision_node_id"].astype(str)
    frame["canonical_decision_node_id"] = [
        canonical_map.get((episode, pre_node))
        for episode, pre_node in zip(frame.episode_id, frame.pre_decision_node_id)
    ]
    # Older materializers may not have exposed the PRE namespace.  In that
    # case the published node identity can still be accepted if it is exact.
    missing_map = frame.canonical_decision_node_id.isna()
    frame.loc[missing_map, "canonical_decision_node_id"] = frame.loc[
        missing_map, "decision_node_id"
    ]
    expected = {(str(row[0].episode_id), str(row[0].decision_node_id)) for row in exact_rows}
    observed = set(
        zip(frame.episode_id, frame.canonical_decision_node_id.astype(str))
    )
    if observed != expected:
        raise RuntimeError("EXP1B_SCENARIO_NODE_SET_MISMATCH")
    counts = frame.groupby(["episode_id", "canonical_decision_node_id"]).size()
    if len(counts) != len(exact_rows) or not counts.eq(64).all():
        raise RuntimeError("EXP1B_SCENARIO_COUNT_PER_NODE_INVALID")
    if frame.duplicated(["episode_id", "canonical_decision_node_id", "scenario_id"]).any():
        raise RuntimeError("EXP1B_SCENARIO_IDENTITY_DUPLICATE")
    return frame


def _conditional_rows(node: pd.DataFrame) -> pd.DataFrame | None:
    selected = node[node.common_supported.astype(bool)].copy()
    mass = float(selected.scenario_weight.sum())
    if mass < 0.90 - 1e-9:
        return None
    required = ["R_IB", "D_OB", "D_TX"]
    values = selected[required].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("EXP1B_PRIMARY_STATE_SUPPORT_NOT_FINITE")
    selected["conditional_weight"] = selected.scenario_weight.astype(float) / mass
    return selected


def node_representation(
    node: pd.DataFrame,
    observation: dict[str, float | None],
    *,
    supports: tuple[float, float, float],
) -> dict[str, object]:
    selected = _conditional_rows(node)
    if selected is None:
        return {
            "status": "EXCLUDE_COMMON_SUPPORT_BELOW_090",
            "support_mass": float(node.loc[node.common_supported.astype(bool), "scenario_weight"].sum()),
        }
    rows = [
        {
            "scenario_id": int(row.scenario_id),
            "r_ib": float(row.R_IB),
            "d_ob": float(row.D_OB),
            "d_tx": float(row.D_TX),
            "weight": float(row.conditional_weight),
        }
        for row in selected.itertuples()
    ]
    joint = from_mapping_rows(rows)
    marginal = build_marginal(joint)
    point = build_point(joint, supports=supports)
    observed = tuple(observation[name] for name in ("R_IB", "D_OB", "D_TX"))
    if any(value is None or not isfinite(float(value)) for value in observed):
        return {
            "status": "ABSTAIN_REALIZED_TARGET_UNAVAILABLE",
            "n_scenarios": len(selected),
            "support_mass": float(selected.scenario_weight.sum()),
        }
    point_joint, marginal_joint, joint_vs = state_variogram_contrasts(
        joint, point, marginal, tuple(float(value) for value in observed)
    )
    return {
        "status": "PASS",
        "n_scenarios": len(selected),
        "support_mass": float(selected.scenario_weight.sum()),
        "Point_minus_Joint_VS": point_joint,
        "Marginal_minus_Joint_VS": marginal_joint,
        "Joint_VS": joint_vs,
        "point_scenario_id": point.scenario.scenario_id,
    }


def _m2_context(prepared, state, bundle):
    keys = exp2_inputs.AirportReferenceKeys(
        connection_airport_id=prepared.episode.connection_airport_id,
        successor_destination_airport_id=exp2_inputs._destination(state),
        carrier_id=None,
        month=state.decision_node.decision_time.month,
        quarter=(state.decision_node.decision_time.month - 1) // 3 + 1,
    )
    references = exp2_inputs.build_node_exposure_references(bundle, keys)
    return exp2_inputs.build_m2_v4_context(
        bundle, keys, node_specific_exposure=references.airport
    )


def _typed_input(row, *, episode_id, decision_node_id, scenario_id, weight):
    supported = SupportState.SUPPORTED
    return M2ScenarioInput(
        episode_id=str(episode_id),
        decision_node_id=str(decision_node_id),
        scenario_id=int(scenario_id),
        scenario_weight=float(weight),
        t_ib_a00_utc=None,
        r_ib_minutes=float(row.R_IB),
        d_ob_minutes=float(row.D_OB),
        d_tx_minutes=float(row.D_TX),
        d_to_minutes=float(row.D_OB + row.D_TX),
        r_ib_support=supported,
        d_ob_support=supported,
        d_tx_support=supported,
        d_to_support=supported,
        pre_lineage=("EXP1_FORMAL_PRESTATE_V1",),
        reference_lineage=("EXP1_M2_NATIVE_EVALUATION",),
        m1_scenario_seed_key=f"exp1:{episode_id}:{decision_node_id}:{scenario_id}",
    )


def _native_values(typed, context):
    return {
        row.component_id: float(row.native_quantity)
        for row in native_quantities(typed, context)
        if row.native_quantity is not None and np.isfinite(float(row.native_quantity))
    }


def downstream_native_summary(node: pd.DataFrame, context, supports) -> dict[str, object]:
    """Compare native M2 distributions under Point, Joint and Marginal.

    The four D_TO-dependent components are remapped through the frozen M2
    formula on the exact product of the selected D_OB and D_TX marginals.
    Single-axis components use their exact induced native marginal.  This is
    an analysis transformation only; no synthetic M1 joint scenario is saved
    as if it were model output.
    """
    selected = _conditional_rows(node)
    if selected is None:
        return {
            "status": "EXCLUDE_COMMON_SUPPORT_BELOW_090",
            "support_mass": float(node.loc[node.common_supported.astype(bool), "scenario_weight"].sum()),
        }
    weights = selected.conditional_weight.to_numpy(float)
    episode_id = str(node.episode_id.iloc[0])
    decision_node_id = str(node.canonical_decision_node_id.iloc[0])
    joint_input = from_mapping_rows([
        {"scenario_id": int(r.scenario_id), "r_ib": float(r.R_IB),
         "d_ob": float(r.D_OB), "d_tx": float(r.D_TX), "weight": float(w)}
        for r, w in zip(selected.itertuples(), weights)
    ])
    point = build_point(joint_input, supports=supports)
    point_row = selected[selected.scenario_id.eq(point.scenario.scenario_id)].iloc[0]
    point_input = _typed_input(
        point_row, episode_id=episode_id, decision_node_id=decision_node_id,
        scenario_id=int(point_row.scenario_id), weight=1.0,
    )
    point_values = _native_values(point_input, context)
    joint_values = {
        component: selected[f"{component}_native"].to_numpy(float)
        for component in COMPONENTS
    }
    direct_components = {"F_continuity", "F_execution", "R_operating"}
    product_components = set(COMPONENTS) - direct_components
    d_ob_atoms = [
        (float(value), float(weight))
        for value, weight in selected.groupby("D_OB", sort=True).conditional_weight.sum().items()
    ]
    d_tx_atoms = [
        (float(value), float(weight))
        for value, weight in selected.groupby("D_TX", sort=True).conditional_weight.sum().items()
    ]
    base_row = next(selected.itertuples(index=False))
    marginal_values = {}
    marginal_weights = {}
    for component in direct_components:
        marginal_values[component] = joint_values[component]
        marginal_weights[component] = weights
    product_values = {component: [] for component in product_components}
    product_weights = {component: [] for component in product_components}
    synthetic_id = 1000000
    for d_ob, weight_ob in d_ob_atoms:
        for d_tx, weight_tx in d_tx_atoms:
            synthetic = base_row._asdict()
            synthetic["D_OB"] = d_ob
            synthetic["D_TX"] = d_tx
            synthetic = SimpleNamespace(**synthetic)
            typed = _typed_input(
                synthetic, episode_id=episode_id, decision_node_id=decision_node_id,
                scenario_id=synthetic_id, weight=weight_ob * weight_tx,
            )
            mapped = _native_values(typed, context)
            for component in product_components:
                if component in mapped:
                    product_values[component].append(mapped[component])
                    product_weights[component].append(weight_ob * weight_tx)
            synthetic_id += 1
    for component in product_components:
        marginal_values[component] = np.asarray(product_values[component], dtype=float)
        marginal_weights[component] = np.asarray(product_weights[component], dtype=float)
    result = {"status": "PASS", "support_mass": float(selected.scenario_weight.sum())}
    for component in COMPONENTS:
        values = joint_values[component]
        if not np.isfinite(values).all() or component not in point_values:
            result[f"{component}_status"] = "ABSTAIN_UNSUPPORTED"
            continue
        joint_w1 = consequence_wasserstein(values, weights, values, weights, 1.0)
        point_w1 = consequence_wasserstein(
            [point_values[component]], [1.0], values, weights, 1.0
        )
        marginal_w1 = consequence_wasserstein(
            marginal_values[component], marginal_weights[component], values, weights, 1.0
        )
        result[f"{component}_point_minus_joint_native_W1"] = point_w1
        result[f"{component}_marginal_minus_joint_native_W1"] = marginal_w1
        result[f"{component}_joint_self_native_W1"] = joint_w1
    return result


def analyze_nodes(
    scenarios: pd.DataFrame,
    exact_rows: list[tuple[object, object, object]],
    taxi_reference,
    *,
    supports: tuple[float, float, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    observations = {}
    for example, prepared, prefix in exact_rows:
        state = prefix[-1]
        observations[(str(example.episode_id), str(example.decision_node_id))] = _target_observation(
            prepared, state, taxi_reference
        )
    representation_rows = []
    downstream_rows = []
    prepared_by_key = {
        (str(example.episode_id), str(example.decision_node_id)): (prepared, prefix[-1])
        for example, prepared, prefix in exact_rows
    }
    bundle = exp2_inputs.load_data2_reference_bundle(exp2_inputs._reference_payloads())
    context_cache = {}
    for (episode, node), group in scenarios.groupby(
        ["episode_id", "canonical_decision_node_id"], sort=True
    ):
        key = (str(episode), str(node))
        base = {"episode_id": episode, "decision_node_id": node}
        representation_rows.append({
            **base,
            **node_representation(group, observations[key], supports=supports),
        })
        prepared, state = prepared_by_key[key]
        context_key = (
            prepared.episode.connection_airport_id,
            exp2_inputs._destination(state),
            state.decision_node.decision_time.month,
            (state.decision_node.decision_time.month - 1) // 3 + 1,
        )
        if context_key not in context_cache:
            context_cache[context_key] = _m2_context(prepared, state, bundle)
        downstream_rows.append({
            **base,
            **downstream_native_summary(group, context_cache[context_key], supports),
        })
    return pd.DataFrame(representation_rows), pd.DataFrame(downstream_rows)


__all__ = [
    "SCENARIO_PATH",
    "analyze_nodes",
    "load_scenario_artifact",
]
