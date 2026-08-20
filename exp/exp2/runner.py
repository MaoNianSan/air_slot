"""Exp2 entry points.

The legacy scalar-row runner remains available for non-scientific smoke tests.
Every Development or formal Exp2 execution must use the typed protocol route.
"""

from __future__ import annotations

from exp.common.runner import BaseRunner, ExperimentRunner
from model.common.errors import ContractError

from .protocol import Exp2Protocol, Exp2RunContext
from .variants import EXP2_VARIANT_IDS


class Exp2Runner(BaseRunner):
    experiment = "exp2"
    variants = EXP2_VARIANT_IDS
    protocol_variants = EXP2_VARIANT_IDS
    reference_evaluator = "M4_RESIDUAL_RISK_FIXED_MAPPING_AND_POLICY"
    headline_metrics = (
        "DECISION_ACTION_DISAGREEMENT",
        "DECISION_RANKING_CHANGE",
        "DECISION_RISK_DIFFERENCE",
        "DECISION_CVAR_DIFFERENCE",
    )

    def run(self, rows, *, smoke=False, **kwargs):
        if not smoke:
            raise ContractError("EXP2_TYPED_PROTOCOL_EXECUTION_REQUIRED")
        return super().run(rows, smoke=True, **kwargs)

    def execute(self, context: Exp2RunContext):
        """Execute one frozen representation contrast through M3 then M4."""

        return ExperimentRunner().execute(Exp2Protocol(), context=context)


__all__ = ["Exp2Runner"]
