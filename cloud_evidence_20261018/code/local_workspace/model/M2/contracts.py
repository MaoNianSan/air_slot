from typing import Literal
from pydantic import model_validator
from model.common.value_objects import FrozenModel
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS

COMPONENTS=CONSEQUENCE_COMPONENTS
Component=Literal["F_continuity","F_execution","F_propagation","P_time","P_itinerary","P_service","R_operating"]

class NativeQuantity(FrozenModel):
    component: Component
    native_value: float|None
    native_unit: str
    driver: str
    evidence_class: str
    support: Literal["SUPPORTED","DEGRADED","ABSTAIN"]
    reason_code: str|None=None
    provenance: tuple[str,...]=()
    @model_validator(mode="after")
    def explicit(self):
        if self.support=="ABSTAIN" and (self.native_value is not None or not self.reason_code): raise ValueError("abstain requires null and reason")
        if self.native_value is None and self.support!="ABSTAIN": raise ValueError("null must abstain")
        return self

class ConsequenceRow(FrozenModel):
    component: Component
    aspect: Literal["Flight","Passenger","Resource"]
    native_value: float|None
    native_unit: str
    driver: str
    constructed_cu: float|None
    evidence_class: str
    support: str
    reason_code: str|None=None
    valuation_rule_id: str|None=None
    valuation_parameter_version: str|None=None
    provenance: tuple[str,...]=()

class ScenarioConsequence(FrozenModel):
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    components: tuple[ConsequenceRow,...]
    available_component_sum_cu: float
    formal_total_cu: float|None
