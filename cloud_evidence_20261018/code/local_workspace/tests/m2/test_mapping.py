from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.common.errors import ContractError
import pytest

def test_mapping_preserves_scenarios_and_abstains_unsupported_component():
    registry=ValuationRegistry.smoke(); mapper=M2Mapper(registry)
    scenarios=[{"decision_node_id":"n","scenario_id":0,"scenario_weight":.5,"r_ib_minutes":10,"r_ob_minutes":5,"t_tx_minutes":15},
               {"decision_node_id":"n","scenario_id":1,"scenario_weight":.5,"r_ib_minutes":20,"r_ob_minutes":10,"t_tx_minutes":25}]
    context={"turnaround_buffer_minutes":15,"downstream_exposure":1,"passenger_exposure":100,
             "itinerary_support":"ABSTAIN","service_threshold_minutes":15,"taxi_reference_minutes":10}
    outputs=mapper.map_scenarios(scenarios,context)
    assert len(outputs)==2 and all(len(x.components)==7 for x in outputs)
    assert outputs[0].scenario_id==0 and outputs[1].scenario_id==1
    itinerary=[x for x in outputs[0].components if x.component=="P_itinerary"][0]
    assert itinerary.constructed_cu is None and outputs[0].formal_total_cu is None


def test_missing_required_context_is_not_silently_zero_filled():
    mapper=M2Mapper(ValuationRegistry.smoke())
    scenario={"decision_node_id":"n","scenario_id":0,"scenario_weight":1,
              "r_ib_minutes":10,"r_ob_minutes":5,"t_tx_minutes":15}
    with pytest.raises(ContractError,match="M2_CONTEXT_PARAMETER_MISSING"):
        mapper.map_scenarios([scenario],{"passenger_exposure":100,"itinerary_disruption_events":0})
