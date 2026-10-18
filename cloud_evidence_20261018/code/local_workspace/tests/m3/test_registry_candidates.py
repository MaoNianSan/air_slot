from pathlib import Path
from model.M3.registry import ActionRegistry
from model.M3.instantiate import instantiate_candidates

def test_all_templates_load_and_unknown_precondition_retains_candidate():
    registry=ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert tuple(x.template_id for x in registry.templates)==("A00","A11","A13","A21","A22","A23","A31","A32","A33","A41","A42","A43","A51","A52","A53","A54","A55","A61","A62","A63","A64","A71","A72")
    candidates=instantiate_candidates({"episode_id":"e","decision_node_id":"n","facts":{"aircraft_identity":True}},registry)
    assert any(x.precondition_state=="UNKNOWN" for x in candidates)
    assert all(x.response_provenance!="EMPIRICAL_ACTION_LOG" for x in candidates)
