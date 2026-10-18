from dataclasses import dataclass
from model.common.errors import ContractError
from .contracts import NativeQuantity, ConsequenceRow

@dataclass(frozen=True)
class ValuationRule:
    component:str; rule_id:str; version:str; multiplier:float; critical:bool=True

class ValuationRegistry:
    def __init__(self,rules): self.rules={r.component:r for r in rules}
    @classmethod
    def smoke(cls):
        return cls([ValuationRule(n,f"{n.upper()}_LINEAR","DEV-1",m) for n,m in {
            "F_continuity":2,"F_execution":1,"F_propagation":1.5,"P_time":.01,
            "P_itinerary":5,"P_service":3,"R_operating":1}.items()])
    def value(self,native:NativeQuantity):
        aspect="Flight" if native.component.startswith("F_") else "Passenger" if native.component.startswith("P_") else "Resource"
        if native.support=="ABSTAIN": return ConsequenceRow(**native.model_dump(),aspect=aspect,constructed_cu=None)
        if native.component not in self.rules: raise ContractError("VALUATION_RULE_NOT_FROZEN")
        rule=self.rules[native.component]
        return ConsequenceRow(**native.model_dump(),aspect=aspect,constructed_cu=native.native_value*rule.multiplier,
            valuation_rule_id=rule.rule_id,valuation_parameter_version=rule.version)
