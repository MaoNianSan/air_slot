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
SIMILAR_DELAY_PRIMARY = 5.0
SIMILAR_DELAY_SENSITIVITY = (10.0, 15.0)
MATERIAL_RANK_GAP = 0.30
TOP_FRACTION_PRIMARY = 0.10
TOP_FRACTION_SECONDARY = 0.20
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260906
FAST_BOOTSTRAP_REPLICATES = 20

INHERITED_SUPPORT_RULE_ID = "EXP1_FROZEN_COMMON_SCENARIO_SUPPORT_V1"
INHERITED_SUPPORT_EXACT_SEMANTICS = (
    "S_i contains scenarios with finite D_TO and inherited formal consequence "
    "status FORMAL_AVAILABLE; support_fraction_i=|S_i|/250; primary >=0.90; "
    "sensitivity >=0.50. Exp2 must consume the inherited result and must not "
    "reconstruct it from M2 V4's seven-component aggregate."
)
INHERITED_SUPPORT_BLOCK = "BLOCK_EXP2_INHERITED_SUPPORT_UNRESOLVED"

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
