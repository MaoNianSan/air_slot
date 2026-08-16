import pytest
from model.common.errors import ContractError
from model.PRE.adapters.data2 import Data2Adapter
from model.PRE.adapters.base import CanonicalReadRequest


def test_data2_declares_posthoc_and_reference_limits():
    adapter = Data2Adapter()
    caps = adapter.capabilities()
    assert caps["realized_events"] == "POSTHOC_DIRECT"
    assert caps["passenger_reference"] == "AGGREGATE_PROXY"
    assert caps["aircraft_type"] == "UNVERIFIED"
    assert caps["realtime_state"] == "UNSUPPORTED"
    with pytest.raises(ContractError, match="RAW_READ_REQUEST_REQUIRED"):
        tuple(adapter.iter_canonical(CanonicalReadRequest(source_family="bts_ontime")))
