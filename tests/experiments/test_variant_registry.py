import pytest

from exp.common.evaluator import default_evaluation_suite
from exp.common.registry import VariantDefinition, VariantRegistry


VARIANTS = (
    ("EXP1_FULL", "information_pathway", "STATE_CRPS"),
    ("EXP1_NO_DIRECT_REUSE", "direct_reuse", "STATE_CRPS"),
    ("EXP2_COLLAPSED", "information_structure", "DECISION_ACTION_DISAGREEMENT"),
    ("EXP2_MARGINAL", "information_structure", "DECISION_RANKING_CHANGE"),
    ("EXP2_JOINT", "information_structure", "DECISION_RISK_DIFFERENCE"),
    ("EXP3_ONE_SHOT", "decision_timing", "SYSTEM_RUNTIME"),
    ("EXP3_ROLLING", "decision_timing", "SYSTEM_LATENCY"),
)


def definition(variant_id, changed_factor, metric_id):
    return VariantDefinition(
        variant_id=variant_id,
        description=f"Interface declaration for {variant_id}",
        changed_factor=changed_factor,
        fixed_factor=("model_parameters", "dataset_cohort", "scenario_seed"),
        allowed_metrics=(metric_id,),
        claim_scope="INTERFACE_ONLY_NOT_A_RESULT",
    )


def test_registry_supports_declared_exp1_exp2_exp3_variant_ids():
    registry = VariantRegistry(definition(*item) for item in VARIANTS)

    assert registry.variant_ids() == tuple(sorted(item[0] for item in VARIANTS))
    assert len(registry) == 7
    assert "EXP2_JOINT" in registry
    registry.validate_metric_catalog(default_evaluation_suite().metric_ids())


def test_registry_rejects_duplicates_and_disallowed_metrics():
    item = definition(*VARIANTS[0])
    registry = VariantRegistry((item,))
    with pytest.raises(ValueError, match="VARIANT_ID_ALREADY_REGISTERED"):
        registry.register(item)
    with pytest.raises(ValueError, match="VARIANT_METRIC_NOT_ALLOWED"):
        registry.validate_metric(item.variant_id, "SYSTEM_LATENCY")


def test_variant_definition_rejects_changed_factor_as_fixed():
    with pytest.raises(ValueError, match="CHANGED_FACTOR_DECLARED_FIXED"):
        VariantDefinition(
            variant_id="INVALID",
            description="invalid fixture",
            changed_factor="history",
            fixed_factor=("history",),
            allowed_metrics=("STATE_CRPS",),
            claim_scope="INTERFACE_ONLY",
        )

