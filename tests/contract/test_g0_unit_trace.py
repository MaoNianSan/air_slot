from pathlib import Path

from validation.g0_unit_trace import build_trace


EPOCH_ROOT = Path("artifacts/diagnostics/v2_phase7/gate_b0_dag")


def test_g0_unit_trace_covers_three_stages_and_typed_taxi_limit():
    result = build_trace(EPOCH_ROOT)
    assert result["status"] == "PASS_STATIC_UNIT_CHAIN_WITH_TYPED_TAXI_LIMIT"
    assert [item["stage"] for item in result["traces"]] == [
        "PRE_IB",
        "POST_IB_PRE_OB",
        "POST_OB_PRE_TO",
    ]
    assert all(item["information_cutoff_ok"] for item in result["traces"])
    assert all(item["m1_state"]["d_to_identity_ok"] for item in result["traces"])
    assert sum(item["status"] == "TRACE_COMPLETE_TO_U" for item in result["traces"]) == 2
    assert result["traces"][-1]["status"] == "TRACE_COMPLETE_TO_PRIORITY_TAXI_U_NOT_AVAILABLE"
