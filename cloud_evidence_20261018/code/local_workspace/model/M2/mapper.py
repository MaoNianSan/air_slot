from .contracts import COMPONENTS, ScenarioConsequence
from .drivers import native_quantities

class M2Mapper:
    def __init__(self,registry): self.registry=registry
    def map_scenarios(self,scenarios,context):
        outputs=[]
        for scenario in scenarios:
            rows=tuple(self.registry.value(q) for q in native_quantities(scenario,context))
            assert tuple(row.component for row in rows)==COMPONENTS
            available=sum(row.constructed_cu for row in rows if row.constructed_cu is not None)
            formal=available if all(row.constructed_cu is not None for row in rows) else None
            outputs.append(ScenarioConsequence(decision_node_id=scenario["decision_node_id"],scenario_id=scenario["scenario_id"],
                scenario_weight=scenario["scenario_weight"],components=rows,available_component_sum_cu=available,formal_total_cu=formal))
        return tuple(outputs)
