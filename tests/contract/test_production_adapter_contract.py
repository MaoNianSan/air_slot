from pathlib import Path
import pytest
from pydantic import ValidationError

from model.common.errors import ContractError
from model.PRE.adapters.registry import RawReadRequest, SourceAdapterRegistry


def test_source_registry_loads_audited_layouts():
    registry = SourceAdapterRegistry.load(Path("registries/source_adapter_registry.yaml"))
    assert {item.source_family for item in registry.sources} >= {
        "opensky_flightlist", "opensky_state_vectors", "iem_metar", "eurostat",
        "ourairports", "bts_ontime", "bts_db1b", "bts_t100", "timezone_reference",
        "airport_reference"}
    assert all(item.version and item.rule_ids for item in registry.sources)
    ontime = registry.get("data2_2019", "bts_ontime")
    assert ontime.column_roles["DepDelay"] == "SIGNED_TIME_OFFSET"
    assert ontime.column_roles["ArrDelay"] == "SIGNED_TIME_OFFSET"
    assert ontime.column_roles["DepDelayMinutes"] == "NONNEGATIVE_DELAY_REPORTING_ONLY"
    assert ontime.column_roles["ArrDelayMinutes"] == "NONNEGATIVE_DELAY_REPORTING_ONLY"


def test_raw_read_request_rejects_escape_and_output_inside_raw(tmp_path: Path):
    root = tmp_path / "raw"; root.mkdir()
    with pytest.raises((ValidationError, ContractError)):
        RawReadRequest(dataset_instance_id="data1_2019", source_family="iem_metar",
            raw_root=root, output_root=root / "cache", max_rows=1)
    request = RawReadRequest(dataset_instance_id="data1_2019", source_family="iem_metar",
        raw_root=root, output_root=tmp_path / "cache", max_rows=1)
    with pytest.raises(ContractError): request.resolve_source(Path("../outside.csv"))
