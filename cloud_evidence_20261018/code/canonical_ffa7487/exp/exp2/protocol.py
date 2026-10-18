"""Frozen Exp2 empirical-analysis constants."""

from __future__ import annotations

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import OperationalStage

COMPONENTS = tuple(CONSEQUENCE_COMPONENTS)
FLIGHT_COMPONENTS = ("F_continuity", "F_execution", "F_propagation")
PASSENGER_COMPONENTS = ("P_time", "P_itinerary", "P_service")
RESOURCE_COMPONENTS = ("R_operating",)

ACTIVE_STAGES = tuple(
    stage.value for stage in OperationalStage if stage is not OperationalStage.COMPLETED
)
PRIMARY_SUPPORT_THRESHOLD = 0.90
SENSITIVITY_SUPPORT_THRESHOLD = 0.50
FULL_SUPPORT_THRESHOLD = 1.0
SIMILAR_DELAY_PRIMARY = 5.0
SIMILAR_DELAY_SENSITIVITY = (10.0, 15.0)
MATERIAL_RANK_GAP = 0.30
TOP_FRACTION_PRIMARY = 0.10
TOP_FRACTION_SECONDARY = 0.20
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260906
FAST_BOOTSTRAP_REPLICATES = 20

COMMON_SUPPORT_RULE_ID = "EXP2_COMMON_SUPPORT_MASS_V1"
COMMON_SUPPORT_SEMANTICS = (
    "Scenario-weight probability mass on which D_TO and all seven active M2 V4 "
    "consequence components and constructed CUs are jointly supported, finite, "
    "and compatible with the active registry."
)
COMMON_SUPPORT_CONDITIONAL_ESTIMAND = "EXP2_COMMON_SUPPORT_CONDITIONAL"

DEVELOPMENT_START = "2019-08-01"
DEVELOPMENT_END = "2019-09-30"
FINAL_TEST_ACCESS_COUNT = 0

DISPLAY_NAMES = {
    "F_continuity": "Continuity",
    "F_execution": "Execution",
    "F_propagation": "Propagation",
    "P_time": "Passenger time",
    "P_itinerary": "Itinerary exposure",
    "P_service": "Service exposure",
    "R_operating": "Operating exposure",
    "score_F": "Flight-chain domain",
    "score_P": "Passenger domain",
    "score_R": "Operating domain",
}
