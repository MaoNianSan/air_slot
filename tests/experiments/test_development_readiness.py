from exp.readiness import build_development_readiness


def test_development_readiness_reflects_m2_m3_freezes():
    readiness = build_development_readiness()
    assert readiness["EXP2_READINESS"] == "PASS"
    assert readiness["EXP2_READINESS_REASON"] == "M2_FORMAL_SCOPE_READY"
    assert readiness["EXP2_FORMAL_SCOPE_STATUS"] == "FORMAL_READY"
    assert readiness["EXP3_READINESS"] == "PASS"
    assert readiness["EXP3_READINESS_REASON"] == "M3_RESPONSE_PARAMETERS_FROZEN"
    assert readiness["EXP4_READINESS"] == "PASS"
    assert readiness["M2_REGISTRY_READY"] == "PASS"
    assert readiness["M2_REGISTRY_HASH"].startswith("sha256:")
    assert readiness["M3_REGISTRY_READY"] == "PASS"
    assert readiness["M3_RESPONSE_REGISTRY_READY"] == "PASS"
    assert readiness["M3_RESPONSE_REGISTRY_HASH"].startswith("sha256:")
    assert readiness["M3_UNFROZEN_RESPONSE_PARAMETER_TEMPLATES"] == 0
    assert readiness["M4_PRINCIPAL_CONFIG_READY"] == "PASS"
    assert readiness["M4_PRINCIPAL_LAMBDA"] == 0.25
    assert readiness["M4_PRINCIPAL_ALPHA"] == 0.90
    assert readiness["FINAL_TEST_ACCESS_COUNT"] == 0
    assert readiness["PAPER_FULL_RUN"] is False
