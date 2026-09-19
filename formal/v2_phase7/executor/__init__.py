"""Frozen Phase-7 nine-stage scientific executor.

The package implements the Freeze-R2 DAG

``CanonicalNodes -> StateVariants -> ConsequenceVariants -> AttentionDecisions
-> ReferenceRecoveryCohort -> RecoveryDecisions -> M4Comparisons -> Bootstrap
-> PaperViews``

over immutable, hash-validated checkpoints. Scientific formulas are never
re-implemented here: every stage calls the frozen M1/M2/M3/M4 services with the
frozen inputs, and every later stage consumes only a validated upstream
checkpoint.
"""

from __future__ import annotations

from . import stages

__all__ = ["stages"]
