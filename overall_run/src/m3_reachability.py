from __future__ import annotations

from typing import Any

import pandas as pd

ZERO_REACHABILITY_CLASSES = {
    "CODE_UNREACHABLE",
    "CONFIG_UNREACHABLE",
    "DATA_UNSUPPORTED_FAIL_CLOSED",
    "EMPIRICALLY_UNREACHED_IN_FAST",
}


def resolve_action_reachability(
    candidate_screen: pd.DataFrame,
    actions: dict[str, Any],
    scientific: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for action_id in actions:
        group = candidate_screen[candidate_screen["action_id"].astype(str).eq(action_id)]
        status = group.get("evaluation_status", pd.Series(index=group.index, dtype="string")).astype("string")
        physical_codes = group.get(
            "physical_rejection_codes", pd.Series(index=group.index, dtype="string")
        ).fillna("").astype(str)
        m2_supported = group.get(
            "m2_cost_supported", pd.Series(False, index=group.index)
        ).fillna(False).astype(bool)
        typed_failed = ~group.get(
            "gate_typed", pd.Series(True, index=group.index)
        ).fillna(False).astype(bool)
        unsupported = (
            ~m2_supported
            | physical_codes.str.contains(
                r"TYPED_GATE_(?:UNSUPPORTED|MISSING)|RESOURCE_STATE_MISSING",
                regex=True,
            )
        )
        scored_count = int(
            group.get("is_evaluated", pd.Series(False, index=group.index))
            .fillna(False)
            .astype(bool)
            .sum()
        )
        if scored_count:
            classification = ""
        elif group.empty:
            classification = "CODE_UNREACHABLE"
        elif int(unsupported.sum()) == len(group):
            classification = "DATA_UNSUPPORTED_FAIL_CLOSED"
        else:
            classification = "EMPIRICALLY_UNREACHED_IN_FAST"
        if classification and classification not in ZERO_REACHABILITY_CLASSES:
            raise RuntimeError(f"M3_ZERO_REACHABILITY_CLASS_INVALID:{classification}")
        rows.append({
            "action_id": action_id,
            "candidate_count": int(len(group)),
            "trigger_fail_count": int(status.eq("TRIGGER_INACTIVE").sum()),
            "value_gate_fail_count": int(
                status.isin(["DECISION_VALUE_REJECTED", "PRE_ACTION_COST_ZERO"]).sum()
            ),
            "typed_gate_fail_count": int(typed_failed.sum()),
            "unsupported_evidence_count": int(unsupported.sum()),
            "scored_count": scored_count,
            "zero_reachability_class": classification,
        })
    return pd.DataFrame(rows)
