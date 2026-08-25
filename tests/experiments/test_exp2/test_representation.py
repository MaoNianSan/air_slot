from exp.exp2.representation import (
    ConsequenceRepresentationAdapter,
    ScenarioRepresentationAdapter,
)
from exp.exp2.variants import (
    EXP2A_JOINT,
    EXP2A_MARGINAL,
    EXP2A_POINT,
    EXP2B_3CHANNEL,
    EXP2B_7COMP,
    EXP2B_SCALAR,
)


def _marginal(samples, field):
    return sorted((getattr(item, field), item.scenario_weight) for item in samples)


def test_exp2a_joint_marginal_and_point_transformations(m1_scenarios):
    adapter = ScenarioRepresentationAdapter(m1_scenarios, artifact_version="M1_FIXTURE_V1")
    joint = adapter.transform(EXP2A_JOINT)
    marginal = adapter.transform(EXP2A_MARGINAL)
    point = adapter.transform(EXP2A_POINT)

    assert joint.source_scenario_hash == marginal.source_scenario_hash == point.source_scenario_hash
    assert joint.samples == adapter.source_samples
    for field in ("D_OB", "D_TX"):
        assert _marginal(joint.samples, field) == _marginal(marginal.samples, field)
    assert all(
        item.D_TO == item.D_OB + item.D_TX
        and item.field_source_scenario_ids["D_TO"] == "DERIVED_FROM_D_OB_PLUS_D_TX"
        for item in marginal.samples
    )
    assert any(
        item.field_source_scenario_ids["D_TX"] != item.scenario_id
        for item in marginal.samples
    )
    assert point.samples[0].scenario_id == "POINT:1"
    assert point.samples[0].scenario_weight == 1.0
    assert (point.samples[0].D_OB, point.samples[0].D_TX, point.samples[0].D_TO) == (6.0, 4.0, 10.0)
    assert point.samples[0].field_source_scenario_ids == {
        "D_OB": 1,
        "D_TX": 1,
        "D_TO": 1,
    }


def test_exp2a_preserves_lineage_at_the_representation_granularity(m1_scenarios):
    adapter = ScenarioRepresentationAdapter(m1_scenarios, artifact_version="M1_FIXTURE_V1")
    source_lineage = {entry for row in adapter.source_samples for entry in row.lineage}
    for variant in (EXP2A_JOINT, EXP2A_MARGINAL):
        transformed = adapter.transform(variant)
        transformed_lineage = {entry for row in transformed.samples for entry in row.lineage}
        assert transformed_lineage == source_lineage
    point = adapter.transform(EXP2A_POINT).samples[0]
    assert point.lineage == ("m1:1",)
    assert set(point.field_source_scenario_ids.values()) == {1}


def test_exp2b_aggregation_preserves_components_and_propagates_support(m2_consequences):
    adapter = ConsequenceRepresentationAdapter(m2_consequences, artifact_version="M2_FIXTURE_V1")
    component = adapter.transform(EXP2B_7COMP)
    channel = adapter.transform(EXP2B_3CHANNEL)
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
    channel = ConsequenceRepresentationAdapter(rows, artifact_version="M2_FIXTURE_V1").transform(EXP2B_3CHANNEL)
    flight = channel.scenarios[0].values[0]
    assert flight.value_cu is None
    assert flight.support_status == "ABSTAINED"
