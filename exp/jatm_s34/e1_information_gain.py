"""E1 Development screening views on the frozen Section 5 cohort.

The runner reuses the Section 5 node builder and the model-owned Stage-I
selector. Exposure factors are read back from the native M2 components
(``P_time`` and ``F_propagation``) paired with the corresponding M1 ``D_TO``;
no second consequence formula is implemented here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from exp.jatm_section5.attention_value import _signal
from exp.jatm_section5.cohorts import canonical_stage_cohort
from exp.jatm_section5.run_development import (
    _build_nodes,
    _canonicalize,
    _reference_eligible,
)
from model.M3.stage1 import select_paired_attention
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import OperationalStage, SupportState
from model.common.identity import content_id
from validation.v2_phase5.common import (
    CURRENT_CHECKPOINT,
    H16_CHECKPOINT,
    chain_id_for_episode,
    load_authorities,
    load_development_bridge,
    load_tail_continuations,
)
from validation.v2_phase5.families import build_consequence_service

Q_GRID = (0.05, 0.10, 0.20, 0.30)
VIEWS = ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM", "CONSEQUENCE")
STAGES = (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB)


def _typed_signal(node, *, score: float | None, signal_type: SignalKind) -> PrioritySignal:
    support = node.support("HISTORY_JOINT")
    if score is None or not support.included:
        return PrioritySignal(
            signal_type=signal_type,
            episode_id=node.episode_id,
            chain_id=node.chain_id,
            node_id=node.node_id,
            representation_id="HISTORY_H16:JOINT",
            score=None,
            support=SupportState.ABSTAIN,
            status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
            comparison_support_mass=float(support.supported_mass),
            comparison_support_threshold=float(support.threshold),
            reason_codes=("E1_NO_COMMON_SUPPORT",),
        )
    status = support.status
    state = SupportState.DEGRADED if support.status is TypedStatus.DEGRADED else SupportState.SUPPORTED
    return PrioritySignal(
        signal_type=signal_type,
        episode_id=node.episode_id,
        chain_id=node.chain_id,
        node_id=node.node_id,
        representation_id="HISTORY_H16:JOINT",
        score=float(score),
        support=state,
        status=status,
        comparison_support_mass=float(support.supported_mass),
        comparison_support_threshold=float(support.threshold),
    )


def _exposure_factors(node) -> tuple[float | None, float | None]:
    state = {item.scenario_id: item for item in node.state("HISTORY_JOINT").scenarios}
    passengers: list[tuple[float, float]] = []
    downstream: list[tuple[float, float]] = []
    for scenario in node.consequences("HISTORY_JOINT").scenarios:
        m1 = state.get(scenario.scenario_id)
        native = scenario.native_components
        if m1 is None or m1.d_to_minutes is None or float(m1.d_to_minutes) <= 1e-12:
            # A supported zero-delay scenario carries zero native exposure but
            # does not identify the node's constant reference factor. Other
            # positive-delay scenarios still identify it exactly.
            continue
        weight = float(scenario.scenario_weight)
        d_to = float(m1.d_to_minutes)
        passengers.append((weight, float(native["P_time"]) / d_to))
        downstream.append((weight, float(native["F_propagation"]) / d_to))
    if not passengers or not downstream:
        return None, None
    total = sum(weight for weight, _ in passengers)
    return (
        sum(weight * value for weight, value in passengers) / total,
        sum(weight * value for weight, value in downstream) / total,
    )


def _select(view_signals, consequence_signals, *, q: float):
    comparator, reference = select_paired_attention(
        view_signals, consequence_signals, q=float(q)
    )
    selected_view = {entry.node_id for entry in comparator.entries if entry.selected}
    selected_ref = {entry.node_id for entry in reference.entries if entry.selected}
    by_id = {item.node_id: item for item in consequence_signals if item.score is not None}
    ref_value = sum(float(by_id[item].score) for item in selected_ref if item in by_id)
    retained = sum(float(by_id[item].score) for item in selected_view if item in by_id)
    return {
        "k": int(comparator.k),
        "n": int(comparator.cohort_size),
        "abstain": int(len(view_signals) - comparator.cohort_size),
        "selected_view": sorted(selected_view),
        "selected_reference": sorted(selected_ref),
        "overlap": len(selected_view & selected_ref),
        "replacement": len(selected_view - selected_ref),
        "retained_consequence": (None if ref_value == 0 else retained / ref_value),
        "reference_consequence_sum": ref_value,
    }


def _bootstrap(stage_nodes, *, view: str, q: float, seed: int, replicates: int) -> dict:
    episodes = sorted({node.episode_id for node in stage_nodes})
    groups = {episode: tuple(node for node in stage_nodes if node.episode_id == episode) for episode in episodes}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(int(replicates)):
        draw = rng.choice(episodes, size=len(episodes), replace=True)
        rows = [node for episode in draw for node in groups[episode]]
        result = _summarize_stage(rows, view=view, q=q)
        values.append(float(result["overlap"]))
    arr = np.asarray(values, dtype=float)
    return {"replicate_count": int(arr.size), "ci_low": float(np.quantile(arr, 0.025)), "ci_high": float(np.quantile(arr, 0.975))}


def _summarize_stage(nodes, *, view: str, q: float) -> dict:
    delay = [_typed_signal(node, score=node.delay_scores["HISTORY_JOINT"], signal_type=SignalKind.DELAY) for node in nodes]
    consequence = [_typed_signal(node, score=node.consequence_scores["HISTORY_JOINT"], signal_type=SignalKind.CONSEQUENCE) for node in nodes]
    if view == "CONSEQUENCE":
        # The model selector exposes one comparator slot alongside its P^C
        # reference. Preserve the P^C score while typing the comparator as the
        # selector's delay-side input.
        comparator = [
            _typed_signal(node, score=node.consequence_scores["HISTORY_JOINT"], signal_type=SignalKind.DELAY)
            for node in nodes
        ]
    elif view == "DELAY":
        comparator = delay
    else:
        comparator = []
        for node, signal in zip(nodes, delay):
            pax, downstream = _exposure_factors(node)
            factor = pax if view == "DELAY_PASSENGER" else downstream
            score = None if signal.score is None or factor is None else float(signal.score) * factor
            comparator.append(_typed_signal(node, score=score, signal_type=SignalKind.DELAY))
    return _select(comparator, consequence, q=q) | {"view": view, "q": float(q)}


def run(*, output_root: Path, node_limit: int | None = None, bootstrap_replicates: int = 2000) -> dict:
    authorities = load_authorities()
    bridge = load_development_bridge()
    tails = load_tail_continuations()
    layer = build_consequence_service(authorities=authorities, bridge=bridge, output_dir=output_root / "materialization")
    nodes = list(_build_nodes(authorities=authorities, bridge=bridge, tails=tails, layer=layer))
    if node_limit is not None:
        nodes = nodes[: int(node_limit)]
    canonical = _canonicalize(nodes, stages=STAGES)
    rows = []
    summaries = []
    for stage in STAGES:
        cohort = tuple(row.node for row in canonical.get(stage, ()) if _reference_eligible(row.node))
        for q in Q_GRID:
            for view in VIEWS:
                result = _summarize_stage(cohort, view=view, q=q)
                result["stage"] = stage.value
                summaries.append(result)
                for node_id in result["selected_view"]:
                    rows.append({"stage": stage.value, "q": q, "view": view, "node_id": node_id, "selected": True})
        for view in VIEWS:
            summaries.append({"stage": stage.value, "q": 0.10, "view": view, "bootstrap": _bootstrap(cohort, view=view, q=0.10, seed=20261011, replicates=bootstrap_replicates)})
    payload = {
        "schema_version": "JATM_S34_E1_DEVELOPMENT_V1",
        "status": "DEVELOPMENT_COMPLETE",
        "research_question": "Does adding approved passenger or downstream exposure to P^D change Stage-I screening while holding cohort, q and M3 tie-break fixed?",
        "estimand": "stage-local shortlist overlap, replacement and retained consequence against P^C",
        "views": {
            "DELAY": "P^D",
            "DELAY_PASSENGER": "P^D * expected_passengers_per_flight",
            "DELAY_DOWNSTREAM": "P^D * expected_downstream_exposure",
            "CONSEQUENCE": "P^C",
        },
        "node_count": len(nodes),
        "canonical_counts": {stage.value: len(canonical.get(stage, ())) for stage in STAGES},
        "summary_rows": summaries,
        "selected_rows": rows,
        "final_test_access_count": 0,
        "git_head": _git_head(),
    }
    payload["artifact_hash"] = content_id(payload)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "E1_SUMMARY.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "E1_SELECTED_ROWS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _git_head() -> str:
    import subprocess
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--node-limit", type=int, default=None)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = run(output_root=args.output_root, node_limit=args.node_limit, bootstrap_replicates=args.bootstrap_replicates)
    print(json.dumps({"status": result["status"], "node_count": result["node_count"], "output_root": str(args.output_root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
