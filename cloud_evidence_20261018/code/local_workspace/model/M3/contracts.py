from typing import Literal,Any
from pydantic import Field, field_validator, model_validator
from model.common.value_objects import FrozenModel
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS

ACTION_FAMILIES={"null","timing_passenger_coordination","flight_execution","timing",
    "capacity_coordination","passenger_recovery","passenger_service","ground_recovery",
    "aircraft_recovery","crew_recovery","extreme_local_network"}
RESPONSE_MODELS={"DETERMINISTIC","BERNOULLI_BETA","DISCRETE_SCENARIO","EMPIRICAL"}
RESPONSE_PROVENANCE={"EMPIRICAL_ACTION_LOG","OPERATOR_INDUSTRY","STRUCTURAL_BOUNDED_SCENARIO",
    "PURE_SCENARIO","UNSUPPORTED"}

class ActionTemplate(FrozenModel):
    template_id:str; name:str; family:str; required_facts:tuple[str,...]=(); required_parameters:tuple[str,...]=()
    authority_capabilities:tuple[str,...]=()
    mitigation:dict[str,float]={}; induced:dict[str,float]={}; induced_response:dict[str,float]={}; response_model:str="BERNOULLI_BETA"
    response_parameters:dict[str,Any]={}; response_provenance:str="PURE_SCENARIO"; coverage:str="PARTIAL"
    preparation_time_minutes:float=Field(default=0,ge=0); deadline_semantics:str="scenario_deadline"

    @field_validator("template_id")
    @classmethod
    def action_id(cls,value):
        if len(value)!=3 or value[0]!="A" or not value[1:].isdigit(): raise ValueError("INVALID_ACTION_ID")
        return value

    @model_validator(mode="after")
    def strict_contract(self):
        unknown=(set(self.mitigation)|set(self.induced)|set(self.induced_response))-set(CONSEQUENCE_COMPONENTS)
        if unknown: raise ValueError(f"UNKNOWN_M2_CONSEQUENCE_COMPONENT:{sorted(unknown)}")
        if self.family not in ACTION_FAMILIES: raise ValueError("UNKNOWN_ACTION_FAMILY")
        if self.response_model not in RESPONSE_MODELS: raise ValueError("UNKNOWN_RESPONSE_MODEL")
        if self.response_provenance not in RESPONSE_PROVENANCE: raise ValueError("UNKNOWN_RESPONSE_PROVENANCE")
        if self.coverage not in {"FULL","HIGH","PARTIAL","INSUFFICIENT"}: raise ValueError("UNKNOWN_COVERAGE")
        if len(set(self.required_parameters))!=len(self.required_parameters): raise ValueError("DUPLICATE_REQUIRED_PARAMETER")
        if not self.deadline_semantics: raise ValueError("DEADLINE_SEMANTICS_REQUIRED")
        return self

class CandidateAction(FrozenModel):
    candidate_action_id:str; template_id:str; action_family:str; parameters:dict[str,Any]
    precondition_state:Literal["TRUE","FALSE","UNKNOWN"]; authority_capabilities:tuple[str,...]
    mitigation:dict[str,float]; induced:dict[str,float]; induced_response:dict[str,float]={}; response_model:str; response_parameters:dict[str,Any]
    response_provenance:str; coverage:Literal["FULL","HIGH","PARTIAL","INSUFFICIENT"]
    preparation_time_minutes:float; deadline_semantics:str
