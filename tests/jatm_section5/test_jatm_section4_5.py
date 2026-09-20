"""Targeted tests for the JATM Section 4/5 Development refactor."""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from exp.jatm_section4 import h_capacity
from exp.jatm_section5 import information_value, run_development
from exp.jatm_section5 import recovery_value
from exp.jatm_section5.attention_value import (
    attention_domain_rows,
    attention_row,
    select_and_evaluate,
)
from exp.jatm_section5.bootstrap import (
    bootstrap_estimates,
    paired_information_increment_contrast,
)
from exp.jatm_section5.cohorts import (
    canonical_node_ids,
    canonical_stage_cohort,
)
from exp.jatm_section5.contracts import (
    AttentionCandidate,
    CanonicalStageRow,
    ReferenceRecoveryCohort,
    ReferenceRecoveryNode,
    RepresentationNode,
)
from exp.jatm_section5.information_value import (
    COMPONENTS,
    common_candidates,
    evaluate_component_attention,
)
from exp.jatm_section5.recovery_value import (
    comparator_recovery,
    recovery_atomic_rows,
    reference_recovery_cohort,
    transition_context,
)
from exp.jatm_section5.reporting import SECTION_MAPPING, render_report
from model.common.decision_contracts import (
    ComparisonSupport,
    HeadroomSummary,
    RecoveryDecision,
    SolverStatus,
    TypedStatus,
)
from model.common.enums import OperationalStage


def _support(episode_id: str, node_id: str, *, mass: float = 1.0) -> ComparisonSupport:
    included = mass >= 0.90
    return ComparisonSupport(
        episode_id=episode_id,
        chain_id=f"chain-{episode_id}",
        node_id=node_id,
        rule_id="M2_COMMON_SUPPORT_NOMINAL_0P90",
        estimand="JOINTLY_SUPPORTED_PRIORITY_COMPARISON",
        supported_mass=mass,
        supported_scenario_ids=(0,) if included else (),
        scenario_count_total=1,
        threshold=0.90,
        included=included,
        status=(
            TypedStatus.SUPPORTED
            if included
            else TypedStatus.ABSTAIN_NO_COMMON_SUPPORT
        ),
    )


def _headroom() -> HeadroomSummary:
    return HeadroomSummary(
        u_max=10.0,
        turnaround_lower_bound_q=41.0,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id="TEST",
        floor_to_minutes=5.0,
    )


def _recovery_decision(
    *,
    node_id: str,
    stage: OperationalStage = OperationalStage.PRE_IB,
    u_star: float = 5.0,
    j_zero: float = 2.0,
    j_star: float = 1.0,
) -> RecoveryDecision:
    return RecoveryDecision(
        episode_id=f"episode-{node_id}",
        chain_id=f"chain-{node_id}",
        node_id=node_id,
        representation_id="HISTORY_H16:JOINT",
        stage=stage,
        actionable_status=TypedStatus.SUPPORTED,
        headroom_summary=_headroom(),
        action_grid=(0.0, 5.0, 10.0),
        u_max=10.0,
        u_star=u_star,
        j_zero=j_zero,
        j_star=j_star,
        recoverable_value=j_zero - j_star,
        lambda_policy=0.25,
        solver_status=SolverStatus.EXACT_ENUMERATION,
    )


def _representation_node(
    node_id: str,
    *,
    stage: OperationalStage = OperationalStage.PRE_IB,
    reference_score: float = 10.0,
    comparator_scores: dict[str, float] | None = None,
    domain_scores: dict[str, float] | None = None,
) -> RepresentationNode:
    scores = {
        "HISTORY_JOINT": reference_score,
        "CURRENT_JOINT": reference_score,
        "HISTORY_POINT": reference_score,
        "HISTORY_MARGINAL": reference_score,
    }
    scores.update(comparator_scores or {})
    supports = {
        representation: _support(f"episode-{node_id}", node_id)
        for representation in scores
    }
    return RepresentationNode(
        episode_id=f"episode-{node_id}",
        chain_id=f"chain-{node_id}",
        node_id=node_id,
        stage=stage,
        decision_time=datetime(2019, 1, 1, tzinfo=timezone.utc),
        sobt_minutes=73.0,
        state_sets={},
        consequence_sets={},
        supports=supports,
        support_full={representation: True for representation in scores},
        delay_scores={representation: 1.0 for representation in scores},
        consequence_scores=scores,
        domain_scores={
            "HISTORY_JOINT": domain_scores or {"F": 1.0, "P": 1.0, "R": 1.0}
        },
    )


def _attention_candidates() -> tuple[AttentionCandidate, ...]:
    return (
        AttentionCandidate(
            episode_id="episode-1",
            chain_id="chain-1",
            node_id="n1",
            stage=OperationalStage.PRE_IB,
            delay_score=1.0,
            consequence_score=10.0,
            p_c=10.0,
            domain_scores={"F": 10.0, "P": 0.0, "R": 0.0},
            support_mass=1.0,
            support_threshold=0.90,
        ),
        AttentionCandidate(
            episode_id="episode-2",
            chain_id="chain-2",
            node_id="n2",
            stage=OperationalStage.PRE_IB,
            delay_score=9.0,
            consequence_score=8.0,
            p_c=8.0,
            domain_scores={"F": 0.0, "P": 8.0, "R": 0.0},
            support_mass=1.0,
            support_threshold=0.90,
        ),
        AttentionCandidate(
            episode_id="episode-3",
            chain_id="chain-3",
            node_id="n3",
            stage=OperationalStage.PRE_IB,
            delay_score=2.0,
            consequence_score=3.0,
            p_c=3.0,
            domain_scores={"F": 0.0, "P": 0.0, "R": 3.0},
            support_mass=1.0,
            support_threshold=0.90,
        ),
        AttentionCandidate(
            episode_id="episode-4",
            chain_id="chain-4",
            node_id="n4",
            stage=OperationalStage.PRE_IB,
            delay_score=2.0,
            consequence_score=2.0,
            p_c=2.0,
            domain_scores={"F": 0.0, "P": 0.0, "R": 2.0},
            support_mass=1.0,
            support_threshold=0.90,
        ),
    )


def _attention_result():
    result = select_and_evaluate(
        _attention_candidates(), q=0.20, cohort_id="TEST_ATTENTION"
    )
    assert result is not None
    return result


# Section 4 H capacity


def test_h_capacity_only_calls_m1() -> None:
    tree = ast.parse(Path(h_capacity.__file__).read_text(encoding="utf-8"))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    model_modules = {module for module in modules if module.startswith("model.")}
    assert model_modules
    assert all(
        module.startswith("model.M1.") or module.startswith("model.common.")
        for module in model_modules
    )


def test_h_capacity_never_imports_m2_m3_m4() -> None:
    source = Path(h_capacity.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        module.startswith(("model.M2", "model.M3", "model.M4"))
        for module in modules
    )


def test_h8_h16_h32_same_features() -> None:
    cohort = {
        "train_episode_ids": ["train-a"],
        "calibration_episode_ids": ["cal-a"],
        "development_episode_ids": ["dev-a"],
    }
    contract = h_capacity._shared_training_contract(cohort)
    assert h_capacity.H_CAPACITY_GRID == (8, 16, 32)
    assert contract["features"] == h_capacity.FEATURE_NAMES_V2
    assert "shared_contract = _shared_training_contract(cohort)" in inspect.getsource(
        h_capacity.run_h_capacity_development
    )


def test_h8_h16_h32_same_split() -> None:
    cohort = {
        "train_episode_ids": ["train-a", "train-b"],
        "calibration_episode_ids": ["cal-a"],
        "development_episode_ids": ["dev-a"],
    }
    first = h_capacity._shared_training_contract(cohort)
    second = h_capacity._shared_training_contract(cohort)
    assert first["split_hash"] == second["split_hash"]
    assert first["support_hash"] == second["support_hash"]


def test_h_capacity_final_test_forbidden() -> None:
    row = SimpleNamespace(episode_date=date(2019, 10, 1))
    with pytest.raises(RuntimeError, match="JATM_SECTION4_FINAL_TEST_FORBIDDEN"):
        h_capacity._require_development_rows((row,))


# Canonical cohort


def test_one_episode_one_stage_one_canonical_node() -> None:
    rows = (
        SimpleNamespace(
            episode_id="e1",
            stage=OperationalStage.PRE_IB,
            decision_time=datetime(2019, 1, 1, 3, tzinfo=timezone.utc),
            node_id="n3",
            supported=True,
        ),
        SimpleNamespace(
            episode_id="e1",
            stage=OperationalStage.PRE_IB,
            decision_time=datetime(2019, 1, 1, 1, tzinfo=timezone.utc),
            node_id="n1",
            supported=True,
        ),
        SimpleNamespace(
            episode_id="e1",
            stage=OperationalStage.PRE_IB,
            decision_time=datetime(2019, 1, 1, 2, tzinfo=timezone.utc),
            node_id="n2",
            supported=True,
        ),
    )
    cohort = canonical_stage_cohort(
        rows, stage=OperationalStage.PRE_IB, eligibility=lambda row: row.supported
    )
    assert canonical_node_ids(cohort) == ("n1",)


def test_canonical_choice_is_deterministic() -> None:
    rows = [
        SimpleNamespace(
            episode_id=f"e{index}",
            stage=OperationalStage.POST_IB_PRE_OB,
            decision_time=datetime(2019, 1, 1, index, tzinfo=timezone.utc),
            node_id=f"n{index}",
            supported=True,
        )
        for index in (3, 1, 2)
    ]
    first = canonical_stage_cohort(
        rows,
        stage=OperationalStage.POST_IB_PRE_OB,
        eligibility=lambda row: row.supported,
    )
    second = canonical_stage_cohort(
        list(reversed(rows)),
        stage=OperationalStage.POST_IB_PRE_OB,
        eligibility=lambda row: row.supported,
    )
    assert canonical_node_ids(first) == canonical_node_ids(second)


def test_variants_share_identical_canonical_ids() -> None:
    rows = (
        SimpleNamespace(
            episode_id="e1",
            stage=OperationalStage.PRE_IB,
            decision_time=datetime(2019, 1, 1, 1, tzinfo=timezone.utc),
            node_id="fixed-node",
            variant="A",
        ),
        SimpleNamespace(
            episode_id="e1",
            stage=OperationalStage.PRE_IB,
            decision_time=datetime(2019, 1, 1, 2, tzinfo=timezone.utc),
            node_id="later-node",
            variant="A",
        ),
    )
    first = canonical_stage_cohort(
        rows, stage=OperationalStage.PRE_IB, eligibility=lambda row: False
    )
    second = canonical_stage_cohort(
        rows, stage=OperationalStage.PRE_IB, eligibility=lambda row: True
    )
    assert canonical_node_ids(first) == canonical_node_ids(second) == ("fixed-node",)
    assert first[0].eligible is False
    assert second[0].eligible is True


# Stage I


def test_delay_consequence_same_candidate_queue() -> None:
    result = _attention_result()
    reference = {
        (entry.episode_id, entry.chain_id, entry.node_id)
        for entry in result.reference_decision.entries
    }
    comparator = {
        (entry.episode_id, entry.chain_id, entry.node_id)
        for entry in result.comparator_decision.entries
    }
    assert reference == comparator


def test_delay_consequence_same_k() -> None:
    result = _attention_result()
    assert result.reference_decision.k == result.comparator_decision.k


def test_L_att_identity() -> None:
    result = _attention_result()
    evaluation = result.evaluation
    assert evaluation.L_att == pytest.approx(
        (evaluation.reference_attention_value - evaluation.comparator_attention_value)
        / evaluation.reference_attention_value
    )


def test_value_retained_identity() -> None:
    row = attention_row(_attention_result(), q=0.20)
    assert row["value_retained"] == pytest.approx(
        float(row["A_D"]) / float(row["A_C"])
    )


def test_reassigned_count_identity() -> None:
    result = _attention_result()
    row = attention_row(result, q=0.20)
    assert row["reassigned_count"] == len(result.evaluation.displaced)
    assert row["reassigned_count"] == int(
        result.evaluation.diagnostics["displaced_count"]
    )


def test_domain_retention_uses_reference_domains() -> None:
    result = _attention_result()
    rows = {
        row["domain"]: row
        for row in attention_domain_rows(result, q=0.20)
    }
    candidates = {row.node_id: row for row in result.candidates}
    for domain in ("F", "P", "R"):
        reference = sum(
            candidates[node_id].domain_scores[domain]
            for node_id in result.evaluation.reference_shortlist
        )
        comparator = sum(
            candidates[node_id].domain_scores[domain]
            for node_id in result.evaluation.comparator_shortlist
        )
        assert rows[domain]["A_reference"] == pytest.approx(reference)
        assert rows[domain]["A_comparator"] == pytest.approx(comparator)


# Bootstrap


def test_bootstrap_resamples_episode() -> None:
    seen: list[tuple[str, ...]] = []

    def statistic(episode_ids):
        seen.append(tuple(episode_ids))
        return float(len(set(episode_ids)))

    values = bootstrap_estimates(
        episode_ids=("e1", "e2", "e3"),
        seed=7,
        replicates=20,
        statistic=statistic,
    )
    assert values.size == 20
    assert any(len(set(draw)) < len(draw) for draw in seen)


def _bootstrap_nodes():
    return {
        OperationalStage.PRE_IB: (
            _representation_node("pre-1", stage=OperationalStage.PRE_IB),
        ),
        OperationalStage.POST_IB_PRE_OB: (
            _representation_node("turn-1", stage=OperationalStage.POST_IB_PRE_OB),
        ),
        OperationalStage.POST_OB_PRE_TO: (
            _representation_node("taxi-1", stage=OperationalStage.POST_OB_PRE_TO),
        ),
    }


def test_bootstrap_recanonicalizes_after_resample(monkeypatch) -> None:
    canonical_calls: list[int] = []
    select_calls: list[tuple[str, ...]] = []

    def fake_canonical(rows, *, stage, eligibility):
        canonical_calls.append(len(tuple(rows)))
        return tuple(
            CanonicalStageRow(node=row, eligible=True, eligibility_reason="TEST")
            for row in rows
        )

    def fake_candidate(node):
        return SimpleNamespace(node_id=node.node_id, stage=node.stage)

    def fake_select(candidates, *, q, cohort_id, canonical_nodes=None):
        candidates = tuple(candidates)
        if not candidates:
            return None
        select_calls.append(tuple(candidate.node_id for candidate in candidates))
        return SimpleNamespace(
            stage=candidates[0].stage,
            evaluation=SimpleNamespace(
                L_att=0.1,
                reference_attention_value=1.0,
                comparator_attention_value=0.9,
                overlap_count=0,
                displaced=(),
                reference_shortlist=tuple(
                    candidate.node_id for candidate in candidates
                ),
            ),
        )

    monkeypatch.setattr(run_development, "canonical_stage_cohort", fake_canonical)
    monkeypatch.setattr(run_development, "candidate", fake_candidate)
    monkeypatch.setattr(run_development, "select_and_evaluate", fake_select)
    run_development._attention_bootstrap(
        _bootstrap_nodes(), q_grid=(0.10,), seed=11, replicates=2
    )
    assert len(canonical_calls) == 6
    assert select_calls


def test_bootstrap_reselects_topk(monkeypatch) -> None:
    select_calls: list[tuple[str, ...]] = []

    def fake_canonical(rows, *, stage, eligibility):
        return tuple(
            CanonicalStageRow(node=row, eligible=True, eligibility_reason="TEST")
            for row in rows
        )

    def fake_candidate(node):
        return SimpleNamespace(node_id=node.node_id, stage=node.stage)

    def fake_select(candidates, *, q, cohort_id, canonical_nodes=None):
        candidates = tuple(candidates)
        if not candidates:
            return None
        select_calls.append(tuple(candidate.node_id for candidate in candidates))
        return SimpleNamespace(
            stage=candidates[0].stage,
            evaluation=SimpleNamespace(
                L_att=0.2,
                reference_attention_value=1.0,
                comparator_attention_value=0.8,
                overlap_count=0,
                displaced=(),
                reference_shortlist=tuple(
                    candidate.node_id for candidate in candidates
                ),
            ),
        )

    monkeypatch.setattr(run_development, "canonical_stage_cohort", fake_canonical)
    monkeypatch.setattr(run_development, "candidate", fake_candidate)
    monkeypatch.setattr(run_development, "select_and_evaluate", fake_select)
    run_development._attention_bootstrap(
        _bootstrap_nodes(), q_grid=(0.10,), seed=11, replicates=3
    )
    assert select_calls


# Stage II


def test_V_equals_J0_minus_Jstar() -> None:
    node = _representation_node("pre-1")
    decision = _recovery_decision(node_id="pre-1", j_zero=4.0, j_star=1.5)
    cohort = ReferenceRecoveryCohort(
        nodes=(
            ReferenceRecoveryNode(
                node=node,
                reference_decision=decision,
                reference_objectives={},
                reference_recoverable_value=2.5,
                action_grid=(0.0, 5.0, 10.0),
            ),
        ),
        source_shortlists={},
    )
    row = recovery_atomic_rows(cohort)[0]
    assert float(row["V"]) == pytest.approx(
        float(row["J_zero"]) - float(row["J_star"])
    )


def test_u_star_in_action_grid() -> None:
    decision = _recovery_decision(node_id="pre-1")
    assert decision.u_star in decision.action_grid


def test_taxistage_not_positive_recovery() -> None:
    nodes = (
        SimpleNamespace(
            node_id="pre-1",
            episode_id="episode-pre-1",
            stage=OperationalStage.PRE_IB,
            support_full={"HISTORY_JOINT": True},
        ),
        SimpleNamespace(
            node_id="turn-1",
            episode_id="episode-turn-1",
            stage=OperationalStage.POST_IB_PRE_OB,
            support_full={"HISTORY_JOINT": True},
        ),
        SimpleNamespace(
            node_id="taxi-1",
            episode_id="episode-taxi-1",
            stage=OperationalStage.POST_OB_PRE_TO,
            support_full={"HISTORY_JOINT": True},
        ),
    )
    cohort = reference_recovery_cohort(
        nodes,
        source_shortlists={
            OperationalStage.PRE_IB: ("pre-1",),
            OperationalStage.POST_IB_PRE_OB: ("turn-1",),
            OperationalStage.POST_OB_PRE_TO: ("taxi-1",),
        },
    )
    assert tuple(node.node_id for node in cohort) == ("pre-1", "turn-1")


def test_reference_recovery_cohort_fixed() -> None:
    first = (
        SimpleNamespace(
            node_id="pre-2",
            episode_id="episode-pre-2",
            stage=OperationalStage.PRE_IB,
            support_full={"HISTORY_JOINT": True},
        ),
        SimpleNamespace(
            node_id="turn-1",
            episode_id="episode-turn-1",
            stage=OperationalStage.POST_IB_PRE_OB,
            support_full={"HISTORY_JOINT": True},
        ),
    )
    second = tuple(reversed(first))
    shortlists = {
        OperationalStage.PRE_IB: ("pre-2",),
        OperationalStage.POST_IB_PRE_OB: ("turn-1",),
    }
    assert tuple(node.node_id for node in reference_recovery_cohort(first, source_shortlists=shortlists)) == (
        "pre-2",
        "turn-1",
    )
    assert tuple(node.node_id for node in reference_recovery_cohort(second, source_shortlists=shortlists)) == (
        "pre-2",
        "turn-1",
    )


def test_stage2_sobt_coordinate_is_node_relative() -> None:
    node = SimpleNamespace(sobt_minutes=73.25)
    context = transition_context(node, _headroom())
    assert context.sobt_minutes == pytest.approx(73.25)
    assert context.sobt_minutes != 0.0


def _fake_reference_item(*, recoverable_value: float = 2.0) -> ReferenceRecoveryNode:
    node = SimpleNamespace(
        node_id="pre-1",
        episode_id="episode-pre-1",
        stage=OperationalStage.PRE_IB,
        sobt_minutes=73.0,
        state=lambda representation: None,
    )
    decision = _recovery_decision(node_id="pre-1")
    return ReferenceRecoveryNode(
        node=node,
        reference_decision=decision,
        reference_objectives={
            ("pre-1", 5.0): 1.0,
            ("pre-1", 10.0): 2.0,
        },
        reference_recoverable_value=recoverable_value,
        action_grid=(0.0, 5.0, 10.0),
    )


def _fake_comparator_recovery(monkeypatch, *, recoverable_value: float = 2.0):
    item = _fake_reference_item(recoverable_value=recoverable_value)
    cohort = ReferenceRecoveryCohort(nodes=(item,), source_shortlists={})
    comparator = _recovery_decision(node_id="pre-1", u_star=10.0)
    monkeypatch.setattr(recovery_value, "_state_supported", lambda *_: True)
    monkeypatch.setattr(
        recovery_value,
        "solve_recovery",
        lambda *args, **kwargs: comparator,
    )
    return cohort, comparator_recovery(
        cohort,
        representation="HISTORY_POINT",
        service=object(),
        headroom=_headroom(),
    )


def test_all_comparators_use_fixed_Rstar(monkeypatch) -> None:
    cohort, result = _fake_comparator_recovery(monkeypatch)
    assert result.evaluation.fixed_cohort == tuple(
        item.node.node_id for item in cohort.nodes
    )


def test_delta_J_always_persisted(monkeypatch) -> None:
    _cohort, result = _fake_comparator_recovery(monkeypatch, recoverable_value=0.0)
    assert result.evaluation.delta_recovery_objective == pytest.approx(1.0)
    assert result.evaluation.L_rec is None


def test_L_rec_undefined_on_zero_reference_value(monkeypatch) -> None:
    _cohort, result = _fake_comparator_recovery(monkeypatch, recoverable_value=0.0)
    assert result.evaluation.reference_recoverable_value == 0.0
    assert result.evaluation.L_rec is None
    assert result.evaluation.status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE


# Information value


def _comparison_nodes() -> tuple[RepresentationNode, ...]:
    return (
        _representation_node(
            "n1",
            comparator_scores={
                "CURRENT_JOINT": 1.0,
                "HISTORY_POINT": 8.0,
                "HISTORY_MARGINAL": 4.0,
            },
            domain_scores={"F": 10.0, "P": 0.0, "R": 0.0},
        ),
        _representation_node(
            "n2",
            comparator_scores={
                "CURRENT_JOINT": 9.0,
                "HISTORY_POINT": 1.0,
                "HISTORY_MARGINAL": 9.0,
            },
            domain_scores={"F": 0.0, "P": 8.0, "R": 0.0},
        ),
        _representation_node(
            "n3",
            comparator_scores={
                "CURRENT_JOINT": 2.0,
                "HISTORY_POINT": 3.0,
                "HISTORY_MARGINAL": 3.0,
            },
            domain_scores={"F": 0.0, "P": 0.0, "R": 3.0},
        ),
        _representation_node(
            "n4",
            comparator_scores={
                "CURRENT_JOINT": 2.0,
                "HISTORY_POINT": 2.0,
                "HISTORY_MARGINAL": 2.0,
            },
            domain_scores={"F": 0.0, "P": 0.0, "R": 2.0},
        ),
    )


def test_all_comparators_use_reference_evaluator() -> None:
    reference_scores = {node.node_id: node.consequence_scores["HISTORY_JOINT"] for node in _comparison_nodes()}
    for component, (comparator, reference) in COMPONENTS.items():
        candidates = common_candidates(_comparison_nodes(), comparator=comparator)
        evaluation = evaluate_component_attention(
            candidates, q=0.20, component=component
        )
        assert evaluation is not None
        assert evaluation.reference_id == reference
        expected = sum(
            reference_scores[node_id] for node_id in evaluation.reference_shortlist
        )
        assert evaluation.reference_attention_value == pytest.approx(expected)


def test_marginal_increment_is_paired_difference() -> None:
    point = [0.4, 0.8, 1.2]
    marginal = [0.1, 0.3, 0.5]
    result = paired_information_increment_contrast(
        point, marginal, seed=13, replicates=2000
    )
    assert result["estimate"] == pytest.approx(
        sum(left - right for left, right in zip(point, marginal)) / len(point)
    )
    assert result["ci_low"] == pytest.approx(0.3)
    assert result["ci_high"] == pytest.approx(0.7)


# Reporting


def _report_payload() -> dict[str, object]:
    return {
        "h_capacity_status": {"H8": "COMPLETE", "H16": "COMPLETE", "H32": "COMPLETE"},
        "selected_history_capacity": 16,
        "attention_value": {
            "canonical_counts": {"PRE": 1, "TURN": 1, "TAXI": 1},
            "q_grid": [0.05, 0.10, 0.20, 0.30],
            "overall": {"L_att_overall": 0.25},
            "bootstrap_status": "COMPLETE",
        },
        "recovery_value": {
            "R_star_size": 2,
            "stage_counts": {"PRE": 1, "TURN": 1},
            "stage_summary": [],
        },
        "information_value": {
            "components": ["ROLLING_HISTORY"],
            "metric_aliases": {
                "CROSS_STATE_DEPENDENCE_L_ATT": {"value": 0.01},
                "CROSS_STATE_DEPENDENCE_L_REC": {"value": 0.02},
                "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT": {"value": 0.03},
                "MARGINAL_UNCERTAINTY_INCREMENT_L_REC": {"value": 0.04},
            },
            "paired_increments": [],
        },
        "robustness": {"row_count": 3},
        "scientific_definition_changed": (
            "STAGE1_EMPIRICAL_ORCHESTRATION_PATCH_ONLY"
        ),
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


def test_reporting_does_not_recompute_science(monkeypatch) -> None:
    import model.M4.evaluation as evaluation

    def forbidden(*args, **kwargs):
        raise AssertionError("reporting recomputed science")

    monkeypatch.setattr(evaluation, "evaluate_attention_allocation", forbidden)
    report = render_report(_report_payload())
    assert "JATM Section 5 Development Report" in report
    assert "Overall L_att: 0.25" in report
    assert "CROSS_STATE_DEPENDENCE_L_ATT" in report
    assert "MARGINAL_UNCERTAINTY_INCREMENT_L_ATT" in report
    assert "Final-Test complete: NO" in report
    assert "SCIENTIFIC_ORCHESTRATION_CHANGED: YES" in report
    assert (
        "SCIENTIFIC_ORCHESTRATION_PATCH: STAGE_MATCHED_PRE_TURN_SCREENING"
        in report
    )
    assert "M1_DEFINITION_CHANGED: NO" in report


def test_reporting_contains_no_section_number_authority() -> None:
    report = render_report(_report_payload())
    assert "Section 5.1" not in report
    assert set(SECTION_MAPPING) == {
        "attention_value",
        "recovery_value",
        "information_value",
        "robustness",
    }


def test_no_L_total() -> None:
    report = render_report(_report_payload())
    assert "L_total" not in report
    source = Path(render_report.__code__.co_filename).read_text(encoding="utf-8")
    assert "L_total" not in source
