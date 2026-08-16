from __future__ import annotations

from itertools import combinations


def formal_multi_action_gate(count: int) -> dict[str, object]:
    if count >= 500:
        claim = "STRONG_AUTHORITATIVE_RANKING_CLAIM_ALLOWED"
    elif count >= 100:
        claim = "DOWNGRADED_AUTHORITATIVE_RANKING_CLAIM"
    else:
        claim = "SCENARIO_CONDITIONED_DECISION_VALUE_ANALYSIS"
    return {"N_FORMAL_MULTI": count, "claim_gate": claim,
            "principal_authoritative_ranking_claim": count >= 100}


def consequence_distortion(reference: dict[str, float], variant: dict[str, float]) -> float:
    keys = sorted(set(reference) & set(variant))
    return sum(abs(float(variant[key]) - float(reference[key])) for key in keys)


def action_gap_distortion(reference: dict[str, float], variant: dict[str, float]) -> float:
    common = sorted(set(reference) & set(variant))
    if len(common) < 2:
        return 0.0
    return sum(abs((variant[a] - variant[b]) - (reference[a] - reference[b]))
               for a, b in combinations(common, 2)) / len(list(combinations(common, 2)))


def pairwise_ranking_reversal_rate(reference: dict[str, float], variant: dict[str, float]) -> float:
    pairs = list(combinations(sorted(set(reference) & set(variant)), 2))
    if not pairs:
        return 0.0
    reversals = sum((reference[a] - reference[b]) * (variant[a] - variant[b]) < 0 for a, b in pairs)
    return reversals / len(pairs)


def top1_disagreement(reference: dict[str, float], variant: dict[str, float]) -> float:
    if not reference or not variant:
        return 0.0
    return float(min(reference, key=reference.get) != min(variant, key=variant.get))


def ranking_at_3_overlap(reference: dict[str, float], variant: dict[str, float]) -> float | None:
    if len(reference) < 3 or len(variant) < 3:
        return None
    left = set(sorted(reference, key=reference.get)[:3])
    right = set(sorted(variant, key=variant.get)[:3])
    return len(left & right) / 3.0


def reference_objective_selection_penalty(reference: dict[str, float], variant: dict[str, float]) -> dict:
    """Select under the variant, then score that action under the reference evaluator."""
    if not reference or not variant:
        return {"ReferenceObjectiveSelectionPenalty": None,
                "NormalizedReferenceObjectiveSelectionPenalty": None}
    chosen = min(variant, key=variant.get)
    reference_choice = min(reference, key=reference.get)
    penalty = float(reference[chosen]) - float(reference[reference_choice])
    gap_scale = max(reference.values()) - min(reference.values())
    normalized = None if gap_scale == 0 else penalty / gap_scale
    return {"selected_action": chosen, "reference_action": reference_choice,
            "ReferenceObjectiveSelectionPenalty": penalty,
            "NormalizedReferenceObjectiveSelectionPenalty": normalized}
