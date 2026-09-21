"""Gate B.0 executor DAG contracts (Development-safe fixture only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from formal import v2_phase7_final_test_run as runner
from formal.v2_phase7 import constants as C
from formal.v2_phase7.executor import stages as S
from formal.v2_phase7.executor.attention_decisions import (
    build_attention_decisions,
    decision_rows,
)
from formal.v2_phase7.executor.bootstrap import bootstrap_seed_provenance
from formal.v2_phase7.gate_b0 import run_gate_b0_binding_audit
from formal.v2_phase7.executor.codec import (
    attention_decision_to_payload,
    priority_signal_to_payload,
    state_set_to_payload,
)
from formal.v2_phase7.executor.nodes import nodes_from_payload
from formal.v2_phase7.executor.paper_views import build_paper_views
from formal.v2_phase7.executor.recovery_decisions import build_recovery_decisions
from formal.v2_phase7.executor.reference_cohort import (
    build_reference_recovery_cohort,
    reference_shortlist_node_ids,
)
from formal.v2_phase7.executor.runner import run_development_safe_dag
from formal.v2_phase7.executor.services import load_frozen_services
from model.M3.stage1 import select_attention
from model.common.decision_contracts import (
    HistoryScope,
    PrioritySignal,
    SignalKind,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState

NODE_LIMIT = 48
REFERENCE_VARIANT = "HISTORY_JOINT"


@pytest.fixture(scope="module")
def dag(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("gate_b0_dag")
    run = run_development_safe_dag(output_root=root, node_limit=NODE_LIMIT)
    return {"run": run, "root": root}


def test_full_dag_computes_every_stage(dag: dict[str, Any]) -> None:
    run = dag["run"]
    assert list(run.manifest["dag_stages"]) == list(S.SCIENCE_DAG_STAGES)
    assert run.manifest["computed_stages"] == list(S.SCIENCE_DAG_STAGES)
    assert run.manifest["reused_stages"] == []
    assert run.manifest["immutable_checkpoint_consumption"] is True
    assert run.manifest["atomic_results_before_views"] is True
    assert run.manifest["access_boundary"] == {
        "q4_raw_read": False,
        "legacy_final_test_result_tree_scientific_read_by_fixture": False,
        "legacy_final_test_result_tree_incidental_repository_audit_reads": 1,
        "legacy_final_test_result_tree_reads_used_for_scientific_computation": False,
        "legacy_final_test_result_tree_reads_used_for_selection": False,
        "phase7_scientific_access_increment": 0,
        "human_release_created": False,
        "phase7_access_epoch_opened": False,
        "historical_final_test_access_total": 1,
        "current_freeze_run_increment": 0,
    }
    for stage in S.SCIENCE_DAG_STAGES:
        assert run.record(stage).payload_hash.startswith("sha256:")
        assert run.payload(stage)["schema_version"] == S.schema_version(stage)


def test_gate_b0_report_binds_executor_before_authorization(
    dag: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(C, "GATE_B_RELEASE_PATH", tmp_path / "NO_RELEASE.json")
    monkeypatch.setattr(C, "PHASE7_ACCESS_AUDIT_PATH", tmp_path / "NO_AUDIT.json")
    epoch_paths = C.epoch_paths_for(tmp_path / "current_epoch")
    historical_paths = C.epoch_paths_for(tmp_path / "historical_epoch")
    report = run_gate_b0_binding_audit(
        output_root=Path(dag["root"]) / "GATE_B0_REPORT.json",
        fixture_root=Path(dag["root"]) / "gate_b0_report_fixture",
        node_limit=NODE_LIMIT,
        epoch_paths=epoch_paths,
        historical_paths=historical_paths,
        write=False,
    )
    assert report["status"] == "PASS"
    assert report["production_executor_bound"] is True
    assert report["production_executor_ready"] is False
    assert report["gate_b_authorized"] is False
    assert report["pre_open_status"] == "PRE_OPEN_AUTHORIZATION_READY_ONLY"
    assert report["access_boundary"]["current_freeze_run_increment"] == 0
    assert report["access_boundary"]["historical_final_test_access_total"] == 1
    assert report["stage2_primary_solver"] == C.STAGE2_PRIMARY_SOLVER
    assert report["highs_role"] == C.HIGHS_ROLE
    assert report["solver_status_semantics"] == C.SOLVER_STATUS_SEMANTICS
    names = {check["name"] for check in report["checks"]}
    assert "PRODUCTION_EXECUTOR_BOUND" in names
    assert "TYPED_STATE_CONTRACTS" in names


def test_resume_reuses_every_stage_without_loading_services(
    dag: dict[str, Any]
) -> None:
    calls: list[int] = []

    def factory():
        calls.append(1)
        return load_frozen_services()

    resumed = run_development_safe_dag(
        output_root=dag["root"],
        node_limit=NODE_LIMIT,
        services_factory=factory,
    )
    assert resumed.manifest["reused_stages"] == list(S.SCIENCE_DAG_STAGES)
    assert resumed.manifest["computed_stages"] == []
    assert resumed.manifest["frozen_services_loaded"] is False
    assert calls == []


def test_downstream_only_rebuild_keeps_upstream_checkpoints(
    dag: dict[str, Any]
) -> None:
    root = Path(dag["root"])
    original = dict(dag["run"].payload(S.PAPER_VIEWS))
    target = root / f"{S.PAPER_VIEWS}.json"
    body = json.loads(target.read_text(encoding="utf-8"))
    target.unlink()
    calls: list[int] = []

    def factory():
        calls.append(1)
        return load_frozen_services()

    rebuilt = run_development_safe_dag(
        output_root=root,
        node_limit=NODE_LIMIT,
        services_factory=factory,
    )
    assert rebuilt.manifest["computed_stages"] == [S.PAPER_VIEWS]
    assert rebuilt.manifest["reused_stages"] == [
        stage for stage in S.SCIENCE_DAG_STAGES if stage != S.PAPER_VIEWS
    ]
    assert calls == []
    assert dict(rebuilt.payload(S.PAPER_VIEWS)) == original
    assert rebuilt.record(S.PAPER_VIEWS).payload_hash == body["payload_hash"]
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_four_primary_variants_share_one_dag(dag: dict[str, Any]) -> None:
    payload = dag["run"].payload(S.STATE_VARIANTS)
    assert payload["reference_variant"] == REFERENCE_VARIANT
    variants = [block["variant"] for block in payload["variants"]]
    assert variants == list(S.PRIMARY_STATE_VARIANTS)
    representations = {
        block["variant"]: block["representation_id"] for block in payload["variants"]
    }
    assert len(set(representations.values())) == 4
    assert payload["fixed_window_sensitivity_status"] == "NOT_AVAILABLE_NOT_FROZEN"
    assert payload["sensitivity"]["FIXED_WINDOW_HISTORY"] == (
        "NOT_AVAILABLE_NOT_FROZEN"
    )
    assert "INDEPEND" in payload["marginal_identity_note"].upper() or (
        "NOT" in payload["marginal_identity_note"].upper()
    )


def test_reference_cohort_follows_history_joint_shortlist(dag: dict[str, Any]) -> None:
    run = dag["run"]
    attention = run.payload(S.ATTENTION_DECISIONS)
    cohort = run.payload(S.REFERENCE_RECOVERY_COHORT)
    shortlist = reference_shortlist_node_ids(attention, stage="PRE_IB")
    turn_shortlist = reference_shortlist_node_ids(
        attention, stage="POST_IB_PRE_OB"
    )
    assert list(shortlist) == cohort["shortlist_node_ids_by_stage"]["PRE_IB"]
    assert list(turn_shortlist) == cohort["shortlist_node_ids_by_stage"][
        "POST_IB_PRE_OB"
    ]
    assert cohort["shortlist_node_ids"] == [
        *cohort["shortlist_node_ids_by_stage"]["PRE_IB"],
        *cohort["shortlist_node_ids_by_stage"]["POST_IB_PRE_OB"],
    ]
    assert cohort["shortlist_size"] == len(cohort["shortlist_node_ids"])
    assert cohort["reference_variant"] == REFERENCE_VARIANT
    assert cohort["reference_authority"] == C.REFERENCE_AUTHORITY
    assert cohort["alternative_representations_use_fixed_r_star"] is True
    assert cohort["flattened_union_semantics"] == (
        "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION"
    )
    assert cohort["stage2_actionable_node_ids_flattened"] == [
        *cohort["stage2_actionable_node_ids_by_stage"]["PRE_IB"],
        *cohort["stage2_actionable_node_ids_by_stage"]["POST_IB_PRE_OB"],
    ]
    assert set(cohort["stage2_actionable_node_ids_by_stage"]) == {
        "PRE_IB",
        "POST_IB_PRE_OB",
    }
    assert set(cohort["stage2_actionable_node_ids"]) <= set(
        cohort["shortlist_node_ids"]
    )
    assert cohort["stage2_cohort_size"] == len(cohort["stage2_actionable_node_ids"])
    stages = {
        node.stage: node.node_id for node in nodes_from_payload(run.payload(S.CANONICAL_NODES))
    }
    assert cohort["shortlist_stage_counts"]


def test_stage2_enumeration_primary_authority(dag: dict[str, Any]) -> None:
    payload = dag["run"].payload(S.RECOVERY_DECISIONS)
    assert payload["stage2_primary_solver"] == C.STAGE2_PRIMARY_SOLVER
    assert payload["final_test_primary_solver"] == C.FINAL_TEST_PRIMARY_SOLVER
    assert payload["highs_role"] == C.HIGHS_ROLE
    assert payload["highs_required_for_production_rows"] is False
    assert payload["deterministic_tie_break"] == C.DETERMINISTIC_TIE_BREAK
    assert payload["solver_status_semantics"] == C.SOLVER_STATUS_SEMANTICS
    assert payload["formal_solver"] == C.STAGE2_PRIMARY_SOLVER
    assert payload["parity_oracle"] == C.PARITY_BACKEND
    assert payload["objective_perturbation"] == "NONE"
    assert payload["production_rows_use_highs"] is False
    assert payload["row_parity_checks_executed"] == 0
    assert payload["invariants"]["status"] == "PASS"
    assert payload["specification"]["lambda"] == C.NOMINAL_LAMBDA
    assert payload["specification"]["u_max"] == C.NOMINAL_U_MAX
    assert payload["specification"]["u_max_by_specification"] == {
        "Q80": 25.0,
        "nominal": 45.0,
        "Q95": 75.0,
    }
    actionable = 0
    for row in payload["rows"]:
        assert row["parity"] is None
        if not row["actionable"]:
            if row["decision"] is not None:
                assert row["decision"]["solver_status"] == "NOT_RUN"
            continue
        actionable += 1
        decision = row["decision"]
        assert decision["solver_status"] == "EXACT_ENUMERATION"
        assert decision["u_star"] in decision["action_grid"]
        assert decision["action_grid"][0] == 0.0
        assert decision["action_grid"][-1] == C.NOMINAL_U_MAX
        assert decision["recoverable_value"] >= -C.M3_NUMERICAL_COMPARISON_TOLERANCE
    assert actionable > 0


def test_production_recovery_never_calls_highs(
    dag: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import model.M3.solver as solver_module

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("production recovery must not call HiGHS")

    monkeypatch.setattr(solver_module, "solve_stage2_with_highs", _explode)
    monkeypatch.setattr(solver_module, "solve_with_highs", _explode)
    run = dag["run"]
    payload = build_recovery_decisions(
        run.payload(S.CANONICAL_NODES),
        run.payload(S.STATE_VARIANTS),
        run.payload(S.REFERENCE_RECOVERY_COHORT),
        services=load_frozen_services(),
    )
    assert payload["stage2_primary_solver"] == C.STAGE2_PRIMARY_SOLVER
    assert payload["row_parity_checks_executed"] == 0
    assert all(row["parity"] is None for row in payload["rows"])


def test_forced_highs_primary_is_typed_blocker() -> None:
    from formal.v2_phase7 import stage2_authority

    with pytest.raises(runner.TypedBlocker) as error:
        stage2_authority.require_enumeration_primary("PYOMO_HIGHS")
    assert error.value.code == "PHASE7_STAGE2_PRIMARY_SOLVER_VIOLATION"


def test_solver_status_is_backend_identity_not_termination_state() -> None:
    from model.common.decision_contracts import SolverStatus
    from formal.v2_phase7.stage2_authority import (
        validate_solver_status_semantics,
    )

    contract = validate_solver_status_semantics()
    assert contract["status"] == "PASS"
    assert contract["field_role"] == (
        "STAGE2_SOLUTION_PROVENANCE_BACKEND_IDENTITY"
    )
    assert contract["member_values"] == [
        "PYOMO_HIGHS",
        "EXACT_ENUMERATION",
        "NOT_RUN",
    ]
    assert contract["termination_condition_is_separate"] is True
    assert not hasattr(SolverStatus, "OPTIMAL")


def test_not_actionable_stage_keeps_typed_zero_action(dag: dict[str, Any]) -> None:
    run = dag["run"]
    nodes = nodes_from_payload(run.payload(S.CANONICAL_NODES))
    non_actionable = [
        node
        for node in nodes
        if node.stage in C.STAGE_II_NON_ACTIONABLE_STAGES
    ]
    if not non_actionable:
        pytest.skip("fixture subset contains no TAXI/COMP node")
    actionable = [
        node for node in nodes if node.stage in C.STAGE_II_ACTIONABLE_STAGES
    ]
    assert actionable
    shortlist = [non_actionable[0].node_id, actionable[0].node_id]
    cohort_payload = {
        "reference_variant": REFERENCE_VARIANT,
        "cohort_id": C.STAGE2_INFORMATION_COHORT,
        "shortlist_node_ids": shortlist,
        "stage2_actionable_node_ids": [actionable[0].node_id],
        "shortlist_size": len(shortlist),
        "stage2_cohort_size": 1,
        "stage2_excluded": [],
    }
    payload = build_recovery_decisions(
        run.payload(S.CANONICAL_NODES),
        run.payload(S.STATE_VARIANTS),
        cohort_payload,
        services=load_frozen_services(),
    )
    rows = {
        (row["variant"], row["node_id"]): row
        for row in payload["rows"]
        if row["node_id"] == non_actionable[0].node_id
    }
    assert len(rows) == len(S.PRIMARY_STATE_VARIANTS)
    for row in rows.values():
        assert row["typed_state"] == "NOT_ACTIONABLE"
        assert row["decision"]["actionable_status"] == "NOT_ACTIONABLE"
        assert row["decision"]["u_star"] == 0.0
        assert row["decision"]["action_grid"] == [0.0]
        assert row["decision"]["recoverable_value"] is None
    assert payload["typed_state_counts"]["NOT_ACTIONABLE"] == len(
        S.PRIMARY_STATE_VARIANTS
    )


def test_m4_common_basis_and_reference_invariants(dag: dict[str, Any]) -> None:
    payload = dag["run"].payload(S.M4_COMPARISONS)
    assert payload["cohort_id"] == C.STAGE2_INFORMATION_COHORT
    assert payload["stage2_information_comparison_uses_fixed_r_star"] is True
    assert payload["alternative_representations_may_define_h_r_for_l_att"] is True
    assert payload["priority_authority"]["delay_comparator_is_l_att_basis"] is False
    assert payload["no_total_loss_constructed"] is True
    invariant = payload["invariants"]
    assert invariant["status"] == "PASS"
    assert invariant["delta_objective_violations"] == []
    assert invariant["reference_attention_identity"] == pytest.approx(0.0, abs=1e-6)
    if invariant["reference_recovery_identity"] is not None:
        assert invariant["reference_recovery_identity"] == pytest.approx(
            0.0, abs=1e-6
        )
    assert invariant["reference_action_agreement"]["A0"] in {None, 1.0}
    assert invariant["reference_action_agreement"]["A5"] in {None, 1.0}
    assert sorted(payload["attention"]["comparators"]) == sorted(
        S.COMPARATOR_VARIANTS
    )
    assert sorted(payload["recovery"]["comparators"]) == sorted(
        S.COMPARATOR_VARIANTS
    )
    assert _find_key(payload, "L_total") == []


def test_bootstrap_plan_and_cis(dag: dict[str, Any]) -> None:
    payload = dag["run"].payload(S.BOOTSTRAP)
    assert payload["seed"] == C.BOOTSTRAP_SEED
    assert payload["replicates"] == 2000
    assert payload["interval"] == "percentile_95"
    assert payload["resampling_unit"] == "episode_id"
    assert payload["paired"] is True
    assert payload["fixed_window_sensitivity_status"] == "NOT_AVAILABLE_NOT_FROZEN"
    provenance = payload["seed_provenance"]
    assert provenance["status"] == "PASS"
    assert provenance["seed_predates_lock"] is True
    assert provenance["result_driven"] is False
    assert provenance["seed_introduced_at"] <= provenance["lock_created_at"]
    assert "NO_THIRD_PARTY_ATTESTATION" in provenance["attestation"]
    defined = 0
    for record in payload["comparators"].values():
        for section in record.values():
            if section["status"] == "PASS":
                defined += 1
                assert section["ci"][0] <= section["point_estimate"] <= section["ci"][1]
                assert section["valid_replicates"] > 0
                assert all(
                    value == value for value in section["ci"]
                )
            else:
                assert section["typed_state"] in C.TYPED_SCIENTIFIC_STATES
                assert section["point_estimate"] is None or section["ci"] is None
    assert defined > 0


def test_bootstrap_seed_provenance_is_pre_lock() -> None:
    provenance = bootstrap_seed_provenance()
    assert provenance["seed"] == 20260906
    assert provenance["seed_source_path"] == "exp/shared/resampling.py"
    assert provenance["lock_path"] == "formal/FINAL_TEST_LOCK_20260907.md"
    assert provenance["seed_predates_lock"] is True
    assert provenance["result_driven"] is False
    lock = Path(provenance["lock_path"]).read_text(encoding="utf-8")
    assert "20260906" in lock and "2000" in lock


def test_attention_abstaining_candidate_is_excluded_not_zero_filled() -> None:
    rows: list[dict[str, Any]] = []
    for variant in S.PRIMARY_STATE_VARIANTS:
        rows.append(
            _attention_row(variant, "node-a", "PRE_IB", 3.0, 30.0)
        )
        rows.append(
            _attention_row(variant, "node-b", "PRE_IB", 2.0, 20.0)
        )
        rows.append(
            _attention_row(
                variant,
                "node-c",
                "PRE_IB",
                None,
                None,
                status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
                support=SupportState.ABSTAIN,
            )
        )
    payload = build_attention_decisions(
        ("node-a", "node-b", "node-c"),
        consequence_variants={"rows": rows, "reference_variant": REFERENCE_VARIANT},
    )
    row = decision_rows(payload, REFERENCE_VARIANT, "PRE_IB", C.NOMINAL_Q)
    assert row["cohort_size"] == 2
    assert row["abstaining_node_count"] == 1
    assert "node-c" not in row["consequence_decision"]["selected_node_ids"]
    assert all(
        entry["node_id"] != "node-c"
        for entry in row["consequence_decision"]["entries"]
    )
    assert row["selected_stage_counts"] == {"PRE_IB": 1}


def test_abstaining_reference_state_is_typed_excluded() -> None:
    node_payload = {
        "materialization_scope": "UNIT_TEST",
        "node_count": 1,
        "nodes": [
            {
                "node_id": "node-1",
                "episode_id": "episode-1",
                "chain_id": "chain-1",
                "stage": "PRE_IB",
                "decision_time": "2019-01-01T00:00:00+00:00",
                "sobt_minutes": 60.0,
                "connection_airport_id": "AAA",
                "destination_airport_id": "BBB",
                "observed": {},
                "reference_binding": {"turnaround_reference_minutes": 41.0},
                "history_values": [[0.0, 0.0]],
                "history_length": 1,
                "pre_state": {},
            }
        ],
    }
    state_set = StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        stage=OperationalStage.PRE_IB,
        representation=StateRepresentationSpec(
            temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=16,
            history_scope=HistoryScope.FULL_PREFIX,
        ),
        scenarios=(
            StateScenario(
                scenario_id=0,
                scenario_weight=1.0,
                stage=OperationalStage.PRE_IB,
                t_ib_minutes=None,
                d_ob_minutes=None,
                d_tx_minutes=None,
                d_to_minutes=None,
                support=SupportState.ABSTAIN,
            ),
        ),
    )
    state_variants = {
        "variants": [
            {
                "variant": REFERENCE_VARIANT,
                "nodes": [
                    {"node_id": "node-1", "state_set": state_set_to_payload(state_set)}
                ],
            }
        ]
    }
    signal = PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        representation_id=C.REFERENCE_REPRESENTATION_ID,
        score=10.0,
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=0.95,
        comparison_support_threshold=0.90,
    )
    decision = select_attention((signal,), q=C.NOMINAL_Q)
    attention_payload = {
        "rows": [
            {
                "variant": REFERENCE_VARIANT,
                "stage": "PRE_IB",
                "q": C.NOMINAL_Q,
                "consequence_decision": attention_decision_to_payload(decision),
            }
        ]
    }
    cohort = build_reference_recovery_cohort(
        node_payload, state_variants, attention_payload
    )
    assert cohort["shortlist_node_ids"] == ["node-1"]
    assert cohort["stage2_actionable_node_ids"] == []
    assert cohort["stage2_excluded_count"] == 1
    assert cohort["stage2_excluded"][0]["typed_state"] == "ABSTAIN_NO_COMMON_SUPPORT"
    assert cohort["stage2_excluded"][0]["abstaining_scenario_ids"] == [0]


def test_paper_views_are_a_read_only_projection(
    dag: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = dag["run"]
    import model.M3.stage2 as stage2_module
    import model.M4.evaluation as evaluation_module

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("paper views must not recompute science")

    monkeypatch.setattr(stage2_module, "solve_recovery", _explode)
    monkeypatch.setattr(evaluation_module, "evaluate_recovery_loss", _explode)
    monkeypatch.setattr(evaluation_module, "evaluate_attention_allocation", _explode)
    views = build_paper_views(
        run.payload(S.ATTENTION_DECISIONS),
        run.payload(S.M4_COMPARISONS),
        run.payload(S.BOOTSTRAP),
        run.payload(S.ROBUSTNESS),
    )
    assert views["scientific_recomputation_performed"] is False
    assert views["primary_design"] == "STAGE_X_Q"
    section_rows = views["section_5_2"]["rows"]
    for stage in S.ACTIONABLE_STAGE_I_STAGES:
        assert [
            row["q"] for row in section_rows if row["stage"] == stage
        ] == list(C.Q_GRID)
    assert [
        row["q"] for row in section_rows if row["stage"] == "OVERALL"
    ] == list(C.Q_GRID)
    assert views["section_5_2"]["pooled_stage1_ranking"] is False
    assert views["section_5_5"]["crossed_with_q_grid"] is False
    assert views["section_5_5"]["nominal_base"]["q"] == C.NOMINAL_Q
    assert views["section_5_5"]["fixed_window_history_status"] == (
        "NOT_AVAILABLE_NOT_FROZEN"
    )
    excluded = {item["item"]: item["status"] for item in views["excluded_from_final_test_scope"]}
    assert excluded["similar_delay_5_10_15"] == "NOT_ACTIVATED_BY_PHASE6_FREEZE"
    assert excluded["itinerary_threshold_30_60"] == "NOT_ACTIVATED_BY_PHASE6_FREEZE"
    assert excluded["service_threshold_150_210"] == "NOT_ACTIVATED_BY_PHASE6_FREEZE"
    assert excluded["fixed_window_history"] == "NOT_AVAILABLE_NOT_FROZEN"
    assert _find_key(views, "L_total") == []


def _attention_row(
    variant: str,
    node_id: str,
    stage: str,
    delay_score: float | None,
    consequence_score: float | None,
    *,
    status: TypedStatus = TypedStatus.SUPPORTED,
    support: SupportState = SupportState.SUPPORTED,
) -> dict[str, Any]:
    def signal(kind: SignalKind, score: float | None) -> PrioritySignal:
        return PrioritySignal(
            signal_type=kind,
            episode_id=f"episode-{node_id}",
            chain_id=f"chain-{node_id}",
            node_id=node_id,
            representation_id="HISTORY_H16:JOINT" if variant == REFERENCE_VARIANT else variant,
            score=score,
            support=support,
            status=status,
            comparison_support_mass=0.95 if score is not None else 0.20,
            comparison_support_threshold=0.90,
            reason_codes=() if score is not None else ("M2_COMMON_SUPPORT_BELOW_THRESHOLD",),
        )

    return {
        "node_id": node_id,
        "episode_id": f"episode-{node_id}",
        "variant": variant,
        "stage": stage,
        "delay_signal": priority_signal_to_payload(signal(SignalKind.DELAY, delay_score)),
        "consequence_signal": priority_signal_to_payload(
            signal(SignalKind.CONSEQUENCE, consequence_score)
        ),
    }


def _find_key(payload: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for name, value in payload.items():
            if name == key:
                found.append(name)
            found.extend(_find_key(value, key))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_find_key(item, key))
    return found
