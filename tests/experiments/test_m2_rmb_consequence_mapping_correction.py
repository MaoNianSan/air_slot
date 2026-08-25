import json
from pathlib import Path

from exp.workflows.m2_rmb_consequence_mapping_correction import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_m2_rmb_interface_binds_seven_components_and_keeps_mapping_unfrozen(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["status"] == "M2_CONSEQUENCE_TO_RMB_INTERFACE_MATERIALIZED"
    assert artifact["m2_output_contract"]["object"] == "C"
    assert len(artifact["component_order"]) == 7
    assert artifact["monetary_mapping_contract"]["formula"] == "RMB_k = f_k(C_k)"
    assert artifact["action_chain"] == "A -> C^a -> RMB^a -> risk"
    assert artifact["monetary_mapping_contract"]["real_currency_claim"] is False
    assert artifact["legacy_cu_boundary"]["monetary_interface"] is False
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
