from exp.exp1.information import apply_direct_reuse_mask, assert_no_direct_reuse_leakage
from exp.exp1.runner import Exp1Runner
from exp.exp1.variants import (
    EXP1B_SENSITIVITY_VARIANTS,
    EXP1_VARIANTS,
    information_mask,
)


def test_exp1_headline_variants_only_cover_information_roles():
    assert EXP1_VARIANTS == (
        "EXP1A_NO_DIRECT_REUSE", "EXP1A_FULL", "EXP1B_CURRENT",
        "EXP1B_ADAPTIVE_HISTORY",
    )
    assert EXP1B_SENSITIVITY_VARIANTS == ("EXP1B_FIXED_HISTORY_30",)
    assert "DecisionWindowGain" not in Exp1Runner.headline_metrics


def test_no_direct_reuse_blocks_hidden_and_weather_rereads_but_keeps_chain():
    artifact = {
        "upstream_hidden_history": {"opaque": True},
        "raw_weather_context": {"wind": 10},
        "baseline_consequence": {"seven_component": True},
    }
    transformed = apply_direct_reuse_mask(artifact, "EXP1A_NO_DIRECT_REUSE")
    assert transformed["full_chain_preserved"] is True
    assert transformed["model_chain"] == ("PRE", "M1", "M2", "M3", "M4")
    assert information_mask("EXP1A_NO_DIRECT_REUSE")["minimal_actionability_facts"] == "STRUCTURALLY_REQUIRED"
    assert_no_direct_reuse_leakage(transformed)


def test_exp1_fast_returns_common_context_results():
    results = Exp1Runner().execute_fast()
    assert len(results) == len(EXP1_VARIANTS)
    assert {item.tier for item in results} == {"CONTRACT_FAST"}
    assert {item.final_test_access_count for item in results} == {0}
