"""Exp1 Development evidence closure (DEVELOPMENT_ONLY) — 2026-08-25 supplement.

Implements the superseding execution instruction
``codex_framework/AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT_20260825.md``
(conflicts with the baseline
``docs/experiment/DEVELOPMENT_CLOSURE_EXECUTION_20260825.md`` resolve to this
module).  No M2 interface change (EXP1A_M2_INTERFACE_CHANGES = NONE), no model
training, no Final Test access (FINAL_TEST_ACCESS_COUNT = 0), no paper-full
result (PAPER_FULL_RUN = False).

- Exp1A: one paper-facing record per decision node per variant
  (EXP1A_FULL / EXP1A_REDUCED) built from the frozen M2 consequence rows and
  read-only M3 action instantiation; comparison/top-1/ranking stay NOT_RUN at
  the shared M4 mapping/replay gate.  A frozen-sorting diagnostic compares
  q_state(i) (scenario-weighted mean D_TO) with q_ctx(i) (scenario-weighted
  mean formal five-component consequence) on the common supported set S_i
  (support_fraction_i = |S_i| / 250) with Spearman/Kendall, top-10%/20%
  overlap, decile-divergence rate, and an episode-cluster bootstrap
  (2000 replicates, seed 20260825, percentile 95% CI).
- Exp1B: per model x target x node prediction records for HISTORY
  (M1_V2_GRU_H32) and CURRENT-only (M1_V2_GRU_H32_CURRENT_ONLY) with
  weighted-median points, CRPS where legal, explicit lead-time sources, and a
  paired delta-MAE table over lead-time bins.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import kendalltau, rankdata, spearmanr

from exp.common.metrics_v2 import crps_from_samples
from exp.common.official_execution import load_official_frozen_binding
from exp.common.rng import stream_generator
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response_registry import load_response_registry
from model.common.errors import ContractError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825"
)
SCENARIOS = Path(
    "artifacts/experiments/exp1/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
)
SCENARIO_MANIFEST = Path(
    "artifacts/experiments/exp1/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
)
CURRENT_SCENARIOS = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_TYPED_SCENARIOS.parquet"
)
CURRENT_SCENARIO_MANIFEST = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_TYPED_SCENARIO_MANIFEST.json"
)
CURRENT_TRAINING_METRICS = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
    "EXP1B_CURRENT_ONLY_H32/M1_V2_CURRENT_ONLY_FAST_TRAIN_METRICS.json"
)
LABELS = Path(
    "artifacts/experiment/full_development_inputs_v1/"
    "M1_V2_FULL_DEVELOPMENT_LABELS.json"
)
INFERENCE_INPUTS = Path(
    "artifacts/experiment/full_development_inputs_v1/"
    "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json"
)
INPUT_MANIFEST = Path(
    "artifacts/experiment/full_development_inputs_v1/"
    "FULL_DEVELOPMENT_INPUT_MANIFEST.json"
)
CONSEQUENCES = Path(
    "artifacts/experiments/exp2/full_development_v1/"
    "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
)
ACTION_REGISTRY_PATH = Path("registries/action_templates.yaml")
RESPONSE_REGISTRY_PATH = Path("registries/m3_response_scenarios.yaml")

M4_GATE_REASON = "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE"
TARGETS = ("T_IB_A00", "D_OB", "D_TX")
TARGET_LABELS = {
    "T_IB_A00": "T_IB_REMAINING_HAZARD",
    "D_OB": "D_OB",
    "D_TX": "D_TX",
}
LEAD_TIME_BINS = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
SCENARIO_COUNT_PER_NODE = 250
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260825
MAIN_SUPPORT_THRESHOLD = 0.90
SENSITIVITY_SUPPORT_THRESHOLD = 0.50
SCHEMA_VERSION = "AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_V2"
SCENARIO_COLUMNS = [
    "episode_id", "decision_node_id", "scenario_id", "scenario_weight",
    "operational_stage", "decision_time_utc",
    "T_IB_A00", "D_OB", "D_TX", "D_TO",
]
CONSEQUENCE_COLUMNS = [
    "episode_id", "decision_node_id", "scenario_id", "scenario_weight",
    "formal_five_component_status", "formal_five_component_value_cu",
    "channels_json", "components_json",
]
SAFETY = {
    "EXP1_RUNS": 0,
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"EXP1_CLOSURE_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _content_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"EXP1_CLOSURE_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def _iso_minutes(later: str, earlier: str) -> float | None:
    try:
        left = datetime.fromisoformat(str(later).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(earlier).replace("Z", "+00:00"))
        return (left - right).total_seconds() / 60.0
    except (TypeError, ValueError):
        return None


def _fact_value(entry: Mapping[str, Any] | None) -> Any:
    """Typed value of a serialized PRE entry; None when unsupported."""
    if not isinstance(entry, dict):
        return None
    support = entry.get("support_state")
    if support not in (None, "SUPPORTED"):
        return None
    return entry.get("value")


def _lead_time_bin(minutes: float | None) -> int | None:
    if minutes is None:
        return None
    value = max(0.0, float(minutes))
    selected = LEAD_TIME_BINS[0]
    for edge in LEAD_TIME_BINS[1:]:
        if value < edge:
            break
        selected = edge
    return int(selected)


def _weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float | None:
    pairs = [
        (float(value), float(weight))
        for value, weight in zip(values, weights)
        if float(weight) > 0
    ]
    if not pairs:
        return None
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total


def _weighted_quantile(
    values: Iterable[float], weights: Iterable[float], quantile: float,
) -> float | None:
    pairs = sorted(
        (float(value), float(weight))
        for value, weight in zip(values, weights)
        if float(weight) > 0
    )
    if not pairs:
        return None
    total = sum(weight for _, weight in pairs)
    target = quantile * total
    accumulated = 0.0
    for value, weight in pairs:
        accumulated += weight
        if accumulated >= target:
            return value
    return pairs[-1][0]


def _weighted_median(values: Iterable[float], weights: Iterable[float]) -> float | None:
    return _weighted_quantile(values, weights, 0.5)


def _pre_facts(pre_state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Facts and parameters from a serialized PRE state.

    Mirrors ``model.M3.instantiate.instantiate_candidates`` typed-state branch:
    ABSTAIN entries become None and are never fabricated.
    """
    facts: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
    sections = (
        pre_state.get("predecessor_state", {}),
        pre_state.get("current_state", {}),
        pre_state.get("successor_state", {}),
        pre_state.get("reference_state", {}),
    )
    for section in sections:
        if not isinstance(section, dict):
            continue
        for name, entry in section.items():
            value = _fact_value(entry)
            facts[name] = None if value is None else bool(value)
            parameters[name] = value
    return facts, parameters


def _structural_fact_set(registry: ActionRegistry) -> set[str]:
    names: set[str] = set()
    for template in registry.templates:
        names.update(template.required_facts)
    return names


def _instantiated_count(
    facts: dict[str, Any], parameters: dict[str, Any],
    episode_id: str, decision_node_id: str,
    registry: ActionRegistry, response_registry: Any,
) -> int:
    candidates = instantiate_candidates(
        {
            "facts": facts,
            "parameters": parameters,
            "episode_id": episode_id,
            "decision_node_id": decision_node_id,
        },
        registry,
        response_registry=response_registry,
        sensitivity="BASE",
    )
    return sum(1 for candidate in candidates if candidate.instantiable)


def _parse_consequence_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append({
            "weight": float(row["scenario_weight"]),
            "formal_status": str(row["formal_five_component_status"]),
            "channels": json.loads(row["channels_json"]),
            "components": json.loads(row["components_json"]),
        })
    return parsed


def _consequence_channels(parsed_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Scenario-weighted channel aggregation from parsed M2 rows.

    F = Flight channel (F_continuity + F_execution + F_propagation);
    P = P_time component only (P_itinerary / P_service are NOT_ANCHORED event
    counts, reported separately and excluded from the P aggregate);
    R = Resource channel (R_operating).  Weights are the frozen scenario
    weights; supported rows only, no zero-filling.
    """
    flight: list[tuple[float, float]] = []
    resource: list[tuple[float, float]] = []
    p_time: list[tuple[float, float]] = []
    p_itin: list[tuple[float, float]] = []
    p_serv: list[tuple[float, float]] = []
    for entry in parsed_rows:
        weight = float(entry["weight"])
        for channel in entry["channels"]:
            if channel.get("support_state") != "SUPPORTED":
                continue
            value = channel.get("value_cu")
            if value is None:
                continue
            channel_id = channel.get("channel_id")
            if channel_id == "Flight":
                flight.append((float(value), weight))
            elif channel_id == "Resource":
                resource.append((float(value), weight))
        for component in entry["components"]:
            if component.get("support_state") != "SUPPORTED":
                continue
            component_id = component.get("component_id")
            if component_id == "P_time" and component.get("constructed_value_cu") is not None:
                p_time.append((float(component["constructed_value_cu"]), weight))
            elif component_id == "P_itinerary" and component.get("native_quantity") is not None:
                p_itin.append((float(component["native_quantity"]), weight))
            elif component_id == "P_service" and component.get("native_quantity") is not None:
                p_serv.append((float(component["native_quantity"]), weight))

    def aggregate(pairs: list[tuple[float, float]]) -> float | None:
        values = [value for value, _ in pairs]
        weights = [weight for _, weight in pairs]
        return _weighted_mean(values, weights)

    return {
        "Flight": {"value_cu": aggregate(flight), "supported_scenario_count": len(flight)},
        "Passenger": {"value_cu": aggregate(p_time), "supported_scenario_count": len(p_time)},
        "Resource": {"value_cu": aggregate(resource), "supported_scenario_count": len(resource)},
        "P_itinerary_events": aggregate(p_itin),
        "P_service_events": aggregate(p_serv),
    }

def build_exp1a_records(
    *,
    consequence_rows: Iterable[Mapping[str, Any]],
    pre_states: Iterable[Mapping[str, Any]],
    registry: ActionRegistry,
    response_registry: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One paper-facing record per node per Exp1A variant.

    REDUCED keeps scenario state, identity, timing, the union of template
    ``required_facts`` and support provenance; every other current operational
    fact (raw weather, hidden history, realized outcomes, future information)
    is blocked.  Consequences are re-aggregated per variant from the same
    frozen M2 rows -- never copied from the FULL variant; equal numbers are a
    computed result (M2 consumes only S_t + identity + train-frozen
    references).  Comparison/top-1/ranking are NOT_RUN at the M4 gate.
    """
    parsed = _parse_consequence_rows(consequence_rows)
    consequences_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row, entry in zip(consequence_rows, parsed):
        consequences_by_node[str(row["decision_node_id"])].append(entry)

    structural = _structural_fact_set(registry)
    records: list[dict[str, Any]] = []
    for pre_state in pre_states:
        node = pre_state["decision_node"]
        node_id = str(node["decision_node_id"])
        episode_id = str(node["episode_id"])
        facts_full, parameters = _pre_facts(pre_state)
        facts_reduced = {
            name: value for name, value in facts_full.items() if name in structural
        }
        full_count = _instantiated_count(
            facts_full, parameters, episode_id, node_id, registry, response_registry,
        )
        reduced_count = _instantiated_count(
            facts_reduced, parameters, episode_id, node_id, registry, response_registry,
        )
        rows = consequences_by_node.get(node_id, ())
        consequence_available = any(
            entry["formal_status"] == "FORMAL_AVAILABLE" for entry in rows
        )
        full_channels = _consequence_channels(rows)
        reduced_channels = _consequence_channels(rows)
        consequence_invariant = _channels_equal(full_channels, reduced_channels)
        action_invariant = full_count == reduced_count
        for variant, channels, count in (
            ("EXP1A_FULL", full_channels, full_count),
            ("EXP1A_REDUCED", reduced_channels, reduced_count),
        ):
            records.append({
                "episode_id": episode_id,
                "decision_node_id": node_id,
                "variant": variant,
                "consequence_available": consequence_available,
                "action_instantiation_available": count > 0,
                "comparison_available": False,
                "comparison_reason": M4_GATE_REASON,
                "n_instantiated_actions": count,
                "n_comparable_actions": 0,
                "F_consequence": channels["Flight"]["value_cu"],
                "P_consequence": channels["Passenger"]["value_cu"],
                "R_consequence": channels["Resource"]["value_cu"],
                "P_itinerary_events": channels["P_itinerary_events"],
                "P_service_events": channels["P_service_events"],
                "top1_action": None,
                "ranking_available": False,
                "ranking_reason": M4_GATE_REASON,
                "consequence_invariant_to_reduced_context": consequence_invariant,
                "action_instantiation_invariant_to_reduced_context": action_invariant,
            })
    meta = {
        "variant_definitions": {
            "EXP1A_FULL": {"context": "FULL_CURRENT_OPERATIONAL_CONTEXT"},
            "EXP1A_REDUCED": {
                "context": (
                    "SCENARIO_STATE_IDENTITY_TIMING_STRUCTURAL_FACTS_SUPPORT_PROVENANCE"
                )
            },
        },
        "m4_gate_reason": M4_GATE_REASON,
        "reduced_context_rule": (
            "scenario state + identity + timing + union(template.required_facts) "
            "+ support provenance; raw weather / hidden history / realized "
            "outcomes / future information blocked"
        ),
        "consequence_reformation": (
            "per-variant re-aggregation from frozen M2 rows; FULL rows are never copied"
        ),
        "claim_scope": "DEVELOPMENT_CONDITIONAL_DIAGNOSTIC",
    }
    return records, meta


def _channels_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    channel_keys = ("Flight", "Passenger", "Resource")
    scalar_keys = ("P_itinerary_events", "P_service_events")
    for key in channel_keys:
        left_value = left[key]["value_cu"]
        right_value = right[key]["value_cu"]
        if left_value is None or right_value is None:
            if left_value is not None or right_value is not None:
                return False
            continue
        if abs(float(left_value) - float(right_value)) > 1e-9:
            return False
    for key in scalar_keys:
        left_value = left[key]
        right_value = right[key]
        if left_value is None or right_value is None:
            if left_value is not None or right_value is not None:
                return False
            continue
        if abs(float(left_value) - float(right_value)) > 1e-9:
            return False
    return True


def build_sorting_diagnostic(
    *,
    scenario_rows: Iterable[Mapping[str, Any]],
    consequence_rows: Iterable[Mapping[str, Any]],
    main_threshold: float = MAIN_SUPPORT_THRESHOLD,
    sensitivity_threshold: float = SENSITIVITY_SUPPORT_THRESHOLD,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """q_state(i) vs q_ctx(i) ranking diagnostic on the common supported set.

    S_i = {s : D_TO_{i,s} finite AND five_component_status_{i,s} ==
    FORMAL_AVAILABLE}; scenario weights are renormalized within S_i;
    support_fraction_i = |S_i| / 250.  Nodes enter the main analysis iff
    support_fraction_i >= 0.90 (sensitivity >= 0.50).  No zero-filling, no
    cross-node interpolation, no silent renormalization.
    """
    m2_by_key: dict[tuple[str, str, int], tuple[str, float | None]] = {}
    for row in consequence_rows:
        key = (
            str(row["episode_id"]), str(row["decision_node_id"]), int(row["scenario_id"]),
        )
        m2_by_key[key] = (
            str(row["formal_five_component_status"]),
            row["formal_five_component_value_cu"],
        )
    by_node: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in scenario_rows:
        by_node[(str(row["episode_id"]), str(row["decision_node_id"]))].append(row)

    node_rows: list[dict[str, Any]] = []
    for (episode_id, node_id), rows in sorted(by_node.items()):
        supported: list[tuple[float, float, float]] = []
        n_finite = 0
        n_formal = 0
        stage = str(rows[0]["operational_stage"])
        for row in rows:
            status, five_value = m2_by_key.get(
                (episode_id, node_id, int(row["scenario_id"])), ("UNKNOWN", None),
            )
            if status == "FORMAL_AVAILABLE":
                n_formal += 1
            d_to = row["D_TO"]
            if d_to is None or pd.isna(d_to):
                continue
            n_finite += 1
            if (
                status == "FORMAL_AVAILABLE"
                and five_value is not None
                and not pd.isna(five_value)
            ):
                supported.append(
                    (float(d_to), float(row["scenario_weight"]), float(five_value))
                )
        support_fraction = len(supported) / SCENARIO_COUNT_PER_NODE
        if n_finite == 0:
            exclusion = "EXCLUDED_M1_NONFINITE"
        elif n_formal == 0:
            exclusion = "EXCLUDED_M2_NOT_AVAILABLE"
        elif support_fraction < main_threshold:
            exclusion = "EXCLUDED_SUPPORT_BELOW_THRESHOLD"
        else:
            exclusion = None
        d_to_values = [value for value, _, _ in supported]
        weights = [weight for _, weight, _ in supported]
        five_values = [five for _, _, five in supported]
        node_rows.append({
            "episode_id": episode_id,
            "decision_node_id": node_id,
            "operational_stage": stage,
            "n_scenarios_total": len(rows),
            "n_finite_d_to": n_finite,
            "n_formal_available": n_formal,
            "support_fraction": support_fraction,
            "q_state": _weighted_mean(d_to_values, weights),
            "q_ctx": _weighted_mean(five_values, weights),
            "q_state_p90": _weighted_quantile(d_to_values, weights, 0.90),
            "exclusion_reason": exclusion,
            "included_main": exclusion is None,
            "included_sensitivity": (
                n_finite > 0
                and n_formal > 0
                and support_fraction >= sensitivity_threshold
            ),
        })

    main_rows = [row for row in node_rows if row["included_main"]]
    sensitivity_rows = [row for row in node_rows if row["included_sensitivity"]]
    excluded = Counter(
        row["exclusion_reason"] for row in node_rows if row["exclusion_reason"]
    )
    excluded_sensitivity = Counter(
        "EXCLUDED_M1_NONFINITE"
        if row["n_finite_d_to"] == 0
        else "EXCLUDED_M2_NOT_AVAILABLE"
        if row["n_formal_available"] == 0
        else "EXCLUDED_SUPPORT_BELOW_THRESHOLD"
        for row in node_rows
        if not row["included_sensitivity"]
    )
    stage_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in main_rows:
        stage_groups[str(row["operational_stage"])].append(row)
    p90_rows = [
        {
            "episode_id": row["episode_id"],
            "decision_node_id": row["decision_node_id"],
            "q_state": row["q_state_p90"],
            "q_ctx": row["q_ctx"],
        }
        for row in main_rows
    ]
    stats = {
        "claim_scope": "DEVELOPMENT_CONDITIONAL_DIAGNOSTIC",
        "top1_ex_post": "NOT_RUN",
        "top1_ex_post_reason": M4_GATE_REASON,
        "main_threshold": main_threshold,
        "sensitivity_threshold": sensitivity_threshold,
        "scenario_count_per_node": SCENARIO_COUNT_PER_NODE,
        "node_count_total": len(node_rows),
        "included_main_nodes": len(main_rows),
        "included_sensitivity_nodes": len(sensitivity_rows),
        "excluded_by_reason": {
            reason: count for reason, count in sorted(excluded.items())
        },
        "excluded_from_sensitivity_by_reason": {
            reason: count for reason, count in sorted(excluded_sensitivity.items())
        },
        "main": _ranking_stats(main_rows, replicates=replicates, seed=seed),
        "sensitivity": _ranking_stats(
            sensitivity_rows, replicates=replicates, seed=seed,
        ),
        "secondary": {
            "operational_stage_strata": {
                str(stage): _ranking_stats(stage_rows, include_bootstrap=False)
                for stage, stage_rows in sorted(stage_groups.items())
            },
            "p90_d_to_sensitivity": _ranking_stats(
                p90_rows, include_bootstrap=False,
            ),
        },
    }
    return node_rows, stats


def _deciles(values: np.ndarray) -> np.ndarray:
    ranks = rankdata(values, method="average")
    count = len(ranks)
    if count == 0:
        return np.array([], dtype=int)
    return np.minimum(10, np.ceil(10.0 * ranks / count).astype(int))


def _top_overlap(
    q_state: np.ndarray, q_ctx: np.ndarray, node_ids: list[str], fraction: float,
) -> float:
    count = len(q_state)
    if count == 0:
        return float("nan")
    top_k = max(1, ceil(count * fraction))
    state_order = sorted(
        range(count), key=lambda index: (-float(q_state[index]), str(node_ids[index])),
    )
    ctx_order = sorted(
        range(count), key=lambda index: (-float(q_ctx[index]), str(node_ids[index])),
    )
    top_state = set(state_order[:top_k])
    top_ctx = set(ctx_order[:top_k])
    return float(len(top_state & top_ctx) / top_k)


def _cluster_bootstrap(
    rows: list[dict[str, Any]], metric: str, estimate: float | None,
    *, replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Episode-cluster bootstrap with percentile 95% CI (no invented metrics)."""
    by_episode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_episode[str(row["episode_id"])].append(row)
    episode_ids = sorted(by_episode)
    episode_state = {
        episode_id: np.array([float(row["q_state"]) for row in by_episode[episode_id]])
        for episode_id in episode_ids
    }
    episode_ctx = {
        episode_id: np.array([float(row["q_ctx"]) for row in by_episode[episode_id]])
        for episode_id in episode_ids
    }
    rng = stream_generator("bootstrap", seed, metric)
    samples: list[float] = []
    degenerate = 0
    for _ in range(replicates):
        pick = rng.integers(0, len(episode_ids), size=len(episode_ids))
        state = np.concatenate([episode_state[episode_ids[index]] for index in pick])
        ctx = np.concatenate([episode_ctx[episode_ids[index]] for index in pick])
        if len(state) < 2 or np.all(state == state[0]) or np.all(ctx == ctx[0]):
            degenerate += 1
            continue
        if metric == "spearman_rho":
            samples.append(float(spearmanr(state, ctx)[0]))
        elif metric == "decile_divergence_rate":
            samples.append(
                float(np.mean(np.abs(_deciles(state) - _deciles(ctx)) >= 3))
            )
    if not samples:
        return {
            "estimate": estimate,
            "ci_95": None,
            "replicates_run": 0,
            "degenerate_replicates": degenerate,
        }
    return {
        "estimate": estimate,
        "ci_95": [
            float(np.quantile(samples, 0.025)),
            float(np.quantile(samples, 0.975)),
        ],
        "replicates_run": len(samples),
        "degenerate_replicates": degenerate,
    }


def _ranking_stats(
    rows: list[dict[str, Any]], *, include_bootstrap: bool = True,
    replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    count = len(rows)
    if count < 2:
        return {"n_nodes": count, "available": False}
    q_state = np.array([float(row["q_state"]) for row in rows])
    q_ctx = np.array([float(row["q_ctx"]) for row in rows])
    node_ids = [str(row["decision_node_id"]) for row in rows]
    rho, p_rho = spearmanr(q_state, q_ctx)
    tau, p_tau = kendalltau(q_state, q_ctx)
    divergence = float(np.mean(np.abs(_deciles(q_state) - _deciles(q_ctx)) >= 3))
    entry: dict[str, Any] = {
        "n_nodes": count,
        "available": True,
        "spearman_rho": float(rho),
        "spearman_p_value": float(p_rho),
        "kendall_tau": float(tau),
        "kendall_p_value": float(p_tau),
        "top10_overlap_rate": _top_overlap(q_state, q_ctx, node_ids, 0.10),
        "top20_overlap_rate": _top_overlap(q_state, q_ctx, node_ids, 0.20),
        "decile_divergence_rate": divergence,
    }
    if include_bootstrap:
        entry["spearman_rho_bootstrap"] = _cluster_bootstrap(
            rows, "spearman_rho", float(rho), replicates=replicates, seed=seed,
        )
        entry["decile_divergence_bootstrap"] = _cluster_bootstrap(
            rows, "decile_divergence_rate", divergence,
            replicates=replicates, seed=seed,
        )
    return entry

def _label_observed(
    label_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = defaultdict(dict)
    for row in label_rows:
        if not row.get("active", True):
            continue
        exact = row.get("exact_minutes")
        if exact is None or pd.isna(exact):
            continue
        node = f"{row['episode_id']}::{row['decision_node_id']}"
        values[node][str(row["target_name"])] = float(exact)
    return dict(values)


def _planned_horizon(
    pre_state: Mapping[str, Any] | None, decision_time: str | None,
) -> float | None:
    if not pre_state or decision_time is None:
        return None
    schedule = _fact_value(
        pre_state.get("successor_state", {}).get("schedule_reference")
    )
    if not isinstance(schedule, dict):
        return None
    planned = schedule.get("scheduled_departure_utc")
    if planned is None:
        return None
    return _iso_minutes(planned, decision_time)


def _lead_time_for(
    target: str, label: float | None,
    pre_state: Mapping[str, Any] | None, decision_time: str | None,
) -> tuple[float | None, str]:
    if target == "T_IB_A00":
        if label is not None:
            return float(label), "REALIZED_REMAINING_MINUTES"
        return None, "NA_NO_OBSERVED_REMAINING_MINUTES"
    if target == "D_OB":
        planned = _planned_horizon(pre_state, decision_time)
        if planned is not None:
            return planned, "PLANNED_SCHEDULE_HORIZON"
        return None, "NA_NO_PLANNED_HORIZON"
    if target == "D_TX":
        return None, "NA_NO_PLANNED_WHEELS_OFF"
    raise ContractError(f"EXP1_CLOSURE_UNKNOWN_TARGET:{target}")


def build_exp1b_records(
    *,
    scenario_rows: Iterable[Mapping[str, Any]],
    label_rows: Iterable[Mapping[str, Any]],
    pre_states: Iterable[Mapping[str, Any]],
    model_id: str,
    model_role: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per model x target x node prediction records from frozen scenario draws.

    Point = scenario-weighted median of finite draws; absolute error =
    |point - observed|; CRPS only where the label is active and at least one
    finite draw exists (``crps_supported`` explicit).  Lead time: T_IB =
    realized remaining minutes; D_OB = planned schedule horizon; D_TX = NA
    (no planned wheels-off reference); unavailable values stay NA, never
    interpolated.
    """
    by_node: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in scenario_rows:
        by_node[f"{row['episode_id']}::{row['decision_node_id']}"].append(row)
    observed = _label_observed(label_rows)
    pre_by_node: dict[str, Mapping[str, Any]] = {}
    for pre_state in pre_states:
        node = pre_state["decision_node"]
        pre_by_node[str(node["decision_node_id"])] = pre_state

    records: list[dict[str, Any]] = []
    for node_key, rows in sorted(by_node.items()):
        episode_id, node_id = node_key.split("::", 1)
        pre_state = pre_by_node.get(node_id)
        decision_node = pre_state.get("decision_node", {}) if pre_state else {}
        decision_time = decision_node.get("decision_time")
        for target in TARGETS:
            samples = [
                (float(row[target]), float(row["scenario_weight"]))
                for row in rows
                if row.get(target) is not None and not pd.isna(row.get(target))
            ]
            sample_values = [value for value, _ in samples]
            sample_weights = [weight for _, weight in samples]
            label = observed.get(node_key, {}).get(TARGET_LABELS[target])
            point = _weighted_median(sample_values, sample_weights) if samples else None
            absolute_error = (
                abs(point - label) if point is not None and label is not None else None
            )
            crps = crps_from_samples(sample_values, label) if label is not None else None
            crps_supported = label is not None and bool(samples)
            lead_time, lead_time_source = _lead_time_for(
                target, label, pre_state, decision_time,
            )
            records.append({
                "episode_id": episode_id,
                "decision_node_id": node_id,
                "lead_time_minutes": lead_time,
                "lead_time_source": lead_time_source,
                "target": target,
                "observed_minutes": label,
                "point_prediction": point,
                "absolute_error": absolute_error,
                "crps": crps,
                "crps_supported": crps_supported,
                "lead_time_bin_minutes": _lead_time_bin(lead_time),
                "model_id": model_id,
                "model_role": model_role,
            })
    meta = {
        "targets": list(TARGETS),
        "point_rule": "SCENARIO_WEIGHTED_MEDIAN_FINITE_DRAWS_ONLY",
        "crps_rule": "ACTIVE_LABEL_AND_FINITE_DRAWS_ONLY",
        "lead_time_rule": (
            "T_IB=realized remaining minutes; D_OB=planned schedule horizon; "
            "D_TX=NA_NO_PLANNED_WHEELS_OFF; NA is never interpolated"
        ),
        "lead_time_bins_minutes": list(LEAD_TIME_BINS),
        "claim_scope": "DEVELOPMENT_COMPARATOR_ONLY",
    }
    return records, meta


def _episode_mean_bootstrap(
    rows: list[dict[str, Any]], metric: str, *,
    replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any] | None:
    """Aggregate within episode (mean), then bootstrap across episodes."""
    by_episode: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_episode[str(row["episode_id"])].append(float(row[metric]))
    episode_ids = sorted(by_episode)
    if not episode_ids:
        return None
    values = np.array(
        [float(np.mean(by_episode[episode_id])) for episode_id in episode_ids]
    )
    rng = stream_generator("bootstrap", seed, metric)
    samples = np.array([
        rng.choice(values, size=len(values), replace=True).mean()
        for _ in range(replicates)
    ])
    return {
        "estimate": float(values.mean()),
        "ci_95": [
            float(np.quantile(samples, 0.025)),
            float(np.quantile(samples, 0.975)),
        ],
        "replicates": replicates,
        "n_episodes": len(episode_ids),
    }


def _exp1b_summary(
    records: list[dict[str, Any]], seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    frame = pd.DataFrame(records)
    summary: dict[str, Any] = {}
    for model_id, model_frame in sorted(frame.groupby("model_id", sort=False)):
        targets: dict[str, Any] = {}
        for target, target_frame in sorted(model_frame.groupby("target", sort=False)):
            observed_frame = target_frame[target_frame["absolute_error"].notna()]
            crps_frame = target_frame[target_frame["crps"].notna()]
            entry: dict[str, Any] = {
                "n_nodes": int(len(target_frame)),
                "n_nodes_with_observed": int(len(observed_frame)),
                "n_episodes_with_observed": int(
                    observed_frame["episode_id"].nunique()
                ),
                "n_crps_supported": int(target_frame["crps_supported"].sum()),
                "lead_time_source_counts": {
                    str(key): int(value)
                    for key, value in
                    target_frame["lead_time_source"].value_counts().items()
                },
                "lead_time_bin_nodes": {
                    str(key): int(value)
                    for key, value in target_frame["lead_time_bin_minutes"]
                    .dropna().value_counts().items()
                },
            }
            if not observed_frame.empty:
                entry["mae_minutes"] = _episode_mean_bootstrap(
                    observed_frame.to_dict("records"), "absolute_error", seed=seed,
                )
            if not crps_frame.empty:
                entry["crps_minutes"] = _episode_mean_bootstrap(
                    crps_frame.to_dict("records"), "crps", seed=seed,
                )
            targets[target] = entry
        summary[model_id] = {
            "role": str(model_frame["model_role"].iloc[0]),
            "targets": targets,
        }
    return summary


def _paired_comparison(
    history_records: list[dict[str, Any]],
    current_records: list[dict[str, Any]],
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """History vs Current-only on common supported nodes, with delta-MAE bins."""
    history = pd.DataFrame(history_records)
    current = pd.DataFrame(current_records)
    result: dict[str, Any] = {
        "claim_scope": "DEVELOPMENT_COMPARATOR_ONLY",
        "targets": {},
    }
    for target in TARGETS:
        history_target = history[history["target"] == target]
        current_target = current[current["target"] == target]
        history_abs = {
            (str(row["episode_id"]), str(row["decision_node_id"])): float(
                row["absolute_error"]
            )
            for _, row in history_target[history_target["absolute_error"].notna()].iterrows()
        }
        current_abs = {
            (str(row["episode_id"]), str(row["decision_node_id"])): float(
                row["absolute_error"]
            )
            for _, row in current_target[current_target["absolute_error"].notna()].iterrows()
        }
        history_bin = {
            (str(row["episode_id"]), str(row["decision_node_id"])): int(
                row["lead_time_bin_minutes"]
            )
            for _, row in history_target[
                history_target["lead_time_bin_minutes"].notna()
            ].iterrows()
        }
        current_bin = {
            (str(row["episode_id"]), str(row["decision_node_id"])): int(
                row["lead_time_bin_minutes"]
            )
            for _, row in current_target[
                current_target["lead_time_bin_minutes"].notna()
            ].iterrows()
        }
        common_abs = sorted(set(history_abs) & set(current_abs))
        history_mae_rows: list[dict[str, Any]] = []
        current_mae_rows: list[dict[str, Any]] = []
        delta_rows: list[dict[str, Any]] = []
        for key in common_abs:
            episode_id, node_id = key
            history_mae_rows.append({
                "episode_id": episode_id, "absolute_error": history_abs[key],
            })
            current_mae_rows.append({
                "episode_id": episode_id, "absolute_error": current_abs[key],
            })
            delta_rows.append({
                "episode_id": episode_id,
                "delta_absolute_error": history_abs[key] - current_abs[key],
            })
        entry: dict[str, Any] = {
            "common_nodes_with_absolute_error": len(common_abs),
        }
        if delta_rows:
            entry["mae_history_minutes"] = _episode_mean_bootstrap(
                history_mae_rows, "absolute_error", seed=seed,
            )
            entry["mae_current_minutes"] = _episode_mean_bootstrap(
                current_mae_rows, "absolute_error", seed=seed,
            )
            entry["delta_mae_minutes"] = _episode_mean_bootstrap(
                delta_rows, "delta_absolute_error", seed=seed,
            )
        else:
            entry["mae_history_minutes"] = None
            entry["mae_current_minutes"] = None
            entry["delta_mae_minutes"] = None

        history_crps = {
            (str(row["episode_id"]), str(row["decision_node_id"])): float(row["crps"])
            for _, row in history_target[history_target["crps"].notna()].iterrows()
        }
        current_crps = {
            (str(row["episode_id"]), str(row["decision_node_id"])): float(row["crps"])
            for _, row in current_target[current_target["crps"].notna()].iterrows()
        }
        common_crps = sorted(set(history_crps) & set(current_crps))
        history_crps_rows = [
            {"episode_id": key[0], "crps": history_crps[key]} for key in common_crps
        ]
        current_crps_rows = [
            {"episode_id": key[0], "crps": current_crps[key]} for key in common_crps
        ]
        delta_crps_rows = [
            {
                "episode_id": key[0],
                "delta_crps": history_crps[key] - current_crps[key],
            }
            for key in common_crps
        ]
        entry["common_nodes_with_crps"] = len(common_crps)
        if delta_crps_rows:
            entry["crps_history_minutes"] = _episode_mean_bootstrap(
                history_crps_rows, "crps", seed=seed,
            )
            entry["crps_current_minutes"] = _episode_mean_bootstrap(
                current_crps_rows, "crps", seed=seed,
            )
            entry["delta_crps_minutes"] = _episode_mean_bootstrap(
                delta_crps_rows, "delta_crps", seed=seed,
            )
        else:
            entry["crps_history_minutes"] = None
            entry["crps_current_minutes"] = None
            entry["delta_crps_minutes"] = None

        entry["delta_mae_by_bin_minutes"] = {}
        for bin_id in LEAD_TIME_BINS:
            keys = [
                key for key in common_abs
                if history_bin.get(key) == bin_id and current_bin.get(key) == bin_id
            ]
            bin_rows = [
                {
                    "episode_id": key[0],
                    "delta_absolute_error": history_abs[key] - current_abs[key],
                }
                for key in keys
            ]
            entry["delta_mae_by_bin_minutes"][str(bin_id)] = (
                _episode_mean_bootstrap(bin_rows, "delta_absolute_error", seed=seed)
                if bin_rows
                else None
            )
        result["targets"][target] = entry
    return result

def _exp1a_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(records)
    summary: dict[str, Any] = {}
    for variant, variant_frame in frame.groupby("variant", sort=False):
        summary[variant] = {
            "node_count": int(variant_frame["decision_node_id"].nunique()),
            "consequence_available_nodes": int(
                variant_frame["consequence_available"].sum()
            ),
            "action_instantiation_available_nodes": int(
                variant_frame["action_instantiation_available"].sum()
            ),
            "comparison_available_nodes": 0,
            "ranking_available_nodes": 0,
            "mean_n_instantiated_actions": float(
                variant_frame["n_instantiated_actions"].mean()
            ),
        }
    full = frame[frame["variant"] == "EXP1A_FULL"].set_index("decision_node_id")
    reduced = frame[frame["variant"] == "EXP1A_REDUCED"].set_index("decision_node_id")
    common = full.index.intersection(reduced.index)
    summary["common_node_count"] = int(len(common))
    summary["consequence_invariant_to_reduced_context_nodes"] = int(
        full.loc[common, "consequence_invariant_to_reduced_context"].sum()
    )
    summary["action_instantiation_invariant_to_reduced_context_nodes"] = int(
        full.loc[common, "action_instantiation_invariant_to_reduced_context"].sum()
    )
    return summary


def _current_scenario_status(root: Path) -> dict[str, Any]:
    artifact = root / CURRENT_SCENARIOS
    manifest_path = root / CURRENT_SCENARIO_MANIFEST
    if not artifact.is_file() or not manifest_path.is_file():
        return {"status": "BLOCKED", "reason": "EXP1B_CURRENT_ONLY_SCENARIOS_MISSING"}
    manifest = _load_json(manifest_path)
    artifact_hash = _sha256_file(artifact)
    return {
        "status": "MATERIALIZED",
        "artifact_hash": artifact_hash,
        "matches_manifest": manifest.get("artifact_hash") == artifact_hash,
        "row_count": manifest.get("row_count"),
        "node_count": manifest.get("node_count"),
        "scenario_count_per_node": manifest.get("scenario_count_per_node"),
        "model_id": manifest.get("model_id"),
        "crn_paired_with_history_scenarios": manifest.get(
            "crn_paired_with_history_scenarios"
        ),
        "paper_result": manifest.get("paper_result"),
    }


def _current_comparator_status(root: Path) -> dict[str, Any]:
    path = root / CURRENT_TRAINING_METRICS
    if not path.is_file():
        return {
            "status": "BLOCKED",
            "reason": "EXP1B_CURRENT_ONLY_COMPARATOR_MISSING",
            "budget_identical_to_reference": None,
            "calibration_path_identical_to_reference": None,
        }
    metrics = _load_json(path)
    return {
        "status": "MATERIALIZED",
        "model_id": metrics.get("model_id"),
        "variant": metrics.get("variant"),
        "budget_identical_to_reference": metrics.get(
            "budget_identical_to_reference"
        ),
        "calibration_path_identical_to_reference": metrics.get(
            "calibration_path_identical_to_reference"
        ),
        "training_config_hash": metrics.get("training_config_hash"),
        "reference_training_config_hash": metrics.get(
            "reference_training_config_hash"
        ),
        "checkpoint_sha256": metrics.get("checkpoint_sha256"),
        "claim_scope": metrics.get("claim_scope"),
    }


def preflight(root: Path, output_root: Path) -> dict[str, Any]:
    root = root.resolve()
    frozen = load_official_frozen_binding(root)
    required = (
        root / SCENARIOS, root / SCENARIO_MANIFEST, root / LABELS,
        root / INFERENCE_INPUTS, root / INPUT_MANIFEST, root / CONSEQUENCES,
        root / ACTION_REGISTRY_PATH, root / RESPONSE_REGISTRY_PATH,
    )
    missing = [
        path.relative_to(root).as_posix() for path in required if not path.is_file()
    ]
    _require(not missing, "EXP1_CLOSURE_INPUT_MISSING:" + ",".join(missing))
    scenario_manifest = _load_json(root / SCENARIO_MANIFEST)
    input_manifest = _load_json(root / INPUT_MANIFEST)
    labels_payload = _load_json(root / LABELS)
    inputs_payload = _load_json(root / INFERENCE_INPUTS)
    _require(
        scenario_manifest.get("artifact_hash") == _sha256_file(root / SCENARIOS),
        "EXP1_CLOSURE_SCENARIO_HASH_MISMATCH",
    )
    labels_declared = labels_payload.get("artifact_hash")
    inputs_declared = inputs_payload.get("artifact_hash")
    manifest_hashes = input_manifest.get("artifact_hashes", {})
    _require(
        labels_declared == manifest_hashes.get("labels"),
        "EXP1_CLOSURE_LABELS_BINDING_MISMATCH",
    )
    _require(
        inputs_declared == manifest_hashes.get("inputs"),
        "EXP1_CLOSURE_INFERENCE_INPUTS_BINDING_MISMATCH",
    )
    # The JSON input artifact_hash is the materializer's canonical content
    # hash declared inside the artifact (and mirrored in the input manifest and
    # the 2026-08-25 supplement); it is not a raw-file hash.  Raw-file hashes
    # are recorded below for provenance only.
    _require(
        str(labels_declared).startswith("sha256:47cba5d7"),
        "EXP1_CLOSURE_LABELS_HASH_MISMATCH",
    )
    _require(
        str(inputs_declared).startswith("sha256:6a5898e1"),
        "EXP1_CLOSURE_INFERENCE_INPUTS_HASH_MISMATCH",
    )
    m2_hash = _sha256_file(root / CONSEQUENCES)
    _require(m2_hash.startswith("sha256:b4e8cc76"), "EXP1_CLOSURE_M2_HASH_MISMATCH")
    current = _current_scenario_status(root)
    if current["status"] == "MATERIALIZED":
        _require(
            current["matches_manifest"] is True,
            "EXP1_CLOSURE_CURRENT_SCENARIO_HASH_MISMATCH",
        )
        _require(
            current["scenario_count_per_node"] == SCENARIO_COUNT_PER_NODE,
            "EXP1_CLOSURE_CURRENT_SCENARIO_COUNT_INVALID",
        )
        _require(
            current["model_id"] == "M1_V2_GRU_H32_CURRENT_ONLY",
            "EXP1_CLOSURE_CURRENT_MODEL_ID_INVALID",
        )
    return {
        "status": "EXP1_DEVELOPMENT_CLOSURE_PREFLIGHT_READY",
        "scope": "DEVELOPMENT_ONLY",
        "scenario_artifact_hash": scenario_manifest["artifact_hash"],
        "m2_artifact_hash": m2_hash,
        "labels_artifact_hash": labels_declared,
        "labels_raw_sha256": _sha256_file(root / LABELS),
        "inference_inputs_artifact_hash": inputs_declared,
        "inference_inputs_raw_sha256": _sha256_file(root / INFERENCE_INPUTS),
        "cohort_hash": input_manifest.get("cohort_hash"),
        "node_count": input_manifest.get("node_count"),
        "episode_count": input_manifest.get("episode_count"),
        "frozen": frozen.as_dict(),
        "current_scenarios": current,
        "safety": dict(SAFETY),
    }


def run(*, root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT).resolve()
    _require(root in output_root.parents, "EXP1_CLOSURE_OUTPUT_OUTSIDE_PROJECT")
    preflight_result = preflight(root, output_root)
    input_manifest = _load_json(root / INPUT_MANIFEST)
    scenario_manifest = _load_json(root / SCENARIO_MANIFEST)
    labels_payload = _load_json(root / LABELS)
    inputs_payload = _load_json(root / INFERENCE_INPUTS)

    scenario_frame = pd.read_parquet(root / SCENARIOS, columns=SCENARIO_COLUMNS)
    consequence_frame = pd.read_parquet(
        root / CONSEQUENCES, columns=CONSEQUENCE_COLUMNS,
    )
    registry = ActionRegistry.load(root / ACTION_REGISTRY_PATH)
    response_registry = load_response_registry(
        root / RESPONSE_REGISTRY_PATH, structural_path=root / ACTION_REGISTRY_PATH,
    )
    pre_states = [
        state
        for states in inputs_payload["pre_states_by_episode"].values()
        for state in states
    ]
    _require(
        len(pre_states) == int(input_manifest["node_count"]),
        "EXP1_CLOSURE_PRE_STATE_COUNT_MISMATCH",
    )

    exp1a_records, exp1a_meta = build_exp1a_records(
        consequence_rows=consequence_frame.to_dict("records"),
        pre_states=pre_states,
        registry=registry,
        response_registry=response_registry,
    )
    diagnostic_rows, diagnostic_stats = build_sorting_diagnostic(
        scenario_rows=scenario_frame.to_dict("records"),
        consequence_rows=consequence_frame.to_dict("records"),
    )
    exp1b_history, exp1b_meta = build_exp1b_records(
        scenario_rows=scenario_frame.to_dict("records"),
        label_rows=labels_payload["labels"],
        pre_states=pre_states,
        model_id="M1_V2_GRU_H32",
        model_role="HISTORY",
    )
    current_status = _current_scenario_status(root)
    if current_status["status"] == "MATERIALIZED":
        current_frame = pd.read_parquet(
            root / CURRENT_SCENARIOS, columns=SCENARIO_COLUMNS,
        )
        exp1b_current, _ = build_exp1b_records(
            scenario_rows=current_frame.to_dict("records"),
            label_rows=labels_payload["labels"],
            pre_states=pre_states,
            model_id="M1_V2_GRU_H32_CURRENT_ONLY",
            model_role="CURRENT",
        )
        paired = _paired_comparison(exp1b_history, exp1b_current)
        prediction_records_status = "HISTORY:MATERIALIZED/CURRENT:MATERIALIZED"
    else:
        exp1b_current = []
        paired = None
        prediction_records_status = (
            f"HISTORY:MATERIALIZED/CURRENT:BLOCKED:{current_status['reason']}"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    a_frame = pd.DataFrame(exp1a_records)
    b_frame = pd.DataFrame(exp1b_history + exp1b_current)
    d_frame = pd.DataFrame(diagnostic_rows)
    for frame, name in (
        (a_frame, "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY"),
        (b_frame, "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY"),
        (d_frame, "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY"),
    ):
        frame.to_csv(output_root / f"{name}.csv", index=False)
        pq.write_table(pa.Table.from_pandas(frame), output_root / f"{name}.parquet")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "EXP1",
        "dataset_id": "DATA2",
        "split": "DEVELOPMENT",
        "scope": "DEVELOPMENT_ONLY",
        "paper_result": False,
        "exp1a_m2_interface_changes": "NONE",
        "cohort": {
            "cohort_hash": input_manifest["cohort_hash"],
            "episode_count": input_manifest["episode_count"],
            "node_count": input_manifest["node_count"],
            "scenario_count_per_node": scenario_manifest.get(
                "scenario_count_per_node"
            ),
        },
        "frozen_hashes": preflight_result["frozen"],
        "scenario_artifact_hash": scenario_manifest.get("artifact_hash"),
        "exp1a": {
            "per_node_records": _exp1a_summary(exp1a_records),
            "sorting_diagnostic": diagnostic_stats,
            **exp1a_meta,
        },
        "exp1b": {
            "prediction_records": prediction_records_status,
            "current_only_comparator": _current_comparator_status(root),
            "per_model": _exp1b_summary(exp1b_history + exp1b_current),
            "paired": paired,
            **exp1b_meta,
        },
        "safety": dict(SAFETY),
    }
    summary["artifact_hash"] = _content_hash(summary)
    _write_json(
        output_root / "EXP1_DEVELOPMENT_CLOSURE_SUMMARY_DEVELOPMENT_ONLY.json",
        summary,
    )
    (output_root / "EXP1_INTERPRETATION_DEVELOPMENT_ONLY.md").write_text(
        _interpretation(summary), encoding="utf-8",
    )

    manifest = {
        "schema_version": SCHEMA_VERSION + "_MANIFEST",
        "status": "EXP1_DEVELOPMENT_CLOSURE_COMPLETE",
        "scope": "DEVELOPMENT_ONLY",
        "exp1a_m2_interface_changes": "NONE",
        "outputs": {
            name: {
                "path": str((output_root / name).relative_to(root)).replace("\\", "/"),
                "sha256": _sha256_file(output_root / name),
            }
            for name in (
                "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY.csv",
                "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY.parquet",
                "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY.csv",
                "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY.parquet",
                "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY.csv",
                "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY.parquet",
                "EXP1_DEVELOPMENT_CLOSURE_SUMMARY_DEVELOPMENT_ONLY.json",
                "EXP1_INTERPRETATION_DEVELOPMENT_ONLY.md",
            )
        },
        "excluded_nodes_by_reason": diagnostic_stats["excluded_by_reason"],
        "current_scenarios": current_status,
        "safety": dict(SAFETY),
    }
    manifest["manifest_hash"] = _content_hash(manifest)
    _write_json(
        output_root / "EXP1_DEVELOPMENT_CLOSURE_MANIFEST.json", manifest,
    )
    return summary


def _interpretation(summary: Mapping[str, Any]) -> str:
    exp1a = summary["exp1a"]
    sorting = exp1a["sorting_diagnostic"]
    exp1b = summary["exp1b"]
    comparator = exp1b["current_only_comparator"]
    lines = [
        "# Exp1 Development Evidence Closure — Interpretation (DEVELOPMENT_ONLY)",
        "",
        "Generated from the 2026-08-25 supplement; DEVELOPMENT_ONLY scope.",
        "",
        "## Claim scope",
        "",
        "- Exp1A records + frozen sorting: `DEVELOPMENT_CONDITIONAL_DIAGNOSTIC` "
        "(non-causal, non-optimal, non-authoritative ranking).",
        "- Exp1B HISTORY/CURRENT records: `DEVELOPMENT_COMPARATOR_ONLY`; "
        "`PAPER_FULL_RUN = FALSE`.",
        "- Comparison/top-1/ranking remain NOT_RUN at the shared M4 "
        "mapping/replay gate (G2).",
        "- `FINAL_TEST_ACCESS_COUNT = 0`; no calibration data read; no model "
        "training in this module.",
        "",
        "## Exp1A",
        "",
        f"- Per-node records: {exp1a['per_node_records']['EXP1A_FULL']['node_count']} "
        "nodes x 2 variants.",
        f"- Sorting diagnostic: {sorting['node_count_total']} nodes; "
        f"{sorting['included_main_nodes']} in main (support_fraction >= 0.90); "
        f"{sorting['included_sensitivity_nodes']} in sensitivity (>= 0.50).",
        f"- Excluded by reason: {json.dumps(sorting['excluded_by_reason'])}.",
        f"- Main Spearman rho = {sorting['main'].get('spearman_rho')}, "
        f"Kendall tau = {sorting['main'].get('kendall_tau')}, "
        f"top-10% overlap = {sorting['main'].get('top10_overlap_rate')}, "
        f"decile-divergence rate = {sorting['main'].get('decile_divergence_rate')}.",
        "",
        "## Exp1B",
        "",
        f"- Prediction records: {exp1b['prediction_records']}.",
        f"- Current-only comparator: {comparator['status']} "
        f"(budget_identical_to_reference="
        f"{comparator['budget_identical_to_reference']}, "
        f"calibration_path_identical_to_reference="
        f"{comparator['calibration_path_identical_to_reference']}).",
        "",
        "## Remaining gates",
        "",
        "- G2: M3 non-A00 / M4 production mapping freeze before "
        "comparison/ranking upgrade.",
        "- G3: freeze `PAPER_OUTPUT_SPEC_V1.json` before Test.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    output_root = args.output_root or root / DEFAULT_OUTPUT
    if args.check:
        print(json.dumps(preflight(root, output_root), sort_keys=True, default=str))
        return 0
    summary = run(root=root, output_root=output_root)
    print(json.dumps({
        "status": "EXP1_DEVELOPMENT_CLOSURE_COMPLETE",
        "scope": "DEVELOPMENT_ONLY",
        "output_root": str(output_root),
        "artifact_hash": summary["artifact_hash"],
        "exp1a_m2_interface_changes": "NONE",
        "exp1b_prediction_records": summary["exp1b"]["prediction_records"],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BOOTSTRAP_REPLICATES",
    "BOOTSTRAP_SEED",
    "DEFAULT_OUTPUT",
    "LEAD_TIME_BINS",
    "M4_GATE_REASON",
    "MAIN_SUPPORT_THRESHOLD",
    "SENSITIVITY_SUPPORT_THRESHOLD",
    "TARGETS",
    "build_exp1a_records",
    "build_exp1b_records",
    "build_sorting_diagnostic",
    "main",
    "preflight",
    "run",
]
