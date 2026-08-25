from exp.exp4.protocol import EXP4_VARIANTS
from exp.exp4.runner import Exp4Runner


def test_exp4_owns_complete_system_adequacy():
    assert EXP4_VARIANTS[:5] == (
        "EXP4A_PREDICTIVE_ADEQUACY", "EXP4B_DECISION_OUTPUT_VALIDITY",
        "EXP4B_LLM_AUXILIARY_AUDIT", "EXP4C_DATA1_DATA2_PORTABILITY",
        "EXP4D_END_TO_END_RUNTIME",
    )
    assert "OverallPerformanceScore" not in Exp4Runner.headline_metrics


def test_exp4_fast_marks_llm_auxiliary_and_portability_within_dataset():
    results = Exp4Runner().execute_fast()
    assert len(results) == 7
    assert all(item.provenance["llm_audit_role"] == "AUXILIARY_ONLY" for item in results)
    assert all(item.provenance["data1_portability_role"] == "WITHIN_DATASET_FULL_MINUS_LIGHTGBM" for item in results)
