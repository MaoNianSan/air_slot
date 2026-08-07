from __future__ import annotations

from collections import Counter
from typing import Iterable

from .contracts import M4ActionEvaluation


def summarize_reason_codes(
    evaluations: Iterable[M4ActionEvaluation],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in evaluations:
        counts.update(item.reason_codes)
    return dict(sorted(counts.items()))


def action_explanation(item: M4ActionEvaluation) -> dict[str, object]:
    return {
        "action_id": item.action_id,
        "decision_lane": item.decision_lane.value,
        "reason_codes": list(item.reason_codes),
        "risk_score": item.risk_score,
        "expected_improvement_vs_a00": item.expected_improvement_vs_a00,
        "tail_improvement_vs_a00": item.tail_improvement_vs_a00,
    }
