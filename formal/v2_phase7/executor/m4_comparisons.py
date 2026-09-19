"""``M4_COMPARISONS``: common-basis attention and recovery evaluation.

Every comparison is formed on the frozen reference basis:

* ``L_att = delta A / A*`` with ``A*`` the consequence-based Stage-I value of the
  ``HISTORY_JOINT`` reference shortlist and ``delta A`` the value difference to
  the comparator shortlist under that same reference priority;
* ``L_rec = sum delta J / V_g*`` with every comparator action scored against the
  reference objective table ``J_i^*(u)`` on the fixed cohort ``R_g*``.

The two losses are always reported separately; no ``L_total`` is constructed.
A comparison is only defined when the frozen M4 common-basis preconditions
hold: identical eligible candidate queues for attention, and a complete
comparator action vector on the fixed cohort for recovery. Otherwise the record
is typed (``N/A_NOT_DEFINED``) with an explicit reason code instead of being
silently recomputed on a different cohort.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.M4.evaluation import (
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)
from .. import constants as C
from ..errors import TypedBlocker, _require
from . import stages as S
from .attention_decisions import attention_decision
from .consequence_variants import signals_by_variant
from .codec import recovery_decision_from_payload
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
    """Evaluate every primary comparator against the frozen reference basis."""

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
    typed_states = sorted(
        {value for value in typed_candidates if value}
    )
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
        "cohort_id": str(reference_cohort["cohort_id"]),
        "cohort_node_ids": list(cohort),
        "cohort_size": len(cohort),
        "nominal_q": float(C.NOMINAL_Q),
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
    reference_signals = signals_by_variant(consequence_variants, reference_variant)
    reference_decision = attention_decision(
        attention_decisions, reference_variant, q, "CONSEQUENCE"
    )
    reference_candidates = tuple(
        sorted(entry.node_id for entry in reference_decision.entries)
    )
    reference_priority: dict[str, float] = {}
    for node_id in reference_candidates:
        signals = reference_signals.get(node_id)
        if signals is None or signals[1].score is None:
            continue
        reference_priority[node_id] = float(signals[1].score)
    reference_shortlist = tuple(
        entry.node_id for entry in reference_decision.entries if entry.selected
    )
    self_value = (
        evaluate_attention_allocation(
            cohort_id=cohort_id,
            reference_id=reference_variant,
            comparator_id=reference_variant,
            reference_decision=reference_decision,
            comparator_decision=reference_decision,
            reference_priority=reference_priority,
        )
        if len(reference_priority) == len(reference_candidates)
        else None
    )
    self_record = (
        _evaluation_record(self_value)
        if self_value is not None
        else _typed_record(
            typed_state=N_A_NOT_DEFINED,
            reason_codes=("PHASE7_ATTENTION_REFERENCE_PRIORITY_INCOMPLETE",),
            detail={"candidate_count": len(reference_candidates)},
        )
    )

    comparators: dict[str, Any] = {}
    bootstrap_rows: dict[str, list[dict[str, Any]]] = {}
    for variant in S.COMPARATOR_VARIANTS:
        decision = attention_decision(
            attention_decisions, variant, q, "CONSEQUENCE"
        )
        candidates = tuple(sorted(entry.node_id for entry in decision.entries))
        if candidates != reference_candidates:
            comparators[variant] = _typed_record(
                typed_state=N_A_NOT_DEFINED,
                reason_codes=(
                    "PHASE7_ATTENTION_COMMON_BASIS_CANDIDATE_QUEUE_MISMATCH",
                ),
                detail={
                    "reference_candidate_count": len(reference_candidates),
                    "comparator_candidate_count": len(candidates),
                    "entered_candidates": sorted(set(candidates) - set(reference_candidates)),
                    "exited_candidates": sorted(set(reference_candidates) - set(candidates)),
                },
            )
            continue
        if len(reference_priority) != len(reference_candidates):
            comparators[variant] = _typed_record(
                typed_state=N_A_NOT_DEFINED,
                reason_codes=("PHASE7_ATTENTION_REFERENCE_PRIORITY_INCOMPLETE",),
                detail={"candidate_count": len(reference_candidates)},
            )
            continue
        evaluation = evaluate_attention_allocation(
            cohort_id=cohort_id,
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
                "node_id": node_id,
                "episode_id": reference_signals[node_id][1].episode_id,
                "reference_priority": reference_priority[node_id],
                "in_reference_shortlist": node_id in set(reference_shortlist),
                "in_comparator_shortlist": node_id in comparator_shortlist,
            }
            for node_id in reference_candidates
        ]

    return {
        "capacity": {
            "q": q,
            "k": int(reference_decision.k),
            "cohort_size": int(reference_decision.cohort_size),
            "selector": "M3_STAGE1_SHARED_SELECTOR",
            "signal": "P^C = Phi_C(C^CU)",
        },
        "reference_candidate_node_ids": list(reference_candidates),
        "reference_shortlist_node_ids": list(reference_shortlist),
        "reference_priority": {
            node_id: reference_priority[node_id]
            for node_id in reference_candidates
            if node_id in reference_priority
        },
        "self_reference": self_record,
        "comparators": comparators,
        "bootstrap_rows": bootstrap_rows,
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
                detail={"missing_node_ids": sorted(set(missing) | set(missing_reference))},
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

    reference_attention = attention["self_reference"]
    reference_recovery = recovery["self_reference"]
    failures: list[str] = []

    def _check_reference_identity(
        record: Mapping[str, Any], field: str, expected: float
    ) -> None:
        value = record.get(field)
        if value is None:
            return
        if abs(float(value) - expected) > TOLERANCE:
            failures.append(f"{field}_REFERENCE_IDENTITY_VIOLATION")

    _check_reference_identity(reference_attention, "L_att", 0.0)
    _check_reference_identity(reference_recovery, "L_rec", 0.0)
    _check_reference_identity(reference_recovery, "A0", 1.0)
    _check_reference_identity(reference_recovery, "A5", 1.0)
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
        "reference_attention_identity": reference_attention.get("L_att"),
        "reference_recovery_identity": reference_recovery.get("L_rec"),
        "reference_action_agreement": {
            "A0": reference_recovery.get("A0"),
            "A5": reference_recovery.get("A5"),
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
