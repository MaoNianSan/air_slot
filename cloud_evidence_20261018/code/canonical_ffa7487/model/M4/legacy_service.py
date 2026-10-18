"""Public M4 service boundary."""

from __future__ import annotations

from .residual_risk import evaluate_residual_risk, rank_risk_evaluations


class M4Service:
    """Evaluate and rank typed M3 action envelopes on a common basis."""

    def evaluate(self, envelope, *, monetary_mapping=None, risk_policy=None):
        return evaluate_residual_risk(
            envelope,
            monetary_mapping=monetary_mapping,
            risk_policy=risk_policy,
        )

    def rank(self, evaluations):
        return rank_risk_evaluations(tuple(evaluations))


__all__ = ["M4Service"]

