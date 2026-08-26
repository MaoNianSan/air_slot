"""Exp2B consequence-representation comparison records (r=7 / r=3 / r=1).

Materializes the manuscript ``eq:exp_consequence_projection`` comparison
(``Rolling_Airline_Recovery_v2/sections/05_experiment.tex`` L170-197) on the
frozen Development records.  Three representations of the action consequence
are compared: Seven-Component (r=7), Three-Channel (r=3:
Flight / Passenger / Resource), and Scalar (r=1, total over supported
components).  The action-selection rule is the frozen M4 mechanism
(min J = 0.75*E + 0.25*CVaR_alpha over the aligned scenario ensemble,
alpha=0.90, deterministic tie-break by action_id, A00 required in the
comparison set). Its Top-1 fields are conditional diagnostic outputs, never
operational recommendations: A00 is a baseline only and operational selection
is delegated to ``exp.exp3.a00_baseline_gate``. Monetary reporting is the constructed-EUR five-anchor
system; ``P_itinerary``/``P_service`` stay ABSTAIN for money (F7) and are
reported as event counts only.  Coarse sums aggregate only supported
components; an unsupported component is never zero-filled (03_methodology.tex
L225-227).  r=7 rows are numerically identical to the frozen Exp3 BASE
action-risk rows and are parity-checked against them.

Development-only: safety all zero, paper_result=false, no Final Test access.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.official_execution import file_sha256, load_json, write_json
from exp.exp3.global_development import (
    ACTION_REGISTRY,
    EXP2_ROOT,
    FIVE_ANCHOR_COMPONENTS,
    INPUT_ROOT,
    M2_REGISTRY,
    MAPPING_REGISTRY,
    PENDING_MONETARY_COMPONENTS,
    RESPONSE_REGISTRY,
    RISK_POLICY,
    SEED,
    SENSITIVITY_LEVELS,
    _conditional_risk,
    _require,
)
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import ResponseScenarioRegistry
from model.PRE.contracts.pre_state import PREState

DEFAULT_OUTPUT = Path("artifacts/experiment/exp2/exp2b_consequence_representation_20260826")
EXISTING_ACTION_RISK = Path(
    "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
EXPECTED_REGISTRY_HASH = "sha256:88beec332b885baf90cef90e3cc8091c8679f4ea93628c0e9227cd919c76d6a3"
CHANNELS = {
    "Flight": ("F_continuity", "F_execution", "F_propagation"),
    "Passenger": ("P_time",),
    "Resource": ("R_operating",),
}

CHANNEL_ORDER = ("Flight", "Passenger", "Resource")

MATCHED_CASE_PROTOCOL = {
    "decision_id": "D1=A (AIR_SLOT_HUMAN_GATES_ALL_APPROVED_20260826)",
    "pairing_unit": "episode",
    "similarity_band": "episode-level decile band of the r=7 supported-component "
                       "total J (sum of the top-1 r7 residual-risk objective over "
                       "the episode's common-scope decision nodes)",
    "composition_definition": "top-3 channel-share flip in at least two of the F/P/R "
                              "channels (the rank order of the three baseline channel "
                              "shares differs in at least two channels)",
    "directions": "both A_TO_B and B_TO_A reported per pair",
    "tie_break": "deterministic: pairs sorted by (decile, total_j, episode_id); share "
                 "ties broken by fixed channel order (Flight, Passenger, Resource)",
    "tuning": "not tuned; declared protocol, frozen",
}
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "EXP2_RUNS": 0,
    "PAPER_FULL_RUN": False,
}
SCHEMA_VERSION = "AIR_SLOT_EXP2B_CONSEQUENCE_REPRESENTATION_V1"
TOP1_SEMANTICS = "CONDITIONAL_DIAGNOSTIC_NOT_OPERATIONAL_RECOMMENDATION"

RECORDS_SCHEMA = pa.schema([
    pa.field("episode_id", pa.string()),
    pa.field("decision_node_id", pa.string()),
    pa.field("representation", pa.string()),
    pa.field("action_id", pa.string()),
    pa.field("action_family", pa.string()),
    pa.field("response_support", pa.string()),
    pa.field("scenario_count", pa.int64()),
    pa.field("finite_support_scenario_count", pa.int64()),
    pa.field("finite_support_rate", pa.float64()),
    pa.field("expected_constructed_eur", pa.float64()),
    pa.field("constructed_eur_cvar_alpha", pa.float64()),
    pa.field("residual_risk_objective", pa.float64()),
    pa.field("top1", pa.bool_()),
    pa.field("rank_position", pa.int64()),
    pa.field("p_itinerary_event_count", pa.float64()),
    pa.field("p_service_event_count", pa.float64()),
    pa.field("exclusion_reason", pa.string()),
])


def _scenario_loss(post: dict[str, float], money_rates: dict[str, float],
                   representation: str) -> tuple[float | None, float, float]:
    """Monetary loss under the r=7/r=3/r=1 projections.

    Returns (loss, itinerary_events, service_events).  Only supported
    components enter a sum; P_itinerary/P_service never enter money.
    """
    if representation == "r7":
        if not all(
            money_rates[name] is not None and post.get(name) is not None
            for name in FIVE_ANCHOR_COMPONENTS
        ):
            return None, post.get("P_itinerary"), post.get("P_service")
        values = [post[name] * money_rates[name] for name in FIVE_ANCHOR_COMPONENTS]
        return float(np.sum(values)), post.get("P_itinerary"), post.get("P_service")
    if representation == "r3":
        channel_values: list[float] = []
        for names in CHANNELS.values():
            supported = [
                post[name] * money_rates[name] for name in names
                if money_rates[name] is not None and post.get(name) is not None
            ]
            if supported:
                channel_values.append(float(np.sum(supported)))
        if not channel_values:
            return None, post.get("P_itinerary"), post.get("P_service")
        return float(np.sum(channel_values)), post.get("P_itinerary"), post.get("P_service")
    if representation == "r1":
        supported = [
            post[name] * money_rates[name] for name in FIVE_ANCHOR_COMPONENTS
            if money_rates[name] is not None and post.get(name) is not None
        ]
        if not supported:
            return None, post.get("P_itinerary"), post.get("P_service")
        return float(np.sum(supported)), post.get("P_itinerary"), post.get("P_service")
    raise ValueError("EXP2B_UNKNOWN_REPRESENTATION")


def materialize(
    *, root: Path, exp2_root: Path | None = None, input_root: Path | None = None,
    output_root: Path | None = None, response_scenario_limit: int | None = None,
) -> dict[str, Path]:
    root = root.resolve()
    exp2_root = (exp2_root or root / EXP2_ROOT).resolve()
    input_root = (input_root or root / INPUT_ROOT).resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    paths = {
        "exp2_manifest": exp2_root / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json",
        "consequences": exp2_root / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet",
        "inputs": input_root / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json",
        "action_registry": root / ACTION_REGISTRY,
        "response_registry": root / RESPONSE_REGISTRY,
        "m2_registry": root / M2_REGISTRY,
        "mapping_registry": root / MAPPING_REGISTRY,
        "risk_policy": root / RISK_POLICY,
        "existing_action_risk": root / EXISTING_ACTION_RISK,
    }
    _require(all(path.is_file() for path in paths.values()), "EXP2B_INPUT_MISSING")
    exp2_manifest = load_json(paths["exp2_manifest"])
    inputs = load_json(paths["inputs"])
    mapping = load_json(paths["mapping_registry"])
    policy_payload = load_json(paths["risk_policy"])
    _require(exp2_manifest["dataset"] == "DATA2" and exp2_manifest["split"] == "DEVELOPMENT", "EXP2B_EXP2_SCOPE_INVALID")
    _require(exp2_manifest["episode_count"] == 128 and exp2_manifest["node_count"] == 1769, "EXP2B_EXP2_CARDINALITY_INVALID")
    _require(file_sha256(paths["consequences"]) == exp2_manifest["artifact_hashes"]["consequences"], "EXP2B_EXP2_HASH_MISMATCH")
    _require(
        mapping.get("registry_hash") == EXPECTED_REGISTRY_HASH,
        "EXP2B_EUR_MAPPING_REGISTRY_DRIFT",
    )
    components = mapping.get("ops_components")
    _require(isinstance(components, list) and len(components) == 7, "EXP2B_MAPPING_INVALID")
    anchor_status = {item["component_id"]: item["anchor_status"] for item in components}
    _require(
        tuple(sorted(name for name, status in anchor_status.items() if status == "FROZEN_ASSUMPTION_GROUNDED"))
        == tuple(sorted(FIVE_ANCHOR_COMPONENTS)),
        "EXP2B_MAPPING_FIVE_ANCHOR_DRIFT",
    )
    money_rates_base: dict[str, float | None] = {
        item["component_id"]: next(
            band["per_cu_money"] for band in item["bands"] if band["band_id"] == "BASE"
        )
        for item in components
    }
    policy = policy_payload["policy"]
    alpha = float(policy["alpha"])
    expected_coefficient = float(policy["expected_loss_coefficient"])
    cvar_coefficient = float(policy["cvar_coefficient"])
    action_registry = ActionRegistry.load(paths["action_registry"])
    response_registry = ResponseScenarioRegistry.load(
        paths["response_registry"], structural_registry=action_registry,
    )
    templates = {item.template_id: item for item in action_registry.templates}
    pre_by_node: dict[str, dict[str, Any]] = {}
    for states in inputs["pre_states_by_episode"].values():
        for state in states:
            pre_by_node[state["decision_node"]["decision_node_id"]] = state

    output_root.mkdir(parents=True, exist_ok=True)
    records_path = output_root / "EXP2B_RECORDS_DEVELOPMENT_ONLY.parquet"
    records_csv = output_root / "EXP2B_RECORDS_DEVELOPMENT_ONLY.csv"
    summary_path = output_root / "EXP2B_SUMMARY_DEVELOPMENT_ONLY.csv"
    node_summary_path = output_root / "EXP2B_NODE_SUMMARY_DEVELOPMENT_ONLY.csv"
    temporary = records_path.with_suffix(".parquet.tmp")
    writer: pq.ParquetWriter | None = None
    parquet = pq.ParquetFile(paths["consequences"])
    node_rows: list[dict[str, Any]] = []
    node_summary: list[dict[str, Any]] = []
    top1_by_representation: dict[str, dict[str, str]] = {r: {} for r in ("r7", "r3", "r1")}
    exclusion_counts: Counter[str] = Counter()
    r7_parity_rows: list[tuple[str, str, float]] = []
    node_count = 0
    try:
        for row_group in range(parquet.num_row_groups):
            source_rows = parquet.read_row_group(row_group).to_pylist()
            node_ids = {row["decision_node_id"] for row in source_rows}
            _require(len(node_ids) == 1, "EXP2B_NODE_ROW_GROUP_INVALID")
            node_id = next(iter(node_ids))
            if response_scenario_limit is not None:
                _require(response_scenario_limit > 0, "EXP2B_RESPONSE_SCENARIO_LIMIT_INVALID")
                source_rows = source_rows[:response_scenario_limit]
            total_weight = sum(float(row["scenario_weight"]) for row in source_rows)
            _require(total_weight > 0, "EXP2B_SCENARIO_WEIGHT_INVALID")
            pre = PREState.model_validate(pre_by_node[node_id])
            candidates = instantiate_candidates(
                pre, action_registry, response_registry=response_registry,
                sensitivity="BASE",
            )
            _require(len(candidates) == 23, "EXP2B_ACTION_LIBRARY_CARDINALITY_INVALID")
            per_representation: dict[str, list[dict[str, Any]]] = {r: [] for r in ("r7", "r3", "r1")}
            for candidate in candidates:
                template = templates[candidate.template_id]
                parameters = response_registry.parameters(candidate.template_id, sensitivity="BASE")
                for representation in ("r7", "r3", "r1"):
                    values: list[float] = []
                    weights: list[float] = []
                    itinerary_events: list[float] = []
                    itinerary_weights: list[float] = []
                    service_events: list[float] = []
                    service_weights: list[float] = []
                    for row in source_rows:
                        components = json.loads(row["components_json"])
                        supported = {
                            item["component_id"]: float(item["constructed_value_cu"])
                            for item in components
                            if item["constructed_value_cu"] is not None
                        }
                        if representation == "r7" and not all(
                            component in supported for component in FIVE_ANCHOR_COMPONENTS
                        ):
                            continue
                        if not any(component in supported for component in FIVE_ANCHOR_COMPONENTS):
                            continue
                        rho = response_draw(
                            seed=SEED,
                            episode_id=row["episode_id"],
                            decision_node_id=node_id,
                            scenario_id=int(row["scenario_id"]),
                            action_template_id=candidate.template_id,
                            parameters=parameters,
                            response_registry_hash=response_registry.registry_hash,
                            sensitivity_level="BASE",
                        )
                        post = action_post_consequences(
                            pre_by_component=supported,
                            mitigation=template.mitigation,
                            induced=template.induced,
                            rho=rho,
                            induced_score_to_cu=float(
                                parameters.get(
                                    "induced_score_to_cu",
                                    response_registry.induced_score_to_cu,
                                )
                            ),
                            included_components=tuple(supported),
                        )
                        loss, itin, svc = _scenario_loss(post, money_rates_base, representation)
                        if loss is None:
                            continue
                        values.append(loss)
                        weights.append(float(row["scenario_weight"]))
                        if itin is not None:
                            itinerary_events.append(itin)
                            itinerary_weights.append(float(row["scenario_weight"]))
                        if svc is not None:
                            service_events.append(svc)
                            service_weights.append(float(row["scenario_weight"]))
                    conditional = _conditional_risk(
                        values, weights, alpha=alpha,
                        expected_coefficient=expected_coefficient,
                        cvar_coefficient=cvar_coefficient,
                    )
                    support_weight = float(np.sum(weights))
                    itin_weight = float(np.sum(itinerary_weights))
                    svc_weight = float(np.sum(service_weights))
                    itin_count = (
                        float(np.sum(np.array(itinerary_events) * np.array(itinerary_weights))) / itin_weight
                        if itin_weight > 0 else None
                    )
                    svc_count = (
                        float(np.sum(np.array(service_events) * np.array(service_weights))) / svc_weight
                        if svc_weight > 0 else None
                    )
                    row_record = {
                        "episode_id": pre.decision_node.episode_id,
                        "decision_node_id": node_id,
                        "representation": representation,
                        "action_id": candidate.template_id,
                        "action_family": candidate.action_family,
                        "response_support": (
                            "IDENTITY" if candidate.template_id == "A00" else "SCENARIO_ASSUMPTION"
                        ),
                        "scenario_count": len(source_rows),
                        "finite_support_scenario_count": len(values),
                        "finite_support_rate": support_weight / total_weight if total_weight > 0 else 0.0,
                        "expected_constructed_eur": None if conditional is None else conditional["expected_constructed_eur"],
                        "constructed_eur_cvar_alpha": None if conditional is None else conditional["constructed_eur_cvar_alpha"],
                        "residual_risk_objective": None if conditional is None else conditional["residual_risk_objective"],
                        "top1": False,
                        "rank_position": None,
                        "p_itinerary_event_count": itin_count,
                        "p_service_event_count": svc_count,
                        "exclusion_reason": None if conditional is not None else "EXP2B_NO_FINITE_SUPPORT",
                    }
                    per_representation[representation].append(row_record)
                    if representation == "r7" and conditional is not None:
                        r7_parity_rows.append((node_id, candidate.template_id, conditional["residual_risk_objective"]))
            # deterministic Top-1 per representation (frozen tie-break by action_id)
            for representation in ("r7", "r3", "r1"):
                comparable = _select_top1(per_representation[representation])
                for rank, row in enumerate(comparable, start=1):
                    row["rank_position"] = rank
                if comparable:
                    comparable[0]["top1"] = True
                    top1_by_representation[representation][node_id] = comparable[0]["action_id"]
                else:
                    exclusion_counts[f"EXP2B_{representation.upper()}_NO_COMPARABLE_ACTION"] += 1
            node_rows.extend(per_representation["r7"])
            node_rows.extend(per_representation["r3"])
            node_rows.extend(per_representation["r1"])
            top1_row = {
                r: next(
                    (row for row in per_representation[r] if row["top1"]), None
                )
                for r in ("r7", "r3", "r1")
            }
            baseline_shares = _baseline_channel_shares(source_rows, money_rates_base)
            node_summary.append({
                "episode_id": pre.decision_node.episode_id,
                "decision_node_id": node_id,
                "top1_r7": top1_by_representation["r7"].get(node_id),
                "top1_r3": top1_by_representation["r3"].get(node_id),
                "top1_r1": top1_by_representation["r1"].get(node_id),
                "family_r7": top1_row["r7"]["action_family"] if top1_row["r7"] else None,
                "family_r3": top1_row["r3"]["action_family"] if top1_row["r3"] else None,
                "family_r1": top1_row["r1"]["action_family"] if top1_row["r1"] else None,
                "baseline_total_constructed_eur": baseline_shares["total"],
                "channel_share_flight": baseline_shares["Flight"],
                "channel_share_passenger": baseline_shares["Passenger"],
                "channel_share_resource": baseline_shares["Resource"],
                "exclusion_reason": (
                    None if node_id in top1_by_representation["r7"]
                    and node_id in top1_by_representation["r3"]
                    and node_id in top1_by_representation["r1"]
                    else "EXP2B_NOT_IN_COMMON_SCOPE"
                ),
            })
            node_count += 1
            table = pa.Table.from_pylist(node_rows[-23 * 3:]).cast(RECORDS_SCHEMA)
            if writer is None:
                writer = pq.ParquetWriter(temporary, RECORDS_SCHEMA, compression="zstd")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    _require(node_count == 1769, "EXP2B_NODE_COUNT_INVALID")
    temporary.replace(records_path)

    node_frame = pd.DataFrame(node_summary)
    node_frame.to_csv(node_summary_path, index=False)

    # endpoints
    common = node_frame[node_frame["exclusion_reason"].isna()]
    summary_rows: list[dict[str, Any]] = []
    for representation in ("r3", "r1"):
        changed = int((common[f"top1_{representation}"] != common["top1_r7"]).sum())
        summary_rows.append({
            "endpoint": "CONDITIONAL_TOP1_DIFFERENCE_RATE",
            "representation": representation,
            "n_common_scope_nodes": len(common),
            "n_changed": changed,
            "estimate": changed / len(common) if len(common) else None,
        })
    # action-family composition of changed decisions
    family_transitions: Counter[tuple[str, str, str]] = Counter()
    for _, row in common.iterrows():
        for representation in ("r3", "r1"):
            if row[f"top1_{representation}"] != row["top1_r7"]:
                family_transitions[(
                    row["family_r7"], row[f"family_{representation}"], representation,
                )] += 1
    family_rows = [
        {
            "representation": representation,
            "family_r7": family7,
            "family_r": family_r,
            "n_changed": count,
        }
        for (family7, family_r, representation), count in family_transitions.items()
    ]
    # matched-case (D1=A): pair episodes in the same episode-level decile band of
    # the r=7 supported-component total J; composition differs on a top-3
    # channel-share flip in at least two F/P/R channels; both directions reported
    records_frame = pd.DataFrame(node_rows)
    matched_rows = _matched_case_rows(node_frame, records_frame)

    summary_frame = pd.DataFrame(summary_rows)
    family_frame = pd.DataFrame(family_rows)
    matched_frame = pd.DataFrame(matched_rows)
    summary_frame.to_csv(summary_path, index=False)
    family_path = output_root / "EXP2B_FAMILY_TRANSITIONS_DEVELOPMENT_ONLY.csv"
    matched_path = output_root / "EXP2B_MATCHED_CASE_DEVELOPMENT_ONLY.csv"
    family_frame.to_csv(family_path, index=False)
    matched_frame.to_csv(matched_path, index=False)

    # parity vs existing Exp3 BASE rows (r=7 must be identical)
    existing = pd.read_parquet(paths["existing_action_risk"])
    existing = existing[existing["response_sensitivity"] == "BASE"]
    existing_map = {
        (row["decision_node_id"], row["action_id"]): float(row["conditional_residual_risk"])
        for row in existing.to_dict(orient="records")
        if row["conditional_residual_risk"] is not None
    }
    parity_diffs = [
        abs(value - existing_map[(node, action)])
        for node, action, value in r7_parity_rows
        if (node, action) in existing_map
    ]
    parity_max = float(max(parity_diffs)) if parity_diffs else None
    parity_matched = len(parity_diffs)

    records_frame.to_csv(records_csv, index=False)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scope": "DATA2_FULL_DEVELOPMENT_NO_FINAL_TEST",
        "dataset": "DATA2",
        "split": "DEVELOPMENT",
        "status": "MATERIALIZED",
        "episode_count": 128,
        "node_count": node_count,
        "representations": ["r7", "r3", "r1"],
        "channels": CHANNELS,
        "action_count": 23,
        "selection_rule": "MIN_J_LAMBDA_0_25_ALPHA_0_90_TIE_ACTION_ID_A00_REQUIRED",
        "top1_semantics": TOP1_SEMANTICS,
        "operational_recommendation": "A00_BASELINE_GATE_V2_REQUIRED",
        "monetary_rule": "F5_CONSTRUCTED_EUR_FIVE_ANCHOR_BASE",
        "abstain_rule": "F7_P_ITIN_P_SERV_EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
        "coarse_sum_rule": "SUPPORTED_COMPONENTS_ONLY_NO_ZERO_FILL",
        "matched_case_rule": "D1=A_EPISODE_DECILE_BAND_TOTAL_J_PAIRING_TOP3_CHANNEL_FLIP",
        "matched_case_protocol": MATCHED_CASE_PROTOCOL,
        "exclusion_counts": dict(exclusion_counts),
        "r7_vs_exp3_base_parity": {
            "matched_rows": parity_matched,
            "max_abs_diff": parity_max,
            "tolerance": 1e-9,
            "status": "PASS" if parity_max is not None and parity_max < 1e-9 else "DRIFT",
        },
        "endpoints": summary_frame.to_dict(orient="records"),
        "input_hashes": {
            "consequences": exp2_manifest["artifact_hashes"]["consequences"],
            "inputs": file_sha256(paths["inputs"]),
            "action_registry": file_sha256(paths["action_registry"]),
            "response_registry": file_sha256(paths["response_registry"]),
            "m2_registry": file_sha256(paths["m2_registry"]),
            "mapping_registry": file_sha256(paths["mapping_registry"]),
            "risk_policy": file_sha256(paths["risk_policy"]),
        },
        "safety": dict(SAFETY),
        "paper_result": False,
        "outputs": {
            "records": str(records_path.relative_to(root)),
            "records_csv": str(records_csv.relative_to(root)),
            "summary": str(summary_path.relative_to(root)),
            "node_summary": str(node_summary_path.relative_to(root)),
            "family_transitions": str(family_path.relative_to(root)),
            "matched_case": str(matched_path.relative_to(root)),
        },
    }
    write_json(output_root / "EXP2B_MANIFEST_DEVELOPMENT_ONLY.json", manifest)
    return {
        "manifest": output_root / "EXP2B_MANIFEST_DEVELOPMENT_ONLY.json",
        "records": records_path, "summary": summary_path,
        "node_summary": node_summary_path,
        "family_transitions": family_path, "matched_case": matched_path,
    }


def _select_top1(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic Top-1 selection: min residual-risk objective with
    tie-break by action_id (frozen M4 ranking semantics).  Returns the
    comparable rows sorted by (objective, action_id)."""
    comparable = [
        row for row in rows
        if row["residual_risk_objective"] is not None
    ]
    comparable.sort(key=lambda row: (row["residual_risk_objective"], row["action_id"]))
    return comparable


def _baseline_channel_shares(
    source_rows: list[dict[str, Any]], money_rates: dict[str, float | None],
) -> dict[str, float | None]:
    """Scenario-weighted baseline (pre-action) monetary total and channel shares."""
    totals = {"Flight": 0.0, "Passenger": 0.0, "Resource": 0.0}
    weight_sum = 0.0
    for row in source_rows:
        components = json.loads(row["components_json"])
        supported = {
            item["component_id"]: float(item["constructed_value_cu"])
            for item in components
            if item["constructed_value_cu"] is not None
        }
        if not any(component in supported for component in FIVE_ANCHOR_COMPONENTS):
            continue
        weight = float(row["scenario_weight"])
        for channel, names in CHANNELS.items():
            totals[channel] += weight * float(np.sum([
                supported[name] * money_rates[name] for name in names
                if name in supported and money_rates[name] is not None
            ]))
        weight_sum += weight
    if weight_sum <= 0:
        return {"total": None, "Flight": None, "Passenger": None, "Resource": None}
    total = sum(totals.values())
    return {
        "total": total / weight_sum,
        "Flight": totals["Flight"] / total if total > 0 else None,
        "Passenger": totals["Passenger"] / total if total > 0 else None,
        "Resource": totals["Resource"] / total if total > 0 else None,
    }


def _episode_aggregates(node_frame: pd.DataFrame, records_frame: pd.DataFrame) -> pd.DataFrame:
    """Episode-level D1=A aggregates over common-scope decision nodes.

    Episode total J = sum of the top-1 r7 residual-risk objective over the
    episode's common-scope nodes; channel shares = baseline-total-weighted
    average of the per-node baseline channel shares.
    """
    common = node_frame[node_frame["exclusion_reason"].isna()].copy()
    r7 = records_frame[
        (records_frame["representation"] == "r7") & (records_frame["top1"])
    ][["decision_node_id", "residual_risk_objective"]]
    common = common.merge(
        r7.rename(columns={"residual_risk_objective": "top1_j_r7"}),
        on="decision_node_id", how="left",
    )
    rows: list[dict[str, Any]] = []
    for episode_id, group in common[common["top1_j_r7"].notna()].groupby("episode_id", sort=True):
        total_j = float(group["top1_j_r7"].sum())
        weight = pd.to_numeric(group["baseline_total_constructed_eur"], errors="coerce")
        weight_ok = weight.notna() & weight.gt(0)
        shares: dict[str, float | None] = {}
        for channel in CHANNEL_ORDER:
            column = f"channel_share_{channel.lower()}"
            values = pd.to_numeric(group[column], errors="coerce")
            ok = values.notna() & weight_ok
            if ok.any():
                shares[channel] = float((values[ok] * weight[ok]).sum() / weight[ok].sum())
            elif values.notna().any():
                shares[channel] = float(values[values.notna()].mean())
            else:
                shares[channel] = None
        rows.append({
            "episode_id": episode_id,
            "n_common_scope_nodes": int(len(group)),
            "total_j_r7": total_j,
            "share_flight": shares["Flight"],
            "share_passenger": shares["Passenger"],
            "share_resource": shares["Resource"],
        })
    return pd.DataFrame(rows)


def _channel_ranks(episode: dict[str, Any]) -> dict[str, int | None]:
    """Rank the three channel shares descending; ties broken by fixed channel order."""
    values = {
        channel: episode.get(f"share_{channel.lower()}")
        for channel in CHANNEL_ORDER
    }
    valid = {channel: value for channel, value in values.items() if value is not None}
    if len(valid) < 2:
        return {channel: None for channel in CHANNEL_ORDER}
    ranked = sorted(
        valid, key=lambda channel: (-valid[channel], CHANNEL_ORDER.index(channel)),
    )
    result: dict[str, int | None] = {}
    for position, channel in enumerate(ranked, start=1):
        result[channel] = position
    for channel in CHANNEL_ORDER:
        result.setdefault(channel, None)
    return result


def _top1_change_rates(
    episode_id: str, node_frame: pd.DataFrame,
) -> tuple[float | None, float | None]:
    """Episode-level r3/r1 vs r7 top-1 change rates on common-scope nodes."""
    nodes = node_frame[
        (node_frame["episode_id"] == episode_id) & node_frame["exclusion_reason"].isna()
    ]
    if len(nodes) == 0:
        return None, None
    return (
        float((nodes["top1_r3"] != nodes["top1_r7"]).mean()),
        float((nodes["top1_r1"] != nodes["top1_r7"]).mean()),
    )


def _matched_case_rows(
    node_frame: pd.DataFrame, records_frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    """D1=A matched-case: pair episodes in the same episode-level decile band of
    the r=7 supported-component total J; ``different composition`` = a top-3
    channel-share flip in at least two of the F/P/R channels; both directions
    reported; deterministic tie-break; declared protocol, not tuned."""
    episodes = _episode_aggregates(node_frame, records_frame)
    if len(episodes) < 2:
        return []
    episodes = episodes[episodes["total_j_r7"].notna()].copy()
    episodes["decile"] = pd.qcut(
        episodes["total_j_r7"], 10, labels=False, duplicates="drop",
    )
    rows: list[dict[str, Any]] = []
    pair_id = 0
    for decile, group in episodes.groupby("decile", sort=True):
        ordered = group.sort_values(["total_j_r7", "episode_id"]).to_dict("records")
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                episode_a, episode_b = ordered[i], ordered[j]
                ranks_a = _channel_ranks(episode_a)
                ranks_b = _channel_ranks(episode_b)
                flipped = [
                    channel for channel in CHANNEL_ORDER
                    if ranks_a.get(channel) is not None
                    and ranks_a.get(channel) != ranks_b.get(channel)
                ]
                composition_different = len(flipped) >= 2
                pair_id += 1
                rates_a = _top1_change_rates(episode_a["episode_id"], node_frame)
                rates_b = _top1_change_rates(episode_b["episode_id"], node_frame)
                for direction, focal, reference in (
                    ("A_TO_B", episode_a, episode_b),
                    ("B_TO_A", episode_b, episode_a),
                ):
                    focal_rates = rates_a if direction == "A_TO_B" else rates_b
                    reference_rates = rates_b if direction == "A_TO_B" else rates_a
                    rows.append({
                        "pair_id": pair_id,
                        "decile": int(decile),
                        "direction": direction,
                        "episode_a": episode_a["episode_id"],
                        "episode_b": episode_b["episode_id"],
                        "total_j_a": episode_a["total_j_r7"],
                        "total_j_b": episode_b["total_j_r7"],
                        "n_common_scope_nodes_a": int(episode_a["n_common_scope_nodes"]),
                        "n_common_scope_nodes_b": int(episode_b["n_common_scope_nodes"]),
                        "share_flight_a": episode_a.get("share_flight"),
                        "share_passenger_a": episode_a.get("share_passenger"),
                        "share_resource_a": episode_a.get("share_resource"),
                        "share_flight_b": episode_b.get("share_flight"),
                        "share_passenger_b": episode_b.get("share_passenger"),
                        "share_resource_b": episode_b.get("share_resource"),
                        "rank_flight_a": ranks_a.get("Flight"),
                        "rank_passenger_a": ranks_a.get("Passenger"),
                        "rank_resource_a": ranks_a.get("Resource"),
                        "rank_flight_b": ranks_b.get("Flight"),
                        "rank_passenger_b": ranks_b.get("Passenger"),
                        "rank_resource_b": ranks_b.get("Resource"),
                        "flipped_channels": "|".join(flipped),
                        "composition_different": composition_different,
                        "focal_top1_change_rate_r3": focal_rates[0],
                        "focal_top1_change_rate_r1": focal_rates[1],
                        "reference_top1_change_rate_r3": reference_rates[0],
                        "reference_top1_change_rate_r1": reference_rates[1],
                    })
    return rows


def matched_case_only(*, root, records_path, node_summary_path, output_root) -> dict[str, Path]:
    """Re-materialize ONLY the D1=A matched-case part from existing records.

    V3 (2026-08-26): if T2 records were already materialized under the
    pre-D1=A matched-case wording, only this part is recomputed; records,
    node summary, endpoints, and family transitions are untouched.
    """
    root = Path(root).resolve()
    records_path = Path(records_path).resolve()
    node_summary_path = Path(node_summary_path).resolve()
    output_root = Path(output_root).resolve()
    _require(root in output_root.parents, "EXP2B_OUTPUT_OUTSIDE_PROJECT")
    records = pd.read_parquet(records_path)
    node_frame = pd.read_csv(node_summary_path)
    matched_rows = _matched_case_rows(node_frame, records)
    matched_frame = pd.DataFrame(matched_rows)
    matched_path = output_root / "EXP2B_MATCHED_CASE_DEVELOPMENT_ONLY.csv"
    matched_path.parent.mkdir(parents=True, exist_ok=True)
    matched_frame.to_csv(matched_path, index=False)
    manifest_path = output_root / "EXP2B_MANIFEST_DEVELOPMENT_ONLY.json"
    _require(manifest_path.is_file(), "EXP2B_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["matched_case_rule"] = "D1=A_EPISODE_DECILE_BAND_TOTAL_J_PAIRING_TOP3_CHANNEL_FLIP"
    manifest["matched_case_protocol"] = MATCHED_CASE_PROTOCOL
    manifest["matched_case"] = {
        "rematerialized": "D1=A_20260826",
        "n_pairs": int(matched_frame["pair_id"].nunique()) if len(matched_frame) else 0,
        "n_direction_rows": int(len(matched_frame)),
        "records_untouched": True,
        "node_summary_untouched": True,
        "endpoints_untouched": True,
        "family_transitions_untouched": True,
    }
    manifest["outputs"]["matched_case"] = str(matched_path.relative_to(root))
    write_json(manifest_path, manifest)
    return {"matched_case": matched_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--response-scenario-limit", type=int)
    parser.add_argument("--matched-case-only", action="store_true")
    parser.add_argument("--records", type=Path)
    parser.add_argument("--node-summary", type=Path)
    args = parser.parse_args(argv)
    if args.matched_case_only:
        _require(args.records is not None and args.node_summary is not None, "EXP2B_MATCHED_CASE_PATHS_REQUIRED")
        matched_case_only(
            root=Path(__file__).resolve().parents[2],
            records_path=args.records, node_summary_path=args.node_summary,
            output_root=args.output_root,
        )
        print("EXP2B_MATCHED_CASE_REMATERIALIZED")
        return 0
    materialize(
        root=Path(__file__).resolve().parents[2],
        exp2_root=args.exp2_root, input_root=args.input_root,
        output_root=args.output_root,
        response_scenario_limit=args.response_scenario_limit,
    )
    print("EXP2B_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
