import json
from pathlib import Path

from exp.workflows.m2_cu_rmb_interface_correction import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_corrected_chain_is_c_to_cu_to_rmb(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["status"] == "M2_C_TO_CU_INTERFACE_BOUND"
    assert artifact["m2_output_contract"]["mapping"] == "CU_k = g_k(C_k)"
    assert artifact["rmb_mapping_contract"]["formula"] == "RMB_k = f_k(CU_k)"
    assert artifact["action_chain"] == "A -> C^a -> CU^a -> RMB^a -> risk"
    assert artifact["rmb_mapping_contract"]["real_currency_claim"] is False
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
