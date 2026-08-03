from __future__ import annotations

from src.pipeline_config import load_config
from src.profile_migration import _profile_scientific_payload
from src.input import object_hash


def test_acceptance_23d_is_scientifically_equivalent_to_legacy_adapt_full() -> None:
    legacy = load_config(mode="adapt_full")
    current = load_config(mode="acceptance_23d")
    assert object_hash(_profile_scientific_payload(legacy)) == object_hash(
        _profile_scientific_payload(current)
    )
