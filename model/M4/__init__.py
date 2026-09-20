"""Current Section 3.5 priority and screening interface.

Monetary residual-risk code remains available only through explicit legacy
modules and is not part of the current empirical mainline.
"""

from .alignment import compare_priority_representations
from .contracts import (
    CommonSupportPolicy,
    ComponentSummary,
    DomainScoreSummary,
    ExcludedNode,
    PopulationScope,
    PriorityAlignmentRecord,
    PriorityOrdering,
    PriorityPopulation,
    PriorityRepresentation,
    PriorityScoreRecord,
    RankDisplacement,
    ScreeningCapacity,
    ScreeningShortlist,
)
from .service import M4Service

__all__ = [
    "CommonSupportPolicy",
    "ComponentSummary",
    "DomainScoreSummary",
    "ExcludedNode",
    "M4Service",
    "PopulationScope",
    "PriorityAlignmentRecord",
    "PriorityOrdering",
    "PriorityPopulation",
    "PriorityRepresentation",
    "PriorityScoreRecord",
    "RankDisplacement",
    "ScreeningCapacity",
    "ScreeningShortlist",
    "compare_priority_representations",
]
