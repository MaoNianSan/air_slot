from pathlib import Path

from model.PRE.feature_registry.inspection import RegistryInspector


def test_every_registered_source_family_has_a_safe_lineage_chain():
    chains = RegistryInspector.from_path(Path("registries")).chains()
    assert chains
    assert len(chains) == 26  # ... + D2-PASSENGER-REFERENCE-H1 + D2-TEMPORAL-SPLIT (D2-10, 2026-08-14) + D2-T100-CLASS (2026-08-16)
    assert {chain.source_family for chain in chains} == {
        "opensky_state_vectors", "opensky_flightlist", "iem_metar",
        "eurostat", "ourairports", "bts_ontime", "bts_db1b",
        "bts_t100", "timezone_reference", "airport_reference", "noaa_isd",
    }
    assert all("M4" not in chain.consumers for chain in chains)
