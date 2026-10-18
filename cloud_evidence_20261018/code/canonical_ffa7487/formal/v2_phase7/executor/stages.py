"""Frozen Phase-7 DAG stages and dependency edges.

The order and the edges reproduce the Phase-6 freeze R2 DAG exactly:

``CanonicalNodes -> StateVariants -> ConsequenceVariants -> AttentionDecisions
-> ReferenceRecoveryCohort -> RecoveryDecisions -> M4Comparisons -> Bootstrap
-> PaperViews``

``CANONICAL_NODES`` is the materialization boundary. A one-shot entry
(:mod:`formal.v2_phase7.executor.raw_entry`) produces that checkpoint from an
explicitly authorized Final-Test raw source; every later stage may only consume
immutable, hash-validated checkpoints.
"""

from __future__ import annotations

CANONICAL_NODES = "CANONICAL_NODES"
STATE_VARIANTS = "STATE_VARIANTS"
CONSEQUENCE_VARIANTS = "CONSEQUENCE_VARIANTS"
ATTENTION_DECISIONS = "ATTENTION_DECISIONS"
REFERENCE_RECOVERY_COHORT = "REFERENCE_RECOVERY_COHORT"
RECOVERY_DECISIONS = "RECOVERY_DECISIONS"
M4_COMPARISONS = "M4_COMPARISONS"
BOOTSTRAP = "BOOTSTRAP"
ROBUSTNESS = "ROBUSTNESS"
PAPER_VIEWS = "PAPER_VIEWS"

SCIENCE_DAG_STAGES: tuple[str, ...] = (
    CANONICAL_NODES,
    STATE_VARIANTS,
    CONSEQUENCE_VARIANTS,
    ATTENTION_DECISIONS,
    REFERENCE_RECOVERY_COHORT,
    RECOVERY_DECISIONS,
    M4_COMPARISONS,
    BOOTSTRAP,
    ROBUSTNESS,
    PAPER_VIEWS,
)

#: Stage -> upstream stages it consumes. The DAG is acyclic and every stage
#: consumes only previously validated checkpoints.
STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    CANONICAL_NODES: (),
    STATE_VARIANTS: (CANONICAL_NODES,),
    CONSEQUENCE_VARIANTS: (CANONICAL_NODES, STATE_VARIANTS),
    ATTENTION_DECISIONS: (CONSEQUENCE_VARIANTS,),
    REFERENCE_RECOVERY_COHORT: (
        CANONICAL_NODES,
        STATE_VARIANTS,
        ATTENTION_DECISIONS,
    ),
    RECOVERY_DECISIONS: (
        CANONICAL_NODES,
        STATE_VARIANTS,
        REFERENCE_RECOVERY_COHORT,
    ),
    M4_COMPARISONS: (
        CONSEQUENCE_VARIANTS,
        ATTENTION_DECISIONS,
        REFERENCE_RECOVERY_COHORT,
        RECOVERY_DECISIONS,
    ),
    BOOTSTRAP: (M4_COMPARISONS,),
    ROBUSTNESS: (
        CANONICAL_NODES,
        STATE_VARIANTS,
        REFERENCE_RECOVERY_COHORT,
        RECOVERY_DECISIONS,
    ),
    PAPER_VIEWS: (
        ATTENTION_DECISIONS,
        M4_COMPARISONS,
        BOOTSTRAP,
        ROBUSTNESS,
    ),
}

MATERIALIZATION_STAGE = CANONICAL_NODES

#: Main state variants of the frozen Phase-7 design.
PRIMARY_STATE_VARIANTS: tuple[str, ...] = (
    "HISTORY_JOINT",
    "CURRENT_JOINT",
    "HISTORY_POINT",
    "HISTORY_MARGINAL",
)
REFERENCE_VARIANT = "HISTORY_JOINT"
COMPARATOR_VARIANTS: tuple[str, ...] = tuple(
    variant for variant in PRIMARY_STATE_VARIANTS if variant != REFERENCE_VARIANT
)

#: Stage-I screening is stage-local. TAXI/COMP remain materialized only.
ACTIONABLE_STAGE_I_STAGES: tuple[str, ...] = (
    "PRE_IB",
    "POST_IB_PRE_OB",
)

#: H8 and fixed-window history are sensitivities, never main variants.
SENSITIVITY_VARIANTS: dict[str, str] = {
    "HISTORY_H8_JOINT": "FROZEN_SENSITIVITY_NOT_RUN_IN_GATE_B0",
    "FIXED_WINDOW_HISTORY": "NOT_AVAILABLE_NOT_FROZEN",
}
FIXED_WINDOW_SENSITIVITY_STATUS = "NOT_AVAILABLE_NOT_FROZEN"

SCHEMA_PREFIX = "AIR_SLOT_V2_PHASE7"


def schema_version(stage: str) -> str:
    """Return the frozen schema tag for one stage payload."""

    if stage not in SCIENCE_DAG_STAGES:
        raise KeyError(stage)
    return f"{SCHEMA_PREFIX}_{stage}_V1"


def downstream_stages(stage: str) -> tuple[str, ...]:
    """Return every stage that (transitively) consumes ``stage``."""

    ordered: list[str] = []
    pending = [stage]
    while pending:
        current = pending.pop(0)
        for candidate, dependencies in STAGE_DEPENDENCIES.items():
            if current in dependencies and candidate not in ordered:
                ordered.append(candidate)
                pending.append(candidate)
    return tuple(ordered)


__all__ = [
    "ATTENTION_DECISIONS",
    "ACTIONABLE_STAGE_I_STAGES",
    "BOOTSTRAP",
    "CANONICAL_NODES",
    "COMPARATOR_VARIANTS",
    "CONSEQUENCE_VARIANTS",
    "FIXED_WINDOW_SENSITIVITY_STATUS",
    "M4_COMPARISONS",
    "MATERIALIZATION_STAGE",
    "PAPER_VIEWS",
    "ROBUSTNESS",
    "PRIMARY_STATE_VARIANTS",
    "RECOVERY_DECISIONS",
    "REFERENCE_RECOVERY_COHORT",
    "REFERENCE_VARIANT",
    "SCIENCE_DAG_STAGES",
    "SENSITIVITY_VARIANTS",
    "STAGE_DEPENDENCIES",
    "STATE_VARIANTS",
    "downstream_stages",
    "schema_version",
]
