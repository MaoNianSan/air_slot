"""``M4_COMPARISONS``: stage-local attention and fixed-cohort recovery."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.M4.evaluation import (
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)
from model.PRE.decision_environment import action_stage_class
from model.common.enums import OperationalStage

from .. import constants as C
from ..errors import TypedBlocker, _require
from . import stages as S
from .attention_decisions import attention_decision
from .codec import recovery_decision_from_payload
from .consequence_variants import signals_by_variant
from .reference_cohort import actionable_cohort
from .recovery_decisions import rows_by_variant as recovery_rows_by_variant

N_A_NOT_DEFINED = "N/A_NOT_DEFINED"
TOLERANCE = C.M3_NUMERICAL_COMPARISON_TOLERANCE


def build_m4_comparisons(
    consequence_variants: Mapping[str, Any],
    attention_decisions: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate PRE and TURN independently, then aggregate objective values."""

    cohort = actionable_cohort(reference_cohort)
    _require(bool(cohort), "PHASE7_M4_RECOVERY_COHORT_EMPTY")
    attention = _attention_block(
        consequence_variants, attention_decisions, reference_cohort
    )
    recovery = _recovery_block(
        reference_cohort, recovery_decisions, cohort=cohort
    )
    invariants = _invariants(attention, recovery, recovery_decisions, cohort)
    typed_candidates = [
        attention["self_reference"].get("typed_state"),
        recovery["self_reference"].get("typed_state"),
    ]
    for block in (attention, recovery):
        typed_candidates.extend(
            record.get("typed_state")
            for record in block["comparators"].values()
        )
    typed_states = sorted({value for value in typed_candidates if value})
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "cohort_id": str(reference_cohort["cohort_id"]),
        "cohort_node_ids": list(cohort),
        "cohort_size": len(cohort),
        "nominal_q": float(C.NOMINAL_Q),
        "stage1_actionable_stages": list(S.ACTIONABLE_STAGE_I_STAGES),
        "one_stage1_decision_per_stage": True,
        "pooled_stage1_ranking_constructed": False,
        "reference_objective_basis": (
            "M3_FORMAL_HIGHS_OBJECTIVE_ON_FIXED_REFERENCE_COHORT"
        ),
        "stage2_information_comparison_uses_fixed_r_star": True,
        "alternative_representations_may_define_h_r_for_l_att": True,
        "priority_authority": {
            "consequence_based_priority_authority": "P^C = Phi_C(C^CU)",
            "delay_comparator": "P^D = E[D^TO | Omega^CS]",
            "delay_comparator_is_l_att_basis": False,
            "shared_stage1_selector": True,
            "stage_local_selector": True,
        },
        "attention": attention,
        "recovery": recovery,
        "invariants": invariants,
        "typed_states": typed_states,
        "no_total_loss_constructed": True,
    }


def _attention_block(
    consequence_variants: Mapping[str, Any],
    attention_decisions: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
) -> dict[str, Any]:
    reference_variant = S.REFERENCE_VARIANT
    q = float(C.NOMINAL_Q)
    cohort_id = str(reference_cohort["cohort_id"])
    reference_signals = signals_by_variant(
        consequence_variants, reference_variant
    )
    by_stage: dict[str, Any] = {}
    stage_self: dict[str, dict[str, Any]] = {}
    stage_bootstrap: dict[str, list[dict[str, Any]]] = {}

    for stage in S.ACTIONABLE_STAGE_I_STAGES:
        reference_decision = attention_decision(
            attention_decisions, reference_variant, stage, q, "CONSEQUENCE"
        )
        reference_candidates = tuple(
            sorted(entry.node_id for entry in reference_decision.entries)
        )
        reference_priority: dict[str, float] = {}
        for node_id in reference_candidates:
            signal = reference_signals.get(node_id)
            if signal is not None and signal[1].score is not None:
                reference_priority[node_id] = float(signal[1].score)
        reference_shortlist = tuple(
            entry.node_id for entry in reference_decision.entries if entry.selected
        )
        if len(reference_priority) != len(reference_candidates):
            self_record = _typed_record(
                typed_state=N_A_NOT_DEFINED,
                reason_codes=("PHASE7_ATTENTION_REFERENCE_PRIORITY_INCOMPLETE",),
                detail={
                    "stage": stage,
                    "candidate_count": len(reference_candidates),
                },
            )
        else:
            self_record = _evaluation_record(
                evaluate_attention_allocation(
                    cohort_id=f"{cohort_id}_{stage}",
                    reference_id=reference_variant,
                    comparator_id=reference_variant,
                    reference_decision=reference_decision,
                    comparator_decision=reference_decision,
                    reference_priority=reference_priority,
                )
            )
        stage_self[stage] = self_record

        comparators: dict[str, Any] = {}
        bootstrap_rows: dict[str, list[dict[str, Any]]] = {}
        for variant in S.COMPARATOR_VARIANTS:
            comparator_signals = signals_by_variant(
                consequence_variants, variant
            )
            decision = attention_decision(
                attention_decisions, variant, stage, q, "CONSEQUENCE"
            )
            candidates = tuple(sorted(entry.node_id for entry in decision.entries))
            if candidates != reference_candidates:
                comparators[variant] = _typed_record(
                    typed_state=N_A_NOT_DEFINED,
                    reason_codes=(
                        "PHASE7_ATTENTION_COMMON_BASIS_CANDIDATE_QUEUE_MISMATCH",
                    ),
                    detail={
                        "stage": stage,
                        "reference_candidate_count": len(reference_candidates),
                        "comparator_candidate_count": len(candidates),
                        "entered_candidates": sorted(
                            set(candidates) - set(reference_candidates)
                        ),
                        "exited_candidates": sorted(
                            set(reference_candidates) - set(candidates)
                        ),
                    },
                )
                continue
            if len(reference_priority) != len(reference_candidates):
                comparators[variant] = _typed_record(
                    typed_state=N_A_NOT_DEFINED,
                    reason_codes=("PHASE7_ATTENTION_REFERENCE_PRIORITY_INCOMPLETE",),
                    detail={"stage": stage, "candidate_count": len(reference_candidates)},
                )
                continue
            evaluation = evaluate_attention_allocation(
                cohort_id=f"{cohort_id}_{stage}",
                reference_id=reference_variant,
                comparator_id=variant,
                reference_decision=reference_decision,
                comparator_decision=decision,
                reference_priority=reference_priority,
            )
            comparators[variant] = _evaluation_record(evaluation)
            comparator_shortlist = set(evaluation.comparator_shortlist)
            bootstrap_rows[variant] = [
                {
                    "stage": stage,
                    "node_id": node_id,
                    "episode_id": reference_signals[node_id][1].episode_id,
                    "chain_id": reference_signals[node_id][1].chain_id,
                    "reference_priority": reference_priority[node_id],
                    "reference_score": float(
                        reference_signals[node_id][1].score
                    ),
                    "comparator_score": float(
                        comparator_signals[node_id][1].score
                    ),
                    "support_mass": float(
                        reference_signals[node_id][1].comparison_support_mass
                    ),
                    "support_threshold": float(
                        reference_signals[node_id][1].comparison_support_threshold
                    ),
                    "in_reference_shortlist": node_id in set(reference_shortlist),
                    "in_comparator_shortlist": node_id in comparator_shortlist,
                }
                for node_id in reference_candidates
            ]
        by_stage[stage] = {
            "stage_class": action_stage_class(
                OperationalStage(stage)
            ),
            "capacity": {
                "q": q,
                "k": int(reference_decision.k),
                "cohort_size": int(reference_decision.cohort_size),
                "selector": "M3_STAGE1_SHARED_SELECTOR",
                "signal": "P^C = Phi_C(C^CU)",
            },
            "reference_candidate_node_ids": list(reference_candidates),
            "reference_shortlist_node_ids": list(reference_shortlist),
            "reference_priority": dict(reference_priority),
            "self_reference": self_record,
            "comparators": comparators,
            "bootstrap_rows": bootstrap_rows,
        }
        stage_bootstrap[stage] = bootstrap_rows

    self_aggregate = _aggregate_records(
        [stage_self[stage] for stage in S.ACTIONABLE_STAGE_I_STAGES],
        stage_scope=S.ACTIONABLE_STAGE_I_STAGES,
    )
    comparators_aggregate: dict[str, Any] = {}
    bootstrap_aggregate: dict[str, list[dict[str, Any]]] = {}
    for variant in S.COMPARATOR_VARIANTS:
        records = [
            by_stage[stage]["comparators"][variant]
            for stage in S.ACTIONABLE_STAGE_I_STAGES
        ]
        comparators_aggregate[variant] = _aggregate_records(
            records, stage_scope=S.ACTIONABLE_STAGE_I_STAGES
        )
        bootstrap_aggregate[variant] = [
            row
            for stage in S.ACTIONABLE_STAGE_I_STAGES
            for row in stage_bootstrap[stage].get(variant, ())
        ]
    return {
        "aggregation": "STAGE_OBJECTIVES_THEN_NORMALIZE",
        "pooled_stage1_ranking": False,
        "stage_order": list(S.ACTIONABLE_STAGE_I_STAGES),
        "by_stage": by_stage,
        "self_reference": self_aggregate,
        "comparators": comparators_aggregate,
        "bootstrap_rows": bootstrap_aggregate,
        "reference_candidate_node_ids": [
            node_id
            for stage in S.ACTIONABLE_STAGE_I_STAGES
            for node_id in by_stage[stage]["reference_candidate_node_ids"]
        ],
        "reference_shortlist_node_ids": [
            node_id
            for stage in S.ACTIONABLE_STAGE_I_STAGES
            for node_id in by_stage[stage]["reference_shortlist_node_ids"]
        ],
    }


def _aggregate_records(
    records: Sequence[Mapping[str, Any]], *, stage_scope: Sequence[str]
) -> dict[str, Any]:
    if len(records) != len(stage_scope):
        return _typed_record(
            typed_state=N_A_NOT_DEFINED,
            reason_codes=("PHASE7_ATTENTION_STAGE_RECORD_MISSING",),
            detail={"stage_scope": list(stage_scope)},
        )
    if any(record.get("record_kind") != "EVALUATED" for record in records):
        return _typed_record(
            typed_state=N_A_NOT_DEFINED,
            reason_codes=("PHASE7_ATTENTION_STAGE_EVALUATION_TYPED",),
            detail={"stage_scope": list(stage_scope)},
        )
    reference = sum(
        float(record["reference_attention_value"]) for record in records
    )
    comparator = sum(
        float(record["comparator_attention_value"]) for record in records
    )
    delta = reference - comparator
    return {
        "record_kind": "EVALUATED",
        "typed_state": None,
        "reference_attention_value": reference,
        "comparator_attention_value": comparator,
        "L_att": None if reference <= 0.0 else delta / reference,
        "overlap_count": sum(int(record.get("overlap_count", 0)) for record in records),
        "entered": [
            value for record in records for value in record.get("entered", ())
        ],
        "displaced": [
            value for record in records for value in record.get("displaced", ())
        ],
        "kendall_tau": None,
        "spearman_rho": None,
        "mean_rank_displacement": None,
        "diagnostics": {
            "aggregation": "OBJECTIVE_THEN_NORMALIZE",
            "stage_scope": list(stage_scope),
        },
        "reference_shortlist": [
            value
            for record in records
            for value in record.get("reference_shortlist", ())
        ],
        "comparator_shortlist": [
            value
            for record in records
            for value in record.get("comparator_shortlist", ())
        ],
        "status": "SUPPORTED",
        "reason_codes": [],
    }


def _recovery_block(
    reference_cohort: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    *,
    cohort: Sequence[str],
) -> dict[str, Any]:
    reference_variant = S.REFERENCE_VARIANT
    cohort_id = str(reference_cohort["cohort_id"])
    reference_rows = recovery_rows_by_variant(recovery_decisions, reference_variant)
    reference_tables = recovery_decisions["reference_objectives"]
    reference_actions: dict[str, float] = {}
    reference_values: dict[str, float] = {}
    reference_objectives: dict[tuple[str, float], float] = {}
    missing_reference: list[str] = []
    for node_id in cohort:
        row = reference_rows.get(node_id)
        decision = None if row is None else row.get("decision")
        if decision is None:
            missing_reference.append(node_id)
            continue
        resolved = recovery_decision_from_payload(decision)
        if resolved.u_star is None or resolved.recoverable_value is None:
            missing_reference.append(node_id)
            continue
        reference_actions[node_id] = float(resolved.u_star)
        reference_values[node_id] = float(resolved.recoverable_value)
        table = reference_tables.get(node_id)
        if table is None:
            raise TypedBlocker("PHASE7_M4_REFERENCE_OBJECTIVE_TABLE_MISSING", node_id)
        for action, objective in table["objective_by_action"]:
            reference_objectives[(node_id, float(action))] = float(objective)

    if missing_reference:
        self_record = _typed_record(
            typed_state=N_A_NOT_DEFINED,
            reason_codes=("PHASE7_M4_REFERENCE_DECISION_MISSING",),
            detail={"node_ids": sorted(missing_reference)},
        )
    else:
        self_record = _evaluation_record(
            evaluate_recovery_loss(
                cohort_id=cohort_id,
                reference_id=reference_variant,
                comparator_id=reference_variant,
                fixed_cohort=tuple(cohort),
                reference_actions=reference_actions,
                comparator_actions=reference_actions,
                reference_objectives=reference_objectives,
                reference_recoverable_values=reference_values,
            )
        )

    comparators: dict[str, Any] = {}
    bootstrap_rows: dict[str, list[dict[str, Any]]] = {}
    for variant in S.COMPARATOR_VARIANTS:
        rows = recovery_rows_by_variant(recovery_decisions, variant)
        actions: dict[str, float] = {}
        missing: list[str] = []
        for node_id in cohort:
            row = rows.get(node_id)
            decision = None if row is None else row.get("decision")
            resolved = (
                None
                if decision is None
                else recovery_decision_from_payload(decision)
            )
            if resolved is None or resolved.u_star is None:
                missing.append(node_id)
                continue
            actions[node_id] = float(resolved.u_star)
        if missing or missing_reference:
            comparators[variant] = _typed_record(
                typed_state=N_A_NOT_DEFINED,
                reason_codes=(
                    "PHASE7_M4_COMPARATOR_DECISION_INCOMPLETE_ON_FIXED_COHORT",
                ),
                detail={
                    "missing_node_ids": sorted(
                        set(missing) | set(missing_reference)
                    )
                },
            )
            continue
        evaluation = evaluate_recovery_loss(
            cohort_id=cohort_id,
            reference_id=reference_variant,
            comparator_id=variant,
            fixed_cohort=tuple(cohort),
            reference_actions=reference_actions,
            comparator_actions=actions,
            reference_objectives=reference_objectives,
            reference_recoverable_values=reference_values,
        )
        comparators[variant] = _evaluation_record(evaluation)
        bootstrap_rows[variant] = [
            {
                "node_id": node_id,
                "episode_id": reference_rows[node_id]["episode_id"],
                "stage": reference_rows[node_id]["stage"],
                "reference_value": reference_values[node_id],
                "j_star": float(evaluation.reference_objectives[node_id]),
                "j_comparator": float(evaluation.comparator_objectives[node_id]),
                "delta_objective": float(evaluation.delta_objectives[node_id]),
                "reference_action": reference_actions[node_id],
                "comparator_action": actions[node_id],
            }
            for node_id in cohort
        ]

    return {
        "cohort_id": cohort_id,
        "cohort_size": len(cohort),
        "cohort_node_ids": list(cohort),
        "stage2_actionable_node_ids_by_stage": reference_cohort.get(
            "stage2_actionable_node_ids_by_stage", {}
        ),
        "stage2_actionable_node_ids_flattened": list(
            reference_cohort.get("stage2_actionable_node_ids_flattened", cohort)
        ),
        "reference_actions": reference_actions,
        "reference_recoverable_values": reference_values,
        "self_reference": self_record,
        "comparators": comparators,
        "bootstrap_rows": bootstrap_rows,
    }


def _invariants(
    attention: Mapping[str, Any],
    recovery: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    cohort: Sequence[str],
) -> dict[str, Any]:
    reference_rows = recovery_rows_by_variant(
        recovery_decisions, S.REFERENCE_VARIANT
    )
    tables = recovery_decisions["reference_objectives"]
    delta_violations: list[dict[str, Any]] = []
    for variant, record in recovery["comparators"].items():
        rows = recovery_rows_by_variant(recovery_decisions, variant)
        for node_id in cohort:
            row = rows.get(node_id)
            if row is None or row.get("decision") is None:
                continue
            reference_row = reference_rows.get(node_id)
            if reference_row is None or reference_row.get("decision") is None:
                continue
            reference_action = recovery_decision_from_payload(
                reference_row["decision"]
            ).u_star
            comparator_action = recovery_decision_from_payload(
                row["decision"]
            ).u_star
            table = {
                float(action): float(objective)
                for action, objective in tables[node_id]["objective_by_action"]
            }
            if reference_action is None or comparator_action is None:
                continue
            if comparator_action not in table or reference_action not in table:
                delta_violations.append(
                    {
                        "variant": variant,
                        "node_id": node_id,
                        "reason": "ACTION_NOT_IN_REFERENCE_OBJECTIVE_TABLE",
                    }
                )
                continue
            delta = table[comparator_action] - table[reference_action]
            if delta < -TOLERANCE:
                delta_violations.append(
                    {
                        "variant": variant,
                        "node_id": node_id,
                        "delta_objective": delta,
                    }
                )

    failures: list[str] = []

    def _check_reference_identity(
        record: Mapping[str, Any], field: str, expected: float
    ) -> None:
        value = record.get(field)
        if value is None:
            return
        if abs(float(value) - expected) > TOLERANCE:
            failures.append(f"{field}_REFERENCE_IDENTITY_VIOLATION")

    _check_reference_identity(attention["self_reference"], "L_att", 0.0)
    _check_reference_identity(recovery["self_reference"], "L_rec", 0.0)
    _check_reference_identity(recovery["self_reference"], "A0", 1.0)
    _check_reference_identity(recovery["self_reference"], "A5", 1.0)
    if delta_violations:
        failures.append("DELTA_OBJECTIVE_BELOW_NEGATIVE_TOLERANCE")
    if failures:
        raise TypedBlocker(
            "PHASE7_M4_REFERENCE_INVARIANT_VIOLATION",
            {
                "failures": sorted(set(failures)),
                "delta_violations": delta_violations,
            },
        )
    return {
        "status": "PASS",
        "reference_attention_identity": attention["self_reference"].get("L_att"),
        "reference_recovery_identity": recovery["self_reference"].get("L_rec"),
        "reference_action_agreement": {
            "A0": recovery["self_reference"].get("A0"),
            "A5": recovery["self_reference"].get("A5"),
        },
        "delta_objective_lower_bound": -TOLERANCE,
        "delta_objective_violations": delta_violations,
        "typed_states_are_legal": True,
    }


def _evaluation_record(evaluation: Any) -> dict[str, Any]:
    payload = evaluation.model_dump(mode="json")
    payload["typed_state"] = None
    payload["record_kind"] = "EVALUATED"
    if hasattr(evaluation, "contract_record"):
        payload["decision_evaluation"] = evaluation.contract_record().model_dump(
            mode="json"
        )
    return payload


def _typed_record(
    *,
    typed_state: str,
    reason_codes: Sequence[str],
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_kind": "TYPED",
        "typed_state": typed_state,
        "reason_codes": [str(code) for code in reason_codes],
        "detail": dict(detail or {}),
        "L_att": None,
        "L_rec": None,
        "A0": None,
        "A5": None,
        "decision_evaluation": None,
    }


__all__ = [
    "N_A_NOT_DEFINED",
    "build_m4_comparisons",
]
