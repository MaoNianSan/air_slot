from __future__ import annotations


def formal_feasibility_audit(rows) -> dict[str, int]:
    return {
        "candidate_cohort": len(rows),
        "numerically_evaluable_cohort": sum(bool(row.get("numerically_evaluable")) for row in rows),
        "formal_multi_action_cohort": sum(int(row.get("formal_action_count", 0)) >= 2 for row in rows),
        "baseline_only_formal_cohort": sum(int(row.get("formal_action_count", 0)) == 1 and row.get("a00_formal", False) for row in rows),
        "no_authoritative_decision_cohort": sum(not row.get("authoritative_decision_available", False) for row in rows),
    }


def lane_rates(rows) -> dict[str, float | None]:
    if not rows:
        return {name: None for name in (
            "FormalMultiActionRate", "FormalA00Rate", "BaselineOnlyFormalRate",
            "ConditionalRate", "ScenarioOnlyRate", "AbstainRate")}
    n = len(rows)
    return {
        "FormalMultiActionRate": sum(int(row.get("formal_action_count", 0)) >= 2 for row in rows) / n,
        "FormalA00Rate": sum(bool(row.get("a00_formal")) for row in rows) / n,
        "BaselineOnlyFormalRate": sum(int(row.get("formal_action_count", 0)) == 1 and row.get("a00_formal", False) for row in rows) / n,
        "ConditionalRate": sum(int(row.get("conditional_action_count", 0)) > 0 for row in rows) / n,
        "ScenarioOnlyRate": sum(int(row.get("scenario_action_count", 0)) > 0 for row in rows) / n,
        "AbstainRate": sum(not row.get("authoritative_decision_available", False) for row in rows) / n,
    }


def invalidated_top1_rate(rows) -> float | None:
    eligible = [row for row in rows if row.get("relaxed_top1") is not None]
    if not eligible:
        return None
    return sum(row.get("relaxed_top1_full_lane") != "FORMAL" for row in eligible) / len(eligible)


def invalidated_topk_share(rows) -> float | None:
    total = invalid = 0
    for row in rows:
        lanes = tuple(row.get("relaxed_topk_full_lanes", ()))
        total += len(lanes)
        invalid += sum(lane != "FORMAL" for lane in lanes)
    return None if total == 0 else invalid / total


def coverage_inflation(full_coverage: float, relaxed_coverage: float) -> float:
    return float(relaxed_coverage) - float(full_coverage)
