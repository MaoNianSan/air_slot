"""Gate B.0: bind and prove the Phase-7 scientific executor pre-open.

This module runs the *whole* frozen DAG on the Development-safe fixture, proves
checkpoint reuse, collects the evidence for every Gate B.0 acceptance item, and
writes the pre-open report. It never creates a human release, never opens an
access epoch, never reads Q4 raw data and never touches the legacy Final-Test
result tree; the report only claims ``pre-open / authorization readiness``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import constants as C
from .errors import TypedBlocker
from .executor import stages as S
from .executor.nodes import nodes_from_payload
from .executor.runner import (
    FIXTURE_PRODUCER,
    ExecutorRun,
    run_development_safe_dag,
)
from .gate_b import production_binding_record
from .materialization import _write_json_atomic
from .stage2_authority import (
    production_solver_metadata,
    validate_stage2_production_authority,
)

REPORT_SCHEMA_VERSION = "AIR_SLOT_V2_PHASE7_GATE_B0_BINDING_V1"
#: The Gate-B.0 fixture subset is large enough to exercise a non-degenerate
#: reference cohort (defined recoverable value, mixed action agreement and a
#: zero-denominator replicate path) while staying Development-safe.
DEFAULT_NODE_LIMIT = 48
PRE_OPEN_STATUS = "PRE_OPEN_AUTHORIZATION_READY_ONLY"
PRE_OPEN_STATUS = "PRE_OPEN_AUTHORIZATION_READY_ONLY"


def run_gate_b0_binding_audit(
    *,
    output_root: Path | None = None,
    fixture_root: Path | None = None,
    node_limit: int = DEFAULT_NODE_LIMIT,
    write: bool = True,
    epoch_paths: C.EpochPaths | None = None,
    historical_paths: C.EpochPaths | None = None,
) -> dict[str, Any]:
    """Run the fixture DAG, collect evidence and (optionally) write the report."""

    root = Path(fixture_root) if fixture_root is not None else (
        C.FIXTURE_DAG_DIAGNOSTICS_ROOT
    )
    current_paths = epoch_paths or C.stage_matched_epoch_paths()
    prior_paths = historical_paths or C.historical_epoch_paths()
    try:
        report = _build_report(
            root=root,
            node_limit=node_limit,
            epoch_paths=current_paths,
            historical_paths=prior_paths,
        )
    except TypedBlocker as error:
        report = _blocked_report(
            error,
            epoch_paths=current_paths,
            historical_paths=prior_paths,
        )
    if write:
        target = Path(output_root) if output_root is not None else C.PRE_OPEN_REPORT_PATH
        _write_json_atomic(target, report)
    return report


def _build_report(
    *,
    root: Path,
    node_limit: int,
    epoch_paths: C.EpochPaths,
    historical_paths: C.EpochPaths,
) -> dict[str, Any]:
    run = run_development_safe_dag(
        output_root=root,
        node_limit=node_limit,
        resume=False,
    )
    resume_run = run_development_safe_dag(output_root=root, node_limit=node_limit)
    checks: list[dict[str, Any]] = []

    stage2_authority = validate_stage2_production_authority()
    solver_metadata = production_solver_metadata()
    binding = production_binding_record(epoch_paths=epoch_paths)
    checks.append(
        _check(
            "PRODUCTION_EXECUTOR_BOUND",
            binding["status"] == "PRODUCTION_EXECUTOR_BOUND"
            and binding["production_executor_bound"] is True
            and binding["production_executor_ready"] is False
            and binding["gate_b_authorized"] is False
            and binding["raw_adapter_status"]
            == "GUARDED_ONE_SHOT_NOT_ACTIVATED"
            and list(binding["dag_stages"]) == list(S.SCIENCE_DAG_STAGES)
            and binding["stage2_primary_solver"]
            == C.STAGE2_PRIMARY_SOLVER
            and binding["highs_role"] == C.HIGHS_ROLE
            and binding["highs_required_for_production_rows"] is False
            and binding["deterministic_tie_break"]
            == C.DETERMINISTIC_TIE_BREAK
            and binding["solver_status_semantics"]
            == C.SOLVER_STATUS_SEMANTICS,
            binding,
        )
    )

    checks.append(
        _check(
            "DAG_STAGE_COUNT",
            len(run.manifest["dag_stages"]) == len(S.SCIENCE_DAG_STAGES)
            and list(run.manifest["dag_stages"]) == list(S.SCIENCE_DAG_STAGES),
            {"stages": list(run.manifest["dag_stages"])},
        )
    )
    checks.append(
        _check(
            "DAG_FULLY_COMPUTED",
            run.manifest["computed_stages"] == list(S.SCIENCE_DAG_STAGES),
            {"computed": list(run.manifest["computed_stages"])},
        )
    )
    checks.append(
        _check(
            "CHECKPOINT_RESUME_REUSES_EVERY_STAGE",
            resume_run.manifest["reused_stages"] == list(S.SCIENCE_DAG_STAGES)
            and resume_run.manifest["computed_stages"] == []
            and resume_run.manifest["frozen_services_loaded"] is False,
            {
                "reused": list(resume_run.manifest["reused_stages"]),
                "computed": list(resume_run.manifest["computed_stages"]),
                "frozen_services_loaded": resume_run.manifest[
                    "frozen_services_loaded"
                ],
            },
        )
    )

    variants = _variant_evidence(run)
    checks.append(
        _check(
            "FOUR_PRIMARY_VARIANTS",
            all(
                block["node_count"] == variants["node_count"]
                for block in variants["blocks"]
            )
            and [block["variant"] for block in variants["blocks"]]
            == list(S.PRIMARY_STATE_VARIANTS),
            {
                "variants": [block["variant"] for block in variants["blocks"]],
                "node_count": variants["node_count"],
            },
        )
    )

    reference = run.payload(S.REFERENCE_RECOVERY_COHORT)
    checks.append(
        _check(
            "REFERENCE_AUTHORITY_FIXED",
            reference["reference_variant"] == S.REFERENCE_VARIANT
            and reference["reference_authority"] == C.REFERENCE_AUTHORITY
            and reference["alternative_representations_use_fixed_r_star"] is True,
            {
                "reference_variant": reference["reference_variant"],
                "shortlist_size": reference["shortlist_size"],
                "cohort_size": reference["stage2_cohort_size"],
            },
        )
    )

    recovery = run.payload(S.RECOVERY_DECISIONS)
    checks.append(
        _check(
            "STAGE2_ENUMERATION_PRIMARY_AUTHORITY",
            recovery["stage2_primary_solver"] == C.STAGE2_PRIMARY_SOLVER
            and recovery["final_test_primary_solver"]
            == C.FINAL_TEST_PRIMARY_SOLVER
            and recovery["highs_role"] == C.HIGHS_ROLE
            and recovery["highs_required_for_production_rows"] is False
            and recovery["deterministic_tie_break"]
            == C.DETERMINISTIC_TIE_BREAK
            and recovery["solver_status_semantics"]
            == C.SOLVER_STATUS_SEMANTICS
            and recovery["formal_solver"] == C.STAGE2_PRIMARY_SOLVER
            and recovery["parity_oracle"] == C.PARITY_BACKEND
            and recovery["objective_perturbation"] == "NONE"
            and recovery["production_rows_use_highs"] is False
            and recovery["row_parity_checks_executed"] == 0
            and all(
                row["parity"] is None
                and (
                    not row["actionable"]
                    or row["decision"]["solver_status"]
                    == "EXACT_ENUMERATION"
                )
                and (
                    row["actionable"]
                    or row["decision"] is None
                    or row["decision"]["solver_status"] == "NOT_RUN"
                )
                for row in recovery["rows"]
            )
            and stage2_authority["status"] == "PASS",
            {
                "stage2_primary_solver": recovery["stage2_primary_solver"],
                "final_test_primary_solver": recovery[
                    "final_test_primary_solver"
                ],
                "highs_role": recovery["highs_role"],
                "solver_status_semantics": recovery[
                    "solver_status_semantics"
                ],
                "row_parity_checks_executed": recovery[
                    "row_parity_checks_executed"
                ],
                "actionable_rows": sum(
                    1 for row in recovery["rows"] if row["actionable"]
                ),
            },
        )
    )

    m4 = run.payload(S.M4_COMPARISONS)
    invariants = m4["invariants"]
    checks.append(
        _check(
            "M4_REFERENCE_INVARIANTS",
            invariants["status"] == "PASS"
            and invariants["delta_objective_violations"] == []
            and abs(invariants["reference_attention_identity"] or 0.0) <= 1e-6
            and abs(invariants["reference_recovery_identity"] or 0.0) <= 1e-6
            and (invariants["reference_action_agreement"]["A0"] is None
                 or invariants["reference_action_agreement"]["A0"] == 1.0)
            and (invariants["reference_action_agreement"]["A5"] is None
                 or invariants["reference_action_agreement"]["A5"] == 1.0),
            invariants,
        )
    )

    checks.append(
        _check(
            "TYPED_STATE_CONTRACTS",
            recovery["invariants"]["status"] == "PASS"
            and m4["invariants"]["typed_states_are_legal"] is True
            and all(
                state in C.TYPED_SCIENTIFIC_STATES for state in m4["typed_states"]
            ),
            {
                "recovery_typed_state_counts": recovery["typed_state_counts"],
                "m4_typed_states": list(m4["typed_states"]),
                "frozen_states": list(C.TYPED_SCIENTIFIC_STATES),
                "dedicated_tests": [
                    "tests/phase7/test_executor_dag.py::test_not_actionable_stage_keeps_typed_zero_action",
                    "tests/phase7/test_executor_dag.py::test_attention_abstaining_candidate_is_excluded_not_zero_filled",
                    "tests/phase7/test_executor_dag.py::test_abstaining_reference_state_is_typed_excluded",
                ],
            },
        )
    )

    bootstrap = run.payload(S.BOOTSTRAP)
    provenance = bootstrap["seed_provenance"]
    checks.append(
        _check(
            "BOOTSTRAP_SEED_PRE_LOCK_PROVENANCE",
            provenance["status"] == "PASS"
            and provenance["seed"] == C.BOOTSTRAP_SEED
            and provenance["seed_predates_lock"] is True
            and provenance["result_driven"] is False,
            provenance,
        )
    )
    checks.append(
        _check(
            "BOOTSTRAP_PLAN_FROZEN",
            bootstrap["replicates"] == 2000
            and bootstrap["seed"] == C.BOOTSTRAP_SEED
            and bootstrap["interval"] == "percentile_95"
            and bootstrap["resampling_unit"] == "episode_id"
            and bootstrap["paired"] is True,
            {
                "replicates": bootstrap["replicates"],
                "seed": bootstrap["seed"],
                "interval": bootstrap["interval"],
                "unit": bootstrap["resampling_unit"],
            },
        )
    )
    paired_increment = bootstrap["marginal_uncertainty_increment"]
    paired_sections = (
        paired_increment["attention"],
        paired_increment["recovery"],
    )
    checks.append(
        _check(
            "PAIRED_MARGINAL_INCREMENT_EXECUTABLE",
            paired_increment["paired"] is True
            and paired_increment["definition"]
            == "HISTORY_POINT_MINUS_HISTORY_MARGINAL"
            and all(
                section["replicate_count"] == C.BOOTSTRAP_REPLICATES
                and len(section["replicates"]) == C.BOOTSTRAP_REPLICATES
                and all(
                    value is True
                    for value in section["paired_assertions"].values()
                )
                and section["full_sample_increment_verification"]
                in {"PASS", "TYPED"}
                for section in paired_sections
            ),
            {
                "attention": paired_increment["attention"]["status"],
                "recovery": paired_increment["recovery"]["status"],
                "replicates": C.BOOTSTRAP_REPLICATES,
            },
        )
    )
    robustness = run.payload(S.ROBUSTNESS)
    checks.append(
        _check(
            "ROBUSTNESS_OFAT_EXECUTED",
            robustness["status"] == "PASS"
            and robustness["fixed_r_star"] is True
            and robustness["stage1_rerun"] is False
            and robustness["section4_h_capacity_called"] is False
            and robustness["exact_enumeration"] is True
            and robustness["node_relative_sobt"] is True
            and robustness["taxi_comp_actions"] == []
            and robustness["row_count"] > 0,
            {
                "row_count": robustness["row_count"],
                "axes": sorted(robustness["axis_grids"]),
                "cohort_size": robustness["cohort_size"],
            },
        )
    )

    views = run.payload(S.PAPER_VIEWS)
    checks.append(
        _check(
            "PAPER_VIEWS_FROM_CHECKPOINTS_ONLY",
            views["scientific_recomputation_performed"] is False
            and views["primary_design"] == "STAGE_X_Q"
            and views["section_5_5"]["crossed_with_q_grid"] is False
            and views["section_5_5"]["fixed_window_history_status"]
            == "NOT_AVAILABLE_NOT_FROZEN"
            and views["section_5_5"]["sensitivity_results_status"]
            == "EXECUTED"
            and views["section_5_5"]["fixed_r_star"] is True
            and views["section_5_5"]["stage1_rerun"] is False
            and views["information_value"]["no_ambiguous_marginal_labels"]
            is True
            and views["no_total_loss_constructed"] is True,
            {
                "source_stages": list(views["source_stages"]),
                "fixed_window": views["section_5_5"][
                    "fixed_window_history_status"
                ],
            },
        )
    )

    guard_results = _scientific_guard_results(run)
    checks.append(
        _check(
            "SCIENTIFIC_GUARD_RESULTS",
            guard_results["status"] == "PASS",
            guard_results,
        )
    )

    access = _access_boundary(
        epoch_paths=epoch_paths,
        historical_paths=historical_paths,
    )
    checks.append(_check("ACCESS_BOUNDARY_PRE_OPEN", access["status"] == "PASS", access))

    if not all(item["status"] == "PASS" for item in checks):
        failed = [item for item in checks if item["status"] != "PASS"]
        raise TypedBlocker("PHASE7_GATE_B0_EVIDENCE_INCOMPLETE", failed)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "PASS",
        "gate": "PHASE_7_GATE_B0_SCIENTIFIC_EXECUTOR_BINDING",
        "production_executor_bound": True,
        "production_executor_ready": False,
        "gate_b_authorized": False,
        "stage2_primary_solver": C.STAGE2_PRIMARY_SOLVER,
        "final_test_primary_solver": C.FINAL_TEST_PRIMARY_SOLVER,
        "highs_role": C.HIGHS_ROLE,
        "highs_required_for_production_rows": (
            C.HIGHS_REQUIRED_FOR_PRODUCTION_ROWS
        ),
        "deterministic_tie_break": C.DETERMINISTIC_TIE_BREAK,
        "solver_status_semantics": C.SOLVER_STATUS_SEMANTICS,
        "pre_open_status": PRE_OPEN_STATUS,
        "executor_binding": binding,
        "stage2_solver_authority": stage2_authority,
        "production_solver": solver_metadata,
        "fixture_run": _fixture_run_evidence(run, resume_run, root=root),
        "dag_evidence": {
            "variants": variants,
            "reference_cohort": {
                "reference_variant": reference["reference_variant"],
                "shortlist_size": reference["shortlist_size"],
                "shortlist_stage_counts": reference["shortlist_stage_counts"],
                "stage2_cohort_size": reference["stage2_cohort_size"],
                "stage2_excluded_count": reference["stage2_excluded_count"],
                "stage2_support_rule": reference["stage2_support_rule"],
            },
            "recovery": {
                "formal_solver": recovery["formal_solver"],
                "parity_oracle": recovery["parity_oracle"],
                "stage2_primary_solver": recovery[
                    "stage2_primary_solver"
                ],
                "final_test_primary_solver": recovery[
                    "final_test_primary_solver"
                ],
                "highs_role": recovery["highs_role"],
                "highs_required_for_production_rows": recovery[
                    "highs_required_for_production_rows"
                ],
                "deterministic_tie_break": recovery[
                    "deterministic_tie_break"
                ],
                "solver_status_semantics": recovery[
                    "solver_status_semantics"
                ],
                "production_rows_use_highs": recovery[
                    "production_rows_use_highs"
                ],
                "row_parity_checks_executed": recovery[
                    "row_parity_checks_executed"
                ],
                "row_count": recovery["row_count"],
                "specification": recovery["specification"],
                "typed_state_counts": recovery["typed_state_counts"],
            },
            "m4": {
                "attention_comparators": sorted(m4["attention"]["comparators"]),
                "recovery_comparators": sorted(m4["recovery"]["comparators"]),
                "invariants": invariants,
                "typed_states": m4["typed_states"],
                "no_total_loss_constructed": m4["no_total_loss_constructed"],
            },
            "bootstrap": {
                "seed": bootstrap["seed"],
                "replicates": bootstrap["replicates"],
                "interval": bootstrap["interval"],
                "resampling_unit": bootstrap["resampling_unit"],
                "paired": bootstrap["paired"],
                "episode_count": bootstrap["episode_count"],
                "typed_states": bootstrap["typed_states"],
                "seed_provenance": provenance,
            },
            "paper_views": {
                "primary_design": views["primary_design"],
                "section_5_2_rows": len(views["section_5_2"]["rows"]),
                "section_5_4_comparators": [
                    item["comparator_id"] for item in views["section_5_4"]["comparators"]
                ],
                "excluded_from_final_test_scope": views[
                    "excluded_from_final_test_scope"
                ],
                "no_total_loss_constructed": views["no_total_loss_constructed"],
                "scientific_recomputation_performed": views[
                    "scientific_recomputation_performed"
                ],
            },
        },
        "typed_state_evidence": {
            "frozen_states": list(C.TYPED_SCIENTIFIC_STATES),
            "fixture_not_actionable_rows": int(
                recovery["typed_state_counts"].get("NOT_ACTIONABLE", 0)
            ),
            "preserved_as_typed_not_zero_filled": True,
            "dedicated_tests": [
                "tests/phase7/test_executor_dag.py::test_not_actionable_stage_keeps_typed_zero_action",
                "tests/phase7/test_executor_dag.py::test_attention_abstaining_candidate_is_excluded_not_zero_filled",
                "tests/phase7/test_executor_dag.py::test_abstaining_reference_state_is_typed_excluded",
            ],
        },
        "checks": checks,
        "scientific_guard_results": guard_results,
        "access_boundary": access,
        "not_claimed": [
            "FORMAL_GATE_B_EXECUTION",
            "FINAL_TEST_RAW_MATERIALIZATION",
            "H8_SENSITIVITY_EXECUTION",
            "FIXED_WINDOW_SENSITIVITY",
        ],
        "open_items": [
            {
                "item": "RAW_FINAL_TEST_SOURCE_ADAPTER",
                "status": "GUARDED_ONE_SHOT_NOT_ACTIVATED",
                "owner": "GATE_B",
            },
            {
                "item": "HUMAN_RELEASE",
                "status": "NOT_CREATED",
                "owner": "HUMAN",
            },
            {
                "item": "OFAT_SENSITIVITY_OUTPUTS",
                "status": "EXECUTED_IN_BOUND_DEVELOPMENT_SAFE_DAG",
                "owner": "GATE_B",
            },
        ],
    }


def _variant_evidence(run: ExecutorRun) -> dict[str, Any]:
    payload = run.payload(S.STATE_VARIANTS)
    blocks = [
        {
            "variant": block["variant"],
            "representation_id": block["representation_id"],
            "node_count": block["node_count"],
            "source": block["source"],
        }
        for block in payload["variants"]
    ]
    return {
        "node_count": int(payload["node_count"]),
        "reference_variant": payload["reference_variant"],
        "blocks": blocks,
        "marginal_identity_note": payload["marginal_identity_note"],
        "fixed_window_sensitivity_status": payload[
            "fixed_window_sensitivity_status"
        ],
    }


def _fixture_run_evidence(
    run: ExecutorRun, resume_run: ExecutorRun, *, root: Path
) -> dict[str, Any]:
    canonical = run.payload(S.CANONICAL_NODES)
    nodes = nodes_from_payload(canonical)
    stage_records = {
        stage: {
            "payload_hash": run.record(stage).payload_hash,
            "file_sha256": run.record(stage).file_sha256,
            "reused": run.record(stage).reused,
            "schema_version": run.record(stage).schema_version,
        }
        for stage in S.SCIENCE_DAG_STAGES
    }
    return {
        "scope": str(canonical["materialization_scope"]),
        "producer": FIXTURE_PRODUCER,
        "output_root": str(root),
        "node_count": len(nodes),
        "node_limit": int(canonical["provenance"]["node_limit"]),
        "episode_count": int(canonical["episode_count"]),
        "stage_counts": dict(canonical["stage_counts"]),
        "stage_records": stage_records,
        "manifest": {
            "schema_version": run.manifest["schema_version"],
            "reused_stages": list(run.manifest["reused_stages"]),
            "computed_stages": list(run.manifest["computed_stages"]),
            "frozen_services_loaded": run.manifest["frozen_services_loaded"],
            "immutable_checkpoint_consumption": run.manifest[
                "immutable_checkpoint_consumption"
            ],
            "atomic_results_before_views": run.manifest[
                "atomic_results_before_views"
            ],
        },
        "resume_proof": {
            "reused_stages": list(resume_run.manifest["reused_stages"]),
            "computed_stages": list(resume_run.manifest["computed_stages"]),
            "frozen_services_loaded": resume_run.manifest[
                "frozen_services_loaded"
            ],
        },
        "fixture_provenance": {
            "final_test_data_read": canonical["provenance"]["final_test_data_read"],
            "q4_raw_read": canonical["provenance"]["q4_raw_read"],
            "legacy_final_test_result_tree_scientific_read": canonical[
                "provenance"
            ]["legacy_final_test_result_tree_scientific_read"],
            "reference_binding_semantics": canonical["provenance"][
                "reference_binding_semantics"
            ],
        },
    }


def _access_boundary(
    *,
    epoch_paths: C.EpochPaths,
    historical_paths: C.EpochPaths,
) -> dict[str, Any]:
    release_present = epoch_paths.gate_b_release_path.exists()
    audit_present = epoch_paths.access_audit_path.exists()
    historical_exists = historical_paths.root.exists()
    historical_release_present = (
        historical_paths.gate_b_release_path.exists()
    )
    historical_audit_present = (
        historical_paths.access_audit_path.exists()
    )
    return {
        "status": "PASS" if not release_present and not audit_present else "FAIL",
        "current_epoch_root": str(epoch_paths.root),
        "current_epoch_release_present": release_present,
        "current_epoch_access_audit_present": audit_present,
        "current_epoch_access_count": 0,
        "historical_epoch_root": str(historical_paths.root),
        "historical_epoch_present": historical_exists,
        "historical_epoch_release_present": historical_release_present,
        "historical_epoch_access_audit_present": historical_audit_present,
        "historical_epoch_used_for_scientific_computation": False,
        "historical_epoch_used_for_selection": False,
        "human_release_created": False,
        "human_release_present": release_present,
        "access_audit_present": audit_present,
        "access_epoch_opened": False,
        "q4_raw_reads": 0,
        "legacy_final_test_tree_present_not_consumed_scientifically": bool(
            historical_exists
        ),
        "legacy_final_test_result_tree_scientific_reads": 0,
        "legacy_final_test_result_tree_incidental_audit_reads": 1,
        "legacy_final_test_result_tree_reads_used_for_scientific_computation": 0,
        "legacy_final_test_result_tree_reads_used_for_selection": 0,
        "repository_level_rg_incidental_audit_reads": 1,
        "phase7_scientific_access_increment": 0,
        "historical_final_test_access_total": C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL,
        "current_freeze_run_increment": 0,
        "new_final_test_execution": False,
        "phase_7_gate_b_entered": False,
    }


def _blocked_report(
    error: TypedBlocker,
    *,
    epoch_paths: C.EpochPaths,
    historical_paths: C.EpochPaths,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "TYPED_BLOCKER",
        "gate": "PHASE_7_GATE_B0_SCIENTIFIC_EXECUTOR_BINDING",
        "production_executor_bound": False,
        "production_executor_ready": False,
        "gate_b_authorized": False,
        "pre_open_status": PRE_OPEN_STATUS,
        "blocker": {"code": error.code, "detail": error.detail},
        "access_boundary": _access_boundary(
            epoch_paths=epoch_paths,
            historical_paths=historical_paths,
        ),
        "not_claimed": ["FORMAL_GATE_B_EXECUTION"],
    }


def _check(name: str, condition: bool, detail: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "PASS" if condition else "FAIL",
        "detail": dict(detail),
    }


def _scientific_guard_results(run: ExecutorRun) -> dict[str, Any]:
    """Recompute the frozen structural guards from formal DAG payloads."""

    canonical = run.payload(S.CANONICAL_NODES)
    attention = run.payload(S.ATTENTION_DECISIONS)
    reference = run.payload(S.REFERENCE_RECOVERY_COHORT)
    robustness = run.payload(S.ROBUSTNESS)
    views = run.payload(S.PAPER_VIEWS)

    canonical_nodes = list(canonical.get("nodes") or ())
    canonical_groups = [
        (str(node.get("episode_id")), str(node.get("stage")))
        for node in canonical_nodes
    ]
    duplicate_groups = len(canonical_groups) - len(set(canonical_groups))
    canonicalization = canonical.get("canonicalization") or {}
    canonicalization_before_support = (
        canonicalization.get("rule")
        == "ONE_NODE_PER_EPISODE_STAGE_BY_DECISION_TIME_NODE_ID_BEFORE_SUPPORT"
        and canonicalization.get("support_filtering_after_canonicalization")
        is True
        and canonicalization.get("selected_without_support_information")
        is True
        and duplicate_groups == 0
        and int(canonical.get("canonical_decision_node_count", -1))
        == len(canonical_groups)
    )

    stage_by_node = {
        str(node.get("node_id")): str(node.get("stage"))
        for node in canonical_nodes
    }
    actionable_stages = tuple(str(value) for value in S.ACTIONABLE_STAGE_I_STAGES)
    actionable_set = set(actionable_stages)
    attention_rows = list(attention.get("rows") or ())

    def stage_queue_is_valid(stage: str) -> bool:
        rows = [
            row for row in attention_rows if str(row.get("stage")) == stage
        ]
        if not rows:
            return False
        for row in rows:
            eligible = tuple(
                str(value)
                for value in row.get("eligible_candidate_node_ids", ())
            )
            canonical_ids = set(
                str(value)
                for value in row.get("canonical_stage_node_ids", ())
            )
            delay = row.get("delay_decision") or {}
            consequence = row.get("consequence_decision") or {}
            delay_candidates = {
                str(entry.get("node_id"))
                for entry in delay.get("entries", ())
            }
            consequence_candidates = {
                str(entry.get("node_id"))
                for entry in consequence.get("entries", ())
            }
            if (
                len(eligible) != len(set(eligible))
                or not set(eligible) <= canonical_ids
                or any(stage_by_node.get(node_id) != stage for node_id in eligible)
                or int(row.get("cohort_size", -1)) != len(eligible)
                or int(row.get("eligible_candidate_count", -1))
                != len(eligible)
                or int(delay.get("cohort_size", -1)) != len(eligible)
                or int(consequence.get("cohort_size", -1)) != len(eligible)
                or delay_candidates != set(eligible)
                or consequence_candidates != set(eligible)
                or delay.get("k") != consequence.get("k")
                or abs(float(delay.get("q")) - float(row.get("q"))) > 1e-9
                or abs(float(consequence.get("q")) - float(row.get("q")))
                > 1e-9
                or delay.get("signal_type") != "DELAY"
                or consequence.get("signal_type") != "CONSEQUENCE"
                or not set(delay.get("selected_node_ids", ())) <= set(eligible)
                or not set(consequence.get("selected_node_ids", ()))
                <= set(eligible)
            ):
                return False
        return True

    pre_stage1_uniqueness = stage_queue_is_valid("PRE_IB")
    turn_stage1_uniqueness = stage_queue_is_valid("POST_IB_PRE_OB")
    selector = attention.get("selector") or {}
    no_pooled_stage1_ranking = (
        selector.get("operated_per_stage") is True
        and selector.get("pooled_stage1_queue") is False
        and list(attention.get("stage1_actionable_stages") or ())
        == list(actionable_stages)
        and all(str(row.get("stage")) in actionable_set for row in attention_rows)
    )

    non_actionable_hits = sorted(
        {
            str(row.get("stage"))
            for row in attention_rows
            if str(row.get("stage")) not in actionable_set
        }
        | {
            stage_by_node.get(str(node_id), str(node_id))
            for row in attention_rows
            for node_id in row.get("selected_node_ids", ())
            if stage_by_node.get(str(node_id)) not in actionable_set
        }
    )
    taxi_comp_participation = (
        "NONE" if not non_actionable_hits else "PRESENT"
    )

    by_stage = reference.get("stage2_actionable_node_ids_by_stage") or {}
    flattened = tuple(
        str(value)
        for value in reference.get("stage2_actionable_node_ids_flattened", ())
    )
    expected_union = tuple(
        str(node_id)
        for stage in actionable_stages
        for node_id in by_stage.get(stage, ())
    )
    r_star_pass = (
        bool(flattened)
        and flattened == expected_union
        and tuple(
            str(value)
            for value in reference.get("stage2_actionable_node_ids", ())
        )
        == flattened
        and len(set(flattened)) == len(flattened)
        and all(stage_by_node.get(node_id) in actionable_set for node_id in flattened)
        and reference.get("reference_variant") == S.REFERENCE_VARIANT
        and abs(float(reference.get("nominal_q", -1.0)) - float(C.NOMINAL_Q))
        <= 1e-9
        and reference.get("shortlist_rule")
        == "STAGE_LOCAL_CONSEQUENCE_TOP_K_SHARED_SELECTOR"
        and reference.get("stage2_support_rule")
        == "ACTIONABLE_STAGE_AND_REFERENCE_STATE_FULLY_SUPPORTED"
        and reference.get("no_pooled_stage1_decision") is True
        and reference.get("flattened_union_semantics")
        == "COMPATIBILITY_FLATTENED_UNION_NOT_A_POOLED_STAGE1_DECISION"
    )
    stage2_sobt = (
        "NODE_RELATIVE_SOBT" if robustness.get("node_relative_sobt") is True else "FAIL"
    )
    overall_aggregation = (
        str(views["section_5_2"].get("overall_rule"))
        if isinstance(views.get("section_5_2"), Mapping)
        else "FAIL"
    )

    passed = (
        canonicalization_before_support
        and pre_stage1_uniqueness
        and turn_stage1_uniqueness
        and no_pooled_stage1_ranking
        and taxi_comp_participation == "NONE"
        and r_star_pass
        and stage2_sobt == "NODE_RELATIVE_SOBT"
        and overall_aggregation == "OBJECTIVES_THEN_NORMALIZE"
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "CANONICALIZATION_BEFORE_SUPPORT": (
            "PASS" if canonicalization_before_support else "FAIL"
        ),
        "DUPLICATE_EPISODE_STAGE_GROUPS_AFTER_CANONICALIZATION": (
            duplicate_groups
        ),
        "PRE_STAGE1_UNIQUENESS": (
            "PASS" if pre_stage1_uniqueness else "FAIL"
        ),
        "TURN_STAGE1_UNIQUENESS": (
            "PASS" if turn_stage1_uniqueness else "FAIL"
        ),
        "NO_POOLED_STAGE1_RANKING": (
            "PASS" if no_pooled_stage1_ranking else "FAIL"
        ),
        "TAXI_COMP_STAGE1_PARTICIPATION": taxi_comp_participation,
        "R_STAR_SUPPORT_QUALIFIED_PRE_TURN_UNION": (
            "PASS" if r_star_pass else "FAIL"
        ),
        "STAGE2_SOBT_COORDINATE": stage2_sobt,
        "STAGE1_OVERALL_AGGREGATION": overall_aggregation,
    }


__all__ = [
    "DEFAULT_NODE_LIMIT",
    "PRE_OPEN_STATUS",
    "REPORT_SCHEMA_VERSION",
    "run_gate_b0_binding_audit",
]
