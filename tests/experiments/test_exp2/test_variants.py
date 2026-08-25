from exp.exp2.variants import EXP2_VARIANT_IDS, EXP2_VARIANT_REGISTRY


def test_all_six_frozen_variants_are_registered_with_required_metadata():
    assert EXP2_VARIANT_REGISTRY.variant_ids() == tuple(sorted(EXP2_VARIANT_IDS))
    assert len(EXP2_VARIANT_REGISTRY) == 6
    for variant_id in EXP2_VARIANT_IDS:
        definition = EXP2_VARIANT_REGISTRY.get(variant_id)
        assert definition.variant_id == variant_id
        assert definition.description
        assert definition.changed_factor
        assert definition.fixed_factor
        assert definition.claim_scope
