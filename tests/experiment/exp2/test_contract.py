from exp.exp2.consequence_coarsening import CoarseResponseContract, assert_coarse_variant_blind_to_components
from exp.exp2.representation import ScenarioRepresentationAdapter
from exp.exp2.runner import Exp2Runner
from exp.exp2.variants import EXP2_VARIANT_IDS
from model.common.identity import content_id


def test_exp2_active_variants_are_information_resolution_protocol():
    assert EXP2_VARIANT_IDS == (
        "EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT",
        "EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP",
    )
    assert "DECISION_RISK_DIFFERENCE" not in Exp2Runner.headline_metrics


def test_marginal_recomputes_derived_delay_samplewise():
    rows = (
        {"scenario_id": 0, "scenario_weight": 0.5, "D_OB": 1, "D_TX": 2, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 0.5, "D_OB": 5, "D_TX": 8, "lineage": ("b",)},
    )
    marginal = ScenarioRepresentationAdapter(rows, artifact_version="M1_FIXTURE").transform("EXP2A_MARGINAL")
    assert all(item.D_TO == item.D_OB + item.D_TX for item in marginal.samples)


def test_coarse_response_is_train_only_and_blind_to_components():
    contract = CoarseResponseContract.create(
        resolution="3CHANNEL",
        train_population_hash=content_id({"split": "train"}),
        action_response_parameters={"A00": {"Flight": 1.0}},
        source_component_artifact_hash=content_id({"components": 7}),
    )
    assert contract.fit_split == "train"
    try:
        assert_coarse_variant_blind_to_components({"components": []})
    except ValueError as error:
        assert "FINE_COMPONENT_ACCESS" in str(error)
    else:
        raise AssertionError("coarse boundary accepted hidden components")


def test_exp2_fast_is_contract_only():
    results = Exp2Runner().execute_fast()
    assert len(results) == 6
    assert all(item.provenance["complete_reference_j_status"].startswith("INTERNAL") for item in results)
