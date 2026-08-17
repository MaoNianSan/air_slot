from exp.readiness import build_development_readiness


def test_development_readiness_keeps_m2_m3_gates_explicit():
    readiness = build_development_readiness()
    assert readiness["EXP2_READINESS"] == "PARTIAL"
    assert readiness["EXP2_READINESS_REASON"] == "M2_FORMAL_FREEZE_PENDING"
    assert readiness["EXP3_READINESS"] == "PARTIAL"
    assert readiness["EXP3_READINESS_REASON"] == "M3_RESPONSE_PARAMETERS_NOT_FROZEN"
    assert readiness["EXP4_READINESS"] == "PARTIAL"
    assert readiness["M3_REGISTRY_READY"] == "PASS"
    assert readiness["M4_PRINCIPAL_CONFIG_READY"] == "PASS"
    assert readiness["M4_PRINCIPAL_LAMBDA"] == 0.25
    assert readiness["M4_PRINCIPAL_ALPHA"] == 0.90
    assert readiness["FINAL_TEST_ACCESS_COUNT"] == 0
    assert readiness["PAPER_FULL_RUN"] is False
