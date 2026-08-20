import pytest

from exp.exp2.representation import (
    ConsequenceRepresentationAdapter,
    ScenarioRepresentationAdapter,
)
from exp.exp2.variants import (
    EXP2A_COLLAPSED,
    EXP2A_JOINT,
    EXP2A_MARGINAL,
    EXP2B_CHANNEL,
    EXP2B_COMPONENT,
    EXP2B_SCALAR,
)


def _marginal(samples, field):
    return sorted((getattr(item, field), item.scenario_weight) for item in samples)


def test_exp2a_joint_marginal_and_collapsed_transformations(m1_scenarios):
    adapter = ScenarioRepresentationAdapter(m1_scenarios, artifact_version="M1_FIXTURE_V1")
    joint = adapter.transform(EXP2A_JOINT)
    marginal = adapter.transform(EXP2A_MARGINAL)
    collapsed = adapter.transform(EXP2A_COLLAPSED)

    assert joint.source_scenario_hash == marginal.source_scenario_hash == collapsed.source_scenario_hash
    assert joint.samples == adapter.source_samples
    for field in ("D_OB", "D_TX", "D_TO"):
        assert _marginal(joint.samples, field) == _marginal(marginal.samples, field)
    assert any(
        item.field_source_scenario_ids["D_TX"] != item.scenario_id
        for item in marginal.samples
    )
    assert collapsed.samples[0].scenario_weight == 1.0
    assert collapsed.samples[0].D_OB == 6.0
    assert collapsed.samples[0].D_TX == pytest.approx(14 / 3)
    assert collapsed.samples[0].D_TO == pytest.approx(32 / 3)


def test_exp2a_preserves_complete_source_lineage(m1_scenarios):
    adapter = ScenarioRepresentationAdapter(m1_scenarios, artifact_version="M1_FIXTURE_V1")
    source_lineage = {entry for row in adapter.source_samples for entry in row.lineage}
    for variant in (EXP2A_JOINT, EXP2A_MARGINAL, EXP2A_COLLAPSED):
        transformed = adapter.transform(variant)
        transformed_lineage = {entry for row in transformed.samples for entry in row.lineage}
        assert transformed_lineage == source_lineage


def test_exp2b_aggregation_preserves_components_and_propagates_support(m2_consequences):
    adapter = ConsequenceRepresentationAdapter(m2_consequences, artifact_version="M2_FIXTURE_V1")
    component = adapter.transform(EXP2B_COMPONENT)
    channel = adapter.transform(EXP2B_CHANNEL)
    scalar = adapter.transform(EXP2B_SCALAR)

    assert len(component.scenarios[0].values) == 7
    assert len(channel.scenarios[0].values) == 3
    assert len(scalar.scenarios[0].values) == 1
    assert channel.scenarios[0].values[0].value_cu == 6.0
    assert scalar.scenarios[0].values[0].value_cu == 28.0
    assert component.source_artifact_hash == channel.source_artifact_hash == scalar.source_artifact_hash


def test_exp2b_never_treats_unsupported_component_as_zero(m2_consequences):
    rows = [dict(item) for item in m2_consequences]
    components = [dict(item) for item in rows[0]["components"]]
    components[0]["constructed_value_cu"] = None
    components[0]["support_state"] = "ABSTAIN"
    rows[0]["components"] = tuple(components)
    channel = ConsequenceRepresentationAdapter(rows, artifact_version="M2_FIXTURE_V1").transform(EXP2B_CHANNEL)
    flight = channel.scenarios[0].values[0]
    assert flight.value_cu is None
    assert flight.support_status == "ABSTAINED"
