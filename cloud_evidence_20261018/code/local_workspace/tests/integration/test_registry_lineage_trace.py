from pathlib import Path

from model.PRE.feature_registry.inspection import RegistryInspector


def test_every_registered_source_family_has_a_safe_lineage_chain():
    chains = RegistryInspector.from_path(Path("registries")).chains()
    assert chains
    assert len(chains) == 10
    assert {chain.source_family for chain in chains} == {
        "opensky_state_vectors", "opensky_flightlist", "iem_metar",
        "eurostat", "ourairports", "bts_ontime", "bts_db1b",
        "bts_t100", "timezone_reference",
    }
    assert all("M4" not in chain.consumers for chain in chains)
