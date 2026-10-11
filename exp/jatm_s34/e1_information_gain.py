"""E1 Development screening views on the frozen Section 5 cohort.

The runner reuses the Section 5 node builder and the model-owned Stage-I
selector. Exposure factors are read back from the native M2 components
(``P_time`` and ``F_propagation``) paired with the corresponding M1 ``D_TO``;
no second consequence formula is implemented here.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import numpy as np

from exp.jatm_section5.run_development import (
    _build_nodes,
    _canonicalize,
    _reference_eligible,
)
from model.M3.stage1 import select_paired_attention
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


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


def _exposure_factors(node, binding) -> tuple[tuple[float, float] | None, dict]:
    """Resolve direct M2 references and verify the native algebraic identity."""

    if binding is None:
        return None, {"status": "ABSTAIN", "reason": "REFERENCE_BINDING_MISSING"}
    expected_pax = float(binding.expected_pax)
    expected_downstream = float(binding.downstream_exposure)
    state = {item.scenario_id: item for item in node.state("HISTORY_JOINT").scenarios}
    checks = []
    for scenario in node.consequences("HISTORY_JOINT").scenarios:
        m1 = state.get(scenario.scenario_id)
        native = scenario.native_components
        if m1 is None or m1.d_to_minutes is None or float(m1.d_to_minutes) <= 1e-12:
            continue
        d_to = float(m1.d_to_minutes)
        pax_ratio = float(native["P_time"]) / d_to
        downstream_ratio = float(native["F_propagation"]) / d_to
        checks.append(
            {
                "scenario_id": int(scenario.scenario_id),
                "d_to_minutes": d_to,
                "pax_ratio": pax_ratio,
                "downstream_ratio": downstream_ratio,
                "pax_abs_error": abs(pax_ratio - expected_pax),
                "downstream_abs_error": abs(downstream_ratio - expected_downstream),
            }
        )
    if not checks:
        return None, {"status": "ABSTAIN", "reason": "NO_POSITIVE_D_TO_SCENARIO", "checks": []}
    max_pax_error = max(item["pax_abs_error"] for item in checks)
    max_downstream_error = max(item["downstream_abs_error"] for item in checks)
    if max(max_pax_error, max_downstream_error) > 1e-6:
        raise ContractError(
            f"E1_EXPOSURE_REFERENCE_MISMATCH:{node.node_id}:{max_pax_error}:{max_downstream_error}"
        )
    return (expected_pax, expected_downstream), {
        "status": "PASS_DIRECT_REFERENCE_AND_NATIVE_IDENTITY",
        "expected_pax": expected_pax,
        "expected_downstream": expected_downstream,
        "max_pax_abs_error": max_pax_error,
        "max_downstream_abs_error": max_downstream_error,
        "checks": checks,
    }


def _select(view_signals, consequence_signals, *, q: float):
    comparator, reference = select_paired_attention(
        view_signals, consequence_signals, q=float(q)
    )
    selected_view = {entry.node_id for entry in comparator.entries if entry.selected}
    selected_ref = {entry.node_id for entry in reference.entries if entry.selected}
    by_id = {item.node_id: item for item in consequence_signals if item.score is not None}
    ref_value = sum(float(by_id[item].score) for item in selected_ref if item in by_id)
    retained = sum(float(by_id[item].score) for item in selected_view if item in by_id)
    gap = None if ref_value == 0.0 else ref_value - retained
    return {
        "k": int(comparator.k),
        "n": int(comparator.cohort_size),
        "abstain": int(sum(item.support is SupportState.ABSTAIN for item in view_signals)),
        "abstain_reasons": dict(
            Counter(reason for item in view_signals if item.support is SupportState.ABSTAIN for reason in item.reason_codes)
        ),
        "selected_view": sorted(selected_view),
        "selected_reference": sorted(selected_ref),
        "overlap": len(selected_view & selected_ref),
        "replacement": len(selected_view - selected_ref),
        "retained_consequence": (None if ref_value == 0 else retained / ref_value),
        "absolute_consequence_gap": gap,
        "attention_loss": (None if ref_value == 0 else gap / ref_value),
        "reference_consequence_sum": ref_value,
        "retained_consequence_sum": retained,
        "valid_reference_denominator": ref_value > 0.0,
    }


def _clone_instance(node, *, replicate: int, occurrence: int):
    suffix = f"::BOOT{int(replicate)}:{int(occurrence)}"
    updates = {
        "episode_id": node.episode_id + suffix,
        "chain_id": node.chain_id + suffix,
        "node_id": node.node_id + suffix,
    }
    try:
        return replace(node, **updates)
    except TypeError:
        clone = copy.copy(node)
        for key, value in updates.items():
            setattr(clone, key, value)
        return clone


def _bootstrap(stage_nodes, *, view: str, q: float, factor_by_node: dict[str, tuple[float, float]], seed: int, replicates: int) -> dict:
    episodes = sorted({node.episode_id for node in stage_nodes})
    groups = {episode: tuple(node for node in stage_nodes if node.episode_id == episode) for episode in episodes}
    rng = np.random.default_rng(seed)
    metrics = {"overlap": [], "replacement": [], "retained_consequence": [], "absolute_consequence_gap": [], "attention_loss": []}
    for replicate in range(int(replicates)):
        draw = rng.choice(episodes, size=len(episodes), replace=True)
        rows = []
        for occurrence, episode in enumerate(draw):
            rows.extend(_clone_instance(node, replicate=replicate, occurrence=occurrence) for node in groups[episode])
        cloned_factors = {node.node_id: factor_by_node[node.node_id.split("::BOOT", 1)[0]] for node in rows}
        result = _summarize_stage(rows, view=view, q=q, factor_by_node=cloned_factors)
        for name in metrics:
            value = result.get(name)
            if value is not None:
                metrics[name].append(float(value))
    out = {"replicate_count": int(replicates), "seed": int(seed), "metrics": {}}
    for name, values in metrics.items():
        arr = np.asarray(values, dtype=float)
        if arr.size == 0:
            out["metrics"][name] = {"status": "NO_VALID_DENOMINATOR", "valid_replicates": 0}
        else:
            out["metrics"][name] = {
                "status": "PASS",
                "valid_replicates": int(arr.size),
                "ci_low": float(np.quantile(arr, 0.025)),
                "ci_high": float(np.quantile(arr, 0.975)),
            }
    return out


def _summarize_stage(nodes, *, view: str, q: float, factor_by_node: dict[str, tuple[float, float]]) -> dict:
    if not nodes:
        return {
            "status": "ABSTAIN_NO_CANDIDATES",
            "selected_view": [],
            "selected_reference": [],
            "overlap": None,
            "replacement": None,
            "retained_consequence": None,
            "absolute_consequence_gap": None,
            "attention_loss": None,
            "valid_reference_denominator": False,
            "view": view,
            "q": float(q),
        }
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
            pax, downstream = factor_by_node[node.node_id]
            factor = pax if view == "DELAY_PASSENGER" else downstream
            score = None if signal.score is None or factor is None else float(signal.score) * factor
            comparator.append(_typed_signal(node, score=score, signal_type=SignalKind.DELAY))
    return _select(comparator, consequence, q=q) | {"view": view, "q": float(q)}


def run(*, output_root: Path, node_limit: int | None = None, bootstrap_replicates: int = 2000, annual_context=None) -> dict:
    if annual_context is None:
        authorities = load_authorities()
        bridge = load_development_bridge()
        tails = load_tail_continuations()
        model_kwargs = {}
    else:
        authorities = annual_context["authorities"]
        bridge = annual_context["bridge"]
        tails = annual_context["tails"]
        model_kwargs = {
            "history_checkpoint": annual_context["history_checkpoint"],
            "current_checkpoint": annual_context["current_checkpoint"],
        }
    layer = build_consequence_service(authorities=authorities, bridge=bridge, output_dir=output_root / "materialization")
    nodes = list(_build_nodes(authorities=authorities, bridge=bridge, tails=tails, layer=layer, **model_kwargs))
    if node_limit is not None:
        nodes = nodes[: int(node_limit)]
    canonical = _canonicalize(nodes, stages=STAGES)
    factor_by_node: dict[str, tuple[float, float]] = {}
    factor_audit: dict[str, dict] = {}
    candidate_exclusions: Counter[str] = Counter()
    common_by_stage = {}
    for stage in STAGES:
        common = []
        for row in canonical.get(stage, ()):
            node = row.node
            if not _reference_eligible(node):
                candidate_exclusions["BASE_COMMON_SUPPORT_OR_SCORE"] += 1
                continue
            binding = layer.bindings.get(node.node_id)
            factors, audit = _exposure_factors(node, binding)
            factor_audit[node.node_id] = audit
            if factors is None:
                candidate_exclusions[audit.get("reason", "EXPOSURE_REFERENCE_UNAVAILABLE")] += 1
                continue
            factor_by_node[node.node_id] = factors
            common.append(node)
        common_by_stage[stage] = tuple(common)
    rows = []
    summaries = []
    for stage in STAGES:
        cohort = common_by_stage[stage]
        for q in Q_GRID:
            for view in VIEWS:
                result = _summarize_stage(cohort, view=view, q=q, factor_by_node=factor_by_node)
                result["stage"] = stage.value
                result["candidate_total"] = len(cohort)
                result["support_denominator"] = len(cohort)
                result["bootstrap_ci"] = _bootstrap(
                    cohort,
                    view=view,
                    q=q,
                    factor_by_node=factor_by_node,
                    seed=20261011 + int(q * 100) + list(STAGES).index(stage) * 1000 + list(VIEWS).index(view),
                    replicates=bootstrap_replicates,
                )
                summaries.append(result)
                for node_id in result["selected_view"]:
                    rows.append({"stage": stage.value, "q": q, "view": view, "node_id": node_id, "selected": True})
    by_key = {(row["stage"], row["q"], row["view"]): row for row in summaries}
    for stage in STAGES:
        for q in Q_GRID:
            baseline = by_key[(stage.value, float(q), "DELAY")]
            for view in VIEWS:
                row = by_key[(stage.value, float(q), view)]
                row["paired_increment_vs_delay"] = {
                    "overlap": (
                        None
                        if row["overlap"] is None or baseline["overlap"] is None
                        else row["overlap"] - baseline["overlap"]
                    ),
                    "replacement": (
                        None
                        if row["replacement"] is None or baseline["replacement"] is None
                        else row["replacement"] - baseline["replacement"]
                    ),
                    "retained_consequence": (
                        None
                        if row["retained_consequence"] is None or baseline["retained_consequence"] is None
                        else row["retained_consequence"] - baseline["retained_consequence"]
                    ),
                    "attention_loss": (
                        None
                        if row["attention_loss"] is None or baseline["attention_loss"] is None
                        else row["attention_loss"] - baseline["attention_loss"]
                    ),
                }
    payload = {
        "schema_version": "JATM_S34_E1_DEVELOPMENT_V2",
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
        "common_candidate_counts": {stage.value: len(common_by_stage[stage]) for stage in STAGES},
        "candidate_exclusions": dict(candidate_exclusions),
        "exposure_reference_audit": factor_audit,
        "source_artifact_hashes": {
            "reference_binding_audit": _sha256(output_root / "materialization" / "REFERENCE_BINDING_AUDIT.json")
            if (output_root / "materialization" / "REFERENCE_BINDING_AUDIT.json").is_file()
            else None,
        },
        "bootstrap": {"replicates": int(bootstrap_replicates), "cluster": "episode", "with_replacement": True, "seed_base": 20261011},
        "summary_rows": summaries,
        "selected_rows": rows,
        "final_test_access_count": 0,
        "git_head": _git_head(),
    }
    payload["artifact_hash"] = content_id(payload)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "E1_SUMMARY.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (output_root / "E1_SELECTED_ROWS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    chart_rows = [
        {
            key: row.get(key)
            for key in (
                "stage", "q", "view", "candidate_total", "support_denominator",
                "n", "k", "abstain", "overlap", "replacement",
                "retained_consequence", "absolute_consequence_gap", "attention_loss",
            )
        }
        for row in summaries
    ]
    (output_root / "E1_CHART_DATA.json").write_text(json.dumps(chart_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
