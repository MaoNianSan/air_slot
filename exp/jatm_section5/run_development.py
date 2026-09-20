"""Run the JATM Section 4 capacity check and Section 5 Development study."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from exp.exp2.development_inputs import _observed
from model.M1.pipeline import M1Pipeline
from model.M1.state_representation import (
    build_joint_representation,
    build_marginal_representation,
    build_point_representation,
)
from model.M2.comparison_support import (
    PRIMARY_AGGREGATION_VIEW,
    delay_priority_signal,
    phi_c,
)
from model.common.decision_contracts import (
    ConsequenceScenario,
    ConsequenceScenarioSet,
    StateRepresentationSpec,
    TemporalKind,
    UncertaintyKind,
    WEIGHT_TOLERANCE,
)
from model.common.enums import OperationalStage, SupportState
from model.common.identity import content_id
from model.PRE.decision_environment import action_stage_class
from validation.v2_phase5.common import (
    CURRENT_CHECKPOINT,
    H16_CHECKPOINT,
    PHASE_DIR,
    chain_id_for_episode,
    comparison_support_for,
    consequence_set,
    expected_cu_for_support,
    load_authorities,
    load_development_bridge,
    load_tail_continuations,
    representation_spec,
    state_set_from_m1_scenarios,
)
from validation.v2_phase5.families import build_consequence_service

from .attention_value import (
    attention_domain_rows,
    attention_row,
    candidate,
    overall_objective,
    select_and_evaluate,
)
from .boundary import boundary_rows
from .cohorts import canonical_stage_cohort
from .contracts import (
    STAGE1_ACTIONABLE_STAGES,
    AttentionStageResult,
    RepresentationNode,
)
from .information_value import information_value_main
from .recovery_value import (
    prepare_reference_recovery,
    recovery_atomic_rows,
    severity_recoverability_rows,
    severity_summary,
    stage_recovery_summary,
)
from .reporting import write_json, write_report
from .robustness import run_robustness


ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_ROOT = ROOT / "artifacts" / "experiment" / "jatm_section5" / "development"
ARCHIVE_ROOT = ROOT / "artifacts" / "experiment" / "jatm_section5" / "archive"
Q_GRID: tuple[float, ...] = (0.05, 0.10, 0.20, 0.30)
NOMINAL_Q = 0.10
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260906
SECTION5_PRIMARY_MODEL = "H16_FROZEN_PRIMARY"
STAGES: tuple[OperationalStage, ...] = (
    OperationalStage.PRE_IB,
    OperationalStage.POST_IB_PRE_OB,
    OperationalStage.POST_OB_PRE_TO,
    OperationalStage.COMPLETED,
)
COMPONENT_KEYS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


def _domain_vector(expected: Mapping[str, float]) -> dict[str, float]:
    return {
        "F": (
            float(expected["F_continuity"])
            + float(expected["F_execution"])
            + float(expected["F_propagation"])
        )
        / 3.0,
        "P": (
            float(expected["P_time"])
            + float(expected["P_itinerary"])
            + float(expected["P_service"])
        )
        / 3.0,
        "R": float(expected["R_operating"]),
    }


def _abstaining_consequence_set(
    state_set,
    *,
    registry_id: str,
    registry_hash: str,
) -> ConsequenceScenarioSet:
    return ConsequenceScenarioSet(
        episode_id=state_set.episode_id,
        chain_id=state_set.chain_id,
        node_id=state_set.node_id,
        stage=state_set.stage,
        representation=state_set.representation,
        registry_id=registry_id,
        registry_hash=registry_hash,
        scenarios=tuple(
            ConsequenceScenario(
                scenario_id=scenario.scenario_id,
                scenario_weight=scenario.scenario_weight,
                support=SupportState.ABSTAIN,
            )
            for scenario in state_set.scenarios
        ),
        support=SupportState.SUPPORTED,
    )


def _schedule_sobt_minutes(state) -> float:
    schedule = state.successor_state.get("schedule_reference")
    value = None if schedule is None else schedule.value
    scheduled = None if not isinstance(value, dict) else value.get(
        "scheduled_departure_utc"
    )
    if scheduled is None:
        raise RuntimeError("JATM_SECTION5_SCHEDULED_DEPARTURE_MISSING")
    decision_time = state.decision_node.decision_time
    if isinstance(scheduled, str):
        scheduled = datetime.fromisoformat(scheduled)
    return float((scheduled - decision_time).total_seconds() / 60.0)


def _representation_specs() -> dict[str, StateRepresentationSpec]:
    return {
        "HISTORY_JOINT": representation_spec(
            TemporalKind.HISTORY, UncertaintyKind.JOINT, history_capacity=16
        ),
        "CURRENT_JOINT": representation_spec(
            TemporalKind.CURRENT, UncertaintyKind.JOINT
        ),
        "HISTORY_POINT": representation_spec(
            TemporalKind.HISTORY, UncertaintyKind.POINT, history_capacity=16
        ),
        "HISTORY_MARGINAL": representation_spec(
            TemporalKind.HISTORY,
            UncertaintyKind.MARGINAL,
            history_capacity=16,
        ),
    }


def _build_nodes(*, authorities, bridge, tails, layer) -> tuple[RepresentationNode, ...]:
    history_pipeline = M1Pipeline.load(H16_CHECKPOINT)
    current_pipeline = M1Pipeline.load(CURRENT_CHECKPOINT)
    history_pipeline.tail_continuations = dict(tails)
    current_pipeline.tail_continuations = dict(tails)
    current_rows = {
        row.decision_node_id: row
        for row in bridge["cache"].partition(
            "development", representation="CURRENT"
        )
    }
    specs = _representation_specs()
    nodes: list[RepresentationNode] = []
    for example, episode, prefix in bridge["rows"]:
        state = prefix[-1]
        decision_node = state.decision_node
        node_id = decision_node.decision_node_id
        current_source = current_rows.get(example.decision_node_id)
        if current_source is None:
            raise RuntimeError(
                f"JATM_SECTION5_CURRENT_ROW_MISSING:{example.decision_node_id}"
            )
        observed = _observed(state, bridge["taxi_reference"])
        history_scenarios = history_pipeline.sample_from_pre(
            state,
            example.values.unsqueeze(0),
            torch.tensor([len(example.values)]),
            observed=observed,
            count=64,
            seed=int(authorities.h16_manifest["training_seed"]),
            taxi_reference=bridge["taxi_reference"],
            tail_continuations=tails,
        )
        current_scenarios = current_pipeline.sample_from_pre(
            state,
            current_source.values.unsqueeze(0),
            torch.tensor([len(current_source.values)]),
            observed=observed,
            count=64,
            seed=int(authorities.current_manifest["training_seed"]),
            taxi_reference=bridge["taxi_reference"],
            tail_continuations=tails,
        )
        history_joint = state_set_from_m1_scenarios(
            history_scenarios,
            episode_id=decision_node.episode_id,
            chain_id=chain_id_for_episode(episode.episode),
            node_id=node_id,
            stage=decision_node.operational_stage,
            representation=specs["HISTORY_JOINT"],
        )
        current_joint = state_set_from_m1_scenarios(
            current_scenarios,
            episode_id=decision_node.episode_id,
            chain_id=chain_id_for_episode(episode.episode),
            node_id=node_id,
            stage=decision_node.operational_stage,
            representation=specs["CURRENT_JOINT"],
        )
        state_sets = {
            "HISTORY_JOINT": build_joint_representation(history_joint),
            "CURRENT_JOINT": current_joint,
            "HISTORY_POINT": build_point_representation(history_joint),
            "HISTORY_MARGINAL": build_marginal_representation(history_joint),
        }
        consequence_sets = {}
        supports = {}
        support_full = {}
        delay_scores: dict[str, float | None] = {}
        consequence_scores: dict[str, float | None] = {}
        domain_scores: dict[str, Mapping[str, float] | None] = {}
        component_scores: dict[str, Mapping[str, float] | None] = {}
        for representation, state_set in state_sets.items():
            if node_id in layer.bindings:
                consequences = consequence_set(layer.service, state_set)
            else:
                consequences = _abstaining_consequence_set(
                    state_set,
                    registry_id=layer.service.registry_id,
                    registry_hash=layer.service.registry_hash,
                )
            support = comparison_support_for(state_set, consequences)
            consequence_sets[representation] = consequences
            supports[representation] = support
            support_full[representation] = bool(
                support.included
                and abs(float(support.supported_mass) - 1.0) <= WEIGHT_TOLERANCE
            )
            if support.included:
                expected = expected_cu_for_support(consequences, support)
                delay = delay_priority_signal(state_set, support).score
                delay_scores[representation] = None if delay is None else float(delay)
                consequence_scores[representation] = float(phi_c(expected))
                domain_scores[representation] = _domain_vector(expected)
                component_scores[representation] = {
                    key: float(value) for key, value in expected.items()
                }
            else:
                delay_scores[representation] = None
                consequence_scores[representation] = None
                domain_scores[representation] = None
                component_scores[representation] = None
        nodes.append(
            RepresentationNode(
                episode_id=decision_node.episode_id,
                chain_id=chain_id_for_episode(episode.episode),
                node_id=node_id,
                stage=decision_node.operational_stage,
                decision_time=decision_node.decision_time,
                sobt_minutes=_schedule_sobt_minutes(state),
                state_sets=state_sets,
                consequence_sets=consequence_sets,
                supports=supports,
                support_full=support_full,
                delay_scores=delay_scores,
                consequence_scores=consequence_scores,
                domain_scores=domain_scores,
                component_scores=component_scores,
            )
        )
    return tuple(nodes)


def _reference_eligible(node: RepresentationNode) -> bool:
    support = node.support("HISTORY_JOINT")
    return bool(
        support.included
        and node.delay_scores["HISTORY_JOINT"] is not None
        and node.consequence_scores["HISTORY_JOINT"] is not None
        and node.domain_scores["HISTORY_JOINT"] is not None
    )


def _clone_for_bootstrap(
    node: RepresentationNode,
    *,
    instance: int,
    replicate: int,
) -> RepresentationNode:
    suffix = f"::BOOT{int(instance)}:{int(replicate)}"
    return RepresentationNode(
        episode_id=node.episode_id + suffix,
        chain_id=node.chain_id + suffix,
        node_id=node.node_id + suffix,
        stage=node.stage,
        decision_time=node.decision_time,
        sobt_minutes=node.sobt_minutes,
        state_sets=node.state_sets,
        consequence_sets=node.consequence_sets,
        supports=node.supports,
        support_full=node.support_full,
        delay_scores=node.delay_scores,
        consequence_scores=node.consequence_scores,
        domain_scores=node.domain_scores,
        component_scores=node.component_scores,
    )


def _materialized_stages(nodes: Sequence[RepresentationNode]) -> tuple[OperationalStage, ...]:
    present = {node.stage for node in nodes}
    ordered = [stage for stage in STAGES if stage in present]
    ordered.extend(sorted(present - set(ordered), key=lambda value: value.value))
    return tuple(ordered)


def _canonicalize(
    nodes: Sequence[RepresentationNode],
    *,
    stages: Sequence[OperationalStage] | None = None,
) -> dict[OperationalStage, tuple]:
    canonical_stages = (
        tuple(stages) if stages is not None else _materialized_stages(nodes)
    )
    output = {}
    for stage in canonical_stages:
        matching = tuple(node for node in nodes if node.stage is stage)
        output[stage] = canonical_stage_cohort(
            matching,
            stage=stage,
            eligibility=_reference_eligible,
        )
    return output


def _canonical_selection(
    canonical_rows: Sequence,
    *,
    q: float,
) -> AttentionStageResult | None:
    if not canonical_rows:
        return None
    canonical_nodes = tuple(row.node for row in canonical_rows)
    candidates = [
        item
        for row in canonical_rows
        for item in (candidate(row.node),)
        if item is not None
    ]
    return select_and_evaluate(
        candidates,
        q=q,
        cohort_id=f"PRIMARY_{action_stage_class(canonical_nodes[0].stage)}",
        canonical_nodes=canonical_nodes,
    )


def _attention_bootstrap(
    raw_by_stage: Mapping[OperationalStage, Sequence[RepresentationNode]],
    *,
    q_grid: Sequence[float],
    seed: int,
    replicates: int,
) -> dict[tuple[str, float], np.ndarray]:
    episodes = sorted({row.episode_id for rows in raw_by_stage.values() for row in rows})
    values = {
        (stage_class, float(q)): np.full(int(replicates), np.nan, dtype=float)
        for q in q_grid
        for stage_class in ("PRE", "TURN", "OVERALL")
    }
    by_episode = {
        stage: {
            episode: tuple(row for row in rows if row.episode_id == episode)
            for episode in episodes
        }
        for stage, rows in raw_by_stage.items()
    }
    rng = np.random.default_rng(int(seed))
    for replicate in range(int(replicates)):
        draw = rng.integers(0, len(episodes), size=len(episodes))
        sampled_by_stage: dict[OperationalStage, list[RepresentationNode]] = {
            stage: [] for stage in raw_by_stage
        }
        for stage in raw_by_stage:
            sampled = sampled_by_stage[stage]
            for instance, index in enumerate(draw):
                for row in by_episode.get(stage, {}).get(episodes[int(index)], ()):
                    sampled.append(
                        _clone_for_bootstrap(
                            row, instance=instance, replicate=replicate
                        )
                    )
        canonical = _canonicalize(
            [row for rows in sampled_by_stage.values() for row in rows],
            stages=tuple(raw_by_stage),
        )
        for q in q_grid:
            stage_results: list[AttentionStageResult] = []
            for stage in STAGE1_ACTIONABLE_STAGES:
                if stage not in canonical:
                    continue
                result = _canonical_selection(canonical[stage], q=q)
                if result is None:
                    continue
                stage_results.append(result)
                values[(action_stage_class(stage), float(q))][replicate] = (
                    float("nan")
                    if result.evaluation.L_att is None
                    else float(result.evaluation.L_att)
                )
            overall = overall_objective(stage_results)
            values[("OVERALL", float(q))][replicate] = (
                float("nan")
                if overall["L_att_overall"] is None
                else float(overall["L_att_overall"])
            )
    return values


def _percentile(values: np.ndarray) -> tuple[float | None, float | None]:
    clean = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if clean.size == 0:
        return None, None
    return float(np.quantile(clean, 0.025)), float(np.quantile(clean, 0.975))


def _component_rows_for_q(
    result: AttentionStageResult,
    *,
    q: float,
    nodes_by_id: Mapping[str, RepresentationNode],
) -> list[dict[str, object]]:
    if result.stage not in STAGE1_ACTIONABLE_STAGES:
        raise RuntimeError("JATM_SECTION5_DOMAIN_NON_ACTIONABLE_STAGE")
    reference_ids = set(result.evaluation.reference_shortlist)
    comparator_ids = set(result.evaluation.comparator_shortlist)
    rows: list[dict[str, object]] = []
    for domain in ("F", "P", "R", *COMPONENT_KEYS):
        reference_total = 0.0
        comparator_total = 0.0
        for node_id in result.evaluation.candidate_node_ids:
            node = nodes_by_id[node_id]
            scores = (
                node.domain_scores["HISTORY_JOINT"]
                if domain in {"F", "P", "R"}
                else node.component_scores["HISTORY_JOINT"]
            )
            if scores is None:
                continue
            value = float(scores[domain])
            if node_id in reference_ids:
                reference_total += value
            if node_id in comparator_ids:
                comparator_total += value
        rows.append(
            {
                "stage": action_stage_class(result.stage),
                "q": float(q),
                "domain": domain,
                "A_reference": reference_total,
                "A_comparator": comparator_total,
                "value_retained": (
                    None if reference_total <= 0.0 else comparator_total / reference_total
                ),
            }
        )
    return rows


def _write_frame(path: Path, rows: Sequence[Mapping[str, object]], *, parquet: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if parquet:
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def _reuse_section4() -> dict[str, object]:
    selection_path = ROOT / "artifacts" / "diagnostics" / "jatm_section4" / "h_capacity" / "H_CAPACITY_SELECTION.json"
    model_path = ROOT / "artifacts" / "diagnostics" / "jatm_section4" / "h_capacity" / "H_CAPACITY_MODEL_PERFORMANCE.csv"
    if not selection_path.is_file() or not model_path.is_file():
        raise RuntimeError("JATM_SECTION5_SECTION4_REUSE_ARTIFACTS_MISSING")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("status") != "COMPLETE":
        raise RuntimeError("JATM_SECTION5_SECTION4_REUSE_STATUS_INVALID")
    if list(selection.get("h_capacity_grid", ())) != [8, 16, 32]:
        raise RuntimeError("JATM_SECTION5_SECTION4_REUSE_GRID_INVALID")
    if int(selection.get("final_test_access_count", -1)) != 0:
        raise RuntimeError("JATM_SECTION5_SECTION4_REUSE_FINAL_TEST_ACCESS")
    frame = pd.read_csv(model_path)
    if set(frame["history_capacity"].astype(int)) != {8, 16, 32}:
        raise RuntimeError("JATM_SECTION5_SECTION4_REUSE_MODEL_ROWS_INVALID")
    return {
        "status": "REUSED_NOT_RERUN",
        "selection": selection,
        "model_performance": frame.to_dict(orient="records"),
        "selection_path": str(selection_path),
        "model_path": str(model_path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _archive_development(output_root: Path) -> Path | None:
    if not output_root.is_dir():
        return None
    target = ARCHIVE_ROOT / "pre_stage_matched_20260919"
    if target.exists():
        manifest_path = target / "ARCHIVE_MANIFEST.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"JATM_SECTION5_ARCHIVE_MANIFEST_MISSING:{target}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("archive_id") != "PRE_STAGE_MATCHED_DEVELOPMENT_BASELINE":
            raise RuntimeError(f"JATM_SECTION5_ARCHIVE_ID_MISMATCH:{target}")
        expected = {
            str(entry["path"]).replace("\\", "/"): str(entry["sha256"])
            for entry in manifest.get("files", ())
        }
        if not expected:
            raise RuntimeError(f"JATM_SECTION5_ARCHIVE_MANIFEST_EMPTY:{target}")
        for relative, digest in expected.items():
            archived = target / relative
            if not archived.is_file() or _sha256(archived) != digest:
                raise RuntimeError(
                    f"JATM_SECTION5_ARCHIVE_INTEGRITY_FAILURE:{relative}"
                )
        return target
    shutil.copytree(output_root, target)
    files = [
        {
            "path": str(path.relative_to(target)).replace("\\", "/"),
            "sha256": _sha256(path),
        }
        for path in sorted(target.rglob("*"))
        if path.is_file()
    ]
    manifest = {
        "archive_id": "PRE_STAGE_MATCHED_DEVELOPMENT_BASELINE",
        "source_root": str(output_root),
        "archive_root": str(target),
        "superseded_scientific_semantics": "PREVIOUS_DEVELOPMENT_SCREENING_SEMANTICS",
        "file_count": len(files),
        "files": files,
    }
    (target / "ARCHIVE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def _section4_payload(section4: Mapping[str, object]) -> dict[str, object]:
    selection = section4.get("selection", {})
    return {
        "status": "REUSED_NOT_RERUN",
        "selected_history_capacity": selection.get("selected_history_capacity"),
        "h_capacity_grid": selection.get("h_capacity_grid", [8, 16, 32]),
        "active_model_mutation": "NONE",
        "downstream_execution": "NONE",
    }


def _information_value_payload(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_component = {str(row["information_component"]): row for row in rows}
    cross_state = by_component["CROSS_STATE_DEPENDENCE"]
    marginal_increment = by_component["MARGINAL_UNCERTAINTY"]
    return {
        "components": [row["information_component"] for row in rows],
        "paired_increments": [marginal_increment],
        "metric_aliases": {
            "CROSS_STATE_DEPENDENCE_L_ATT": {
                "information_component": "CROSS_STATE_DEPENDENCE",
                "comparator": "HISTORY_MARGINAL",
                "reference": "HISTORY_JOINT",
                "definition": "L_HISTORY_MARGINAL - L_HISTORY_JOINT",
                "value": cross_state["L_att"],
                "ci_low": cross_state["L_att_ci_low"],
                "ci_high": cross_state["L_att_ci_high"],
            },
            "CROSS_STATE_DEPENDENCE_L_REC": {
                "information_component": "CROSS_STATE_DEPENDENCE",
                "comparator": "HISTORY_MARGINAL",
                "reference": "HISTORY_JOINT",
                "definition": "L_HISTORY_MARGINAL - L_HISTORY_JOINT",
                "value": cross_state["L_rec"],
                "ci_low": cross_state["L_rec_ci_low"],
                "ci_high": cross_state["L_rec_ci_high"],
            },
            "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT": {
                "information_component": "MARGINAL_UNCERTAINTY",
                "comparator": "POINT_MINUS_MARGINAL",
                "reference": "HISTORY_POINT_MINUS_HISTORY_MARGINAL",
                "definition": "L_HISTORY_POINT - L_HISTORY_MARGINAL",
                "paired_bootstrap": True,
                "value": marginal_increment["L_att"],
                "ci_low": marginal_increment["L_att_ci_low"],
                "ci_high": marginal_increment["L_att_ci_high"],
            },
            "MARGINAL_UNCERTAINTY_INCREMENT_L_REC": {
                "information_component": "MARGINAL_UNCERTAINTY",
                "comparator": "POINT_MINUS_MARGINAL",
                "reference": "HISTORY_POINT_MINUS_HISTORY_MARGINAL",
                "definition": "L_HISTORY_POINT - L_HISTORY_MARGINAL",
                "paired_bootstrap": True,
                "value": marginal_increment["L_rec"],
                "ci_low": marginal_increment["L_rec_ci_low"],
                "ci_high": marginal_increment["L_rec_ci_high"],
            },
        },
    }


def run_development(
    *,
    run_section4: bool = False,
    node_limit: int | None = None,
    bootstrap_replicates: int = BOOTSTRAP_REPLICATES,
    output_root: Path = DEVELOPMENT_ROOT,
) -> dict[str, object]:
    output_root = Path(output_root).resolve()
    if output_root != DEVELOPMENT_ROOT.resolve():
        raise RuntimeError("JATM_SECTION5_OUTPUT_ROOT_MUST_BE_DEVELOPMENT_NAMESPACE")
    if run_section4:
        raise RuntimeError("JATM_SECTION5_SECTION4_RERUN_FORBIDDEN")
    _archive_development(output_root)
    section4 = _reuse_section4()

    authorities = load_authorities()
    bridge = load_development_bridge()
    tails = load_tail_continuations()
    layer = build_consequence_service(
        authorities=authorities,
        bridge=bridge,
        output_dir=output_root / "materialization",
    )
    nodes = _build_nodes(
        authorities=authorities, bridge=bridge, tails=tails, layer=layer
    )
    if node_limit is not None:
        nodes = nodes[: int(node_limit)]
    canonical = _canonicalize(nodes)
    canonical_counts = {
        action_stage_class(stage): len(canonical[stage]) for stage in canonical
    }
    stage1_canonical_counts = {
        action_stage_class(stage): len(canonical[stage])
        for stage in STAGE1_ACTIONABLE_STAGES
        if stage in canonical
    }

    stage_results: dict[float, dict[str, AttentionStageResult]] = {}
    stage_q_rows: list[dict[str, object]] = []
    domain_rows: list[dict[str, object]] = []
    boundary_rows_all: list[dict[str, object]] = []
    for q in Q_GRID:
        stage_results[float(q)] = {}
        for stage in STAGE1_ACTIONABLE_STAGES:
            if stage not in canonical:
                continue
            result = _canonical_selection(canonical[stage], q=q)
            if result is None:
                continue
            stage_results[float(q)][action_stage_class(stage)] = result
            stage_q_rows.append(attention_row(result, q=q))
        q_results = list(stage_results[float(q)].values())
        overall = overall_objective(q_results)
        stage_q_rows.append(
            {
                "stage": "OVERALL",
                "q": float(q),
                "N": sum(len(item.candidates) for item in q_results),
                "K": sum(item.reference_decision.k for item in q_results),
                "canonical_stage_node_count": sum(
                    len(item.canonical_node_ids) for item in q_results
                ),
                "eligible_candidate_count": sum(
                    len(item.eligible_candidate_ids) for item in q_results
                ),
                "abstaining_node_count": sum(
                    len(item.abstaining_node_ids) for item in q_results
                ),
                "A_C": overall["A_C_overall"],
                "A_D": overall["A_D_overall"],
                "value_retained": (
                    None
                    if overall["A_C_overall"] in (None, 0.0)
                    else float(overall["A_D_overall"]) / float(overall["A_C_overall"])
                ),
                "L_att": overall["L_att_overall"],
                "overlap_count": sum(item.evaluation.overlap_count for item in q_results),
                "reassigned_count": sum(len(item.evaluation.displaced) for item in q_results),
                "reassigned_share": (
                    None
                    if not q_results
                    else sum(len(item.evaluation.displaced) for item in q_results)
                    / sum(len(item.evaluation.reference_shortlist) for item in q_results)
                ),
                "F_value_retained": None,
                "P_value_retained": None,
                "R_value_retained": None,
            }
        )
    nodes_by_id = {node.node_id: node for node in nodes}
    for q, by_stage in stage_results.items():
        for result in by_stage.values():
            domain_rows.extend(
                _component_rows_for_q(result, q=q, nodes_by_id=nodes_by_id)
            )
            if abs(float(q) - NOMINAL_Q) <= 1e-12:
                boundary_rows_all.extend(boundary_rows(result))

    attention_main = [
        row
        for row in stage_q_rows
        if str(row["stage"]) in {"PRE", "TURN"}
        and abs(float(row["q"]) - NOMINAL_Q) <= 1e-12
    ]
    bootstrap_values = _attention_bootstrap(
        {
            stage: tuple(node for node in nodes if node.stage is stage)
            for stage in canonical
        },
        q_grid=Q_GRID,
        seed=BOOTSTRAP_SEED,
        replicates=int(bootstrap_replicates),
    )
    bootstrap_rows: list[dict[str, object]] = []
    for (stage, q), values in sorted(bootstrap_values.items()):
        estimate_row = next(
            (
                row
                for row in stage_q_rows
                if str(row["stage"]) == stage and abs(float(row["q"]) - q) <= 1e-12
            ),
            None,
        )
        low, high = _percentile(values)
        bootstrap_rows.append(
            {
                "stage": stage,
                "q": q,
                "estimate": None if estimate_row is None else estimate_row["L_att"],
                "ci_low": low,
                "ci_high": high,
                "replicate_count": int(np.isfinite(values).sum()),
            }
        )

    nominal = stage_results[NOMINAL_Q]
    source_shortlists = {
        OperationalStage.PRE_IB: tuple(
            item.node_id
            for item in nominal.get("PRE", None).reference_decision.entries
            if item.selected
        )
        if nominal.get("PRE") is not None
        else (),
        OperationalStage.POST_IB_PRE_OB: tuple(
            item.node_id
            for item in nominal.get("TURN", None).reference_decision.entries
            if item.selected
        )
        if nominal.get("TURN") is not None
        else (),
    }
    headroom_payload = json.loads(
        (PHASE_DIR / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json").read_text(
            encoding="utf-8"
        )
    )
    from model.common.decision_contracts import HeadroomSummary

    headroom = HeadroomSummary.model_validate(
        headroom_payload["factual_headroom"]["headroom_summary"]
    )
    reference_cohort = prepare_reference_recovery(
        tuple(
            row.node
            for stage in STAGE1_ACTIONABLE_STAGES
            for row in canonical.get(stage, ())
        ),
        source_shortlists=source_shortlists,
        service=layer.service,
        headroom=headroom,
    )
    recovery_rows = recovery_atomic_rows(reference_cohort)
    recovery_main = stage_recovery_summary(recovery_rows)
    severity_rows = severity_recoverability_rows(recovery_rows)
    severity_summary_rows = severity_summary(severity_rows)

    information_nodes = [
        row.node
        for stage in canonical
        for row in canonical[stage]
        if row.eligible
        and all(
            row.node.support(representation).included
            for representation in (
                "HISTORY_JOINT",
                "CURRENT_JOINT",
                "HISTORY_POINT",
                "HISTORY_MARGINAL",
            )
        )
    ]
    information_rows, information_diagnostics, information_bootstrap = (
        information_value_main(
            information_nodes,
            q=NOMINAL_Q,
            reference_cohort=reference_cohort,
            service=layer.service,
            headroom=headroom,
            seed=BOOTSTRAP_SEED,
            replicates=int(bootstrap_replicates),
        )
    )
    robustness_rows = run_robustness(
        reference_cohort,
        service=layer.service,
        nominal_headroom=headroom,
    )

    attention_dir = output_root / "attention"
    recovery_dir = output_root / "recovery"
    information_dir = output_root / "information"
    robustness_dir = output_root / "robustness"
    _write_frame(attention_dir / "ATTENTION_VALUE_MAIN.csv", attention_main)
    _write_frame(attention_dir / "ATTENTION_STAGE_Q.csv", stage_q_rows)
    _write_frame(
        attention_dir / "ATTENTION_DOMAIN_DECOMPOSITION.csv", domain_rows
    )
    _write_frame(attention_dir / "ATTENTION_BOUNDARY.csv", boundary_rows_all)
    _write_frame(attention_dir / "ATTENTION_BOOTSTRAP.csv", bootstrap_rows)
    _write_frame(
        recovery_dir / "RECOVERY_VALUE_ROWS.parquet",
        recovery_rows,
        parquet=True,
    )
    _write_frame(recovery_dir / "RECOVERY_VALUE_MAIN.csv", recovery_main)
    _write_frame(
        recovery_dir / "SEVERITY_RECOVERABILITY.csv", severity_rows
    )
    _write_frame(
        recovery_dir / "SEVERITY_RECOVERABILITY_SUMMARY.csv",
        severity_summary_rows,
    )
    _write_frame(
        information_dir / "INFORMATION_VALUE_MAIN.csv", information_rows
    )
    _write_frame(
        information_dir / "INFORMATION_DECISION_DIAGNOSTICS.csv",
        information_diagnostics,
    )
    _write_frame(
        information_dir / "INFORMATION_INCREMENT_BOOTSTRAP.csv",
        information_bootstrap,
    )
    _write_frame(
        robustness_dir / "ROBUSTNESS_RECOVERY.csv", robustness_rows
    )

    payload: dict[str, object] = {
        "schema_version": "JATM_SECTION5_DEVELOPMENT_V1",
        "scientific_patch": "STAGE_MATCHED_PRE_TURN_SCREENING",
        "supersedes": "PREVIOUS_DEVELOPMENT_SCREENING_SEMANTICS",
        "stage1_overall_aggregation": "PRE_TURN_OBJECTIVE_THEN_NORMALIZE",
        "scientific_definition_changed": "STAGE1_EMPIRICAL_ORCHESTRATION_PATCH_ONLY",
        "section4_h_capacity_status": "REUSED_NOT_RERUN",
        "h_capacity_status": {
            "H8": "REUSED_NOT_RERUN",
            "H16": "REUSED_NOT_RERUN",
            "H32": "REUSED_NOT_RERUN",
        },
        "selected_history_capacity": section4.get("selection", {}).get(
            "selected_history_capacity"
        ),
        "section5_primary_model": SECTION5_PRIMARY_MODEL,
        "canonicalization_before_support": "PASS",
        "stage2_sobt_coordinate": "NODE_RELATIVE_SOBT",
        "h_capacity_downstream_execution": "NONE",
        "h_capacity_active_model_mutation": "NONE",
        "attention_value": {
            "stage1_stages": ["PRE", "TURN"],
            "materialized_rolling_node_count": len(nodes),
            "canonical_counts": canonical_counts,
            "stage1_canonical_counts": stage1_canonical_counts,
            "stage1_eligible_counts": {
                stage: len(
                    next(
                        item
                        for item in stage_results[NOMINAL_Q].values()
                        if action_stage_class(item.stage) == stage
                    ).eligible_candidate_ids
                )
                for stage in ("PRE", "TURN")
                if any(
                    action_stage_class(item.stage) == stage
                    for item in stage_results[NOMINAL_Q].values()
                )
            },
            "q_grid": list(Q_GRID),
            "nominal_q": NOMINAL_Q,
            "overall": {
                "L_att_overall": next(
                    (
                        row["L_att"]
                        for row in stage_q_rows
                        if row["stage"] == "OVERALL"
                        and abs(float(row["q"]) - NOMINAL_Q) <= 1e-12
                    ),
                    None,
                )
            },
            "bootstrap_status": "COMPLETE",
        },
        "recovery_value": {
            "R_star_size": len(reference_cohort.nodes),
            "shortlist_node_ids_by_stage": {
                key: list(value)
                for key, value in reference_cohort.shortlist_node_ids_by_stage.items()
            },
            "stage2_actionable_node_ids_by_stage": {
                key: list(value)
                for key, value in reference_cohort.stage2_actionable_node_ids_by_stage.items()
            },
            "stage2_actionable_node_ids_flattened": list(
                reference_cohort.stage2_actionable_node_ids_flattened
            ),
            "flattened_union_semantics": reference_cohort.flattened_union_semantics,
            "stage_counts": dict(
                pd.DataFrame(recovery_rows)["stage"].value_counts().to_dict()
            )
            if recovery_rows
            else {},
            "stage_summary": recovery_main,
            "severity_recoverability_status": "COMPLETE",
        },
        "information_value": _information_value_payload(information_rows),
        "robustness": {"row_count": len(robustness_rows)},
        "section4": _section4_payload(section4),
        "final_test_access_count": 0,
        "model_definition_provenance": {
            "M1_DEFINITION_CHANGED": "NO",
            "M2_DEFINITION_CHANGED": "NO",
            "M3_SELECTOR_DEFINITION_CHANGED": "NO",
            "M3_STAGE2_DEFINITION_CHANGED": "NO",
            "M4_LOSS_DEFINITION_CHANGED": "NO",
            "SCIENTIFIC_ORCHESTRATION_CHANGED": "YES",
            "SCIENTIFIC_ORCHESTRATION_PATCH": (
                "STAGE_MATCHED_PRE_TURN_SCREENING"
            ),
        },
        "development_ready_for_freeze": "YES",
        "final_test_ready_to_open": "YES",
        "final_test_complete": "NO",
        "final_test_readiness": "DEVELOPMENT_READY_FOR_FREEZE",
        "blockers": [],
    }
    payload["artifact_hash"] = content_id(payload)
    write_report(output_root / "report", payload)
    write_json(output_root / "report" / "JATM_SECTION5_MANIFEST.json", payload)
    return {
        "status": "COMPLETE",
        "output_root": str(output_root),
        "payload": payload,
        "node_count": len(nodes),
    }


def main() -> int:
    result = run_development()
    print(
        {
            "status": result["status"],
            "output_root": result["output_root"],
            "node_count": result["node_count"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
