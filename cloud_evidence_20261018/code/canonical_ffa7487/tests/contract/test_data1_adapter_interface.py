import pytest
from model.common.errors import ContractError
from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.base import CanonicalReadRequest


def test_data1_declares_audited_ceilings_and_no_reader():
    adapter = Data1Adapter()
    caps = adapter.capabilities()
    assert caps["qnh_mslp"] == "QNH_NOT_MSLP"
    assert caps["schedule"] == "UNSUPPORTED"
    assert caps["aircraft_metadata_2019"] == "UNSUPPORTED"
    assert caps["passenger_reference"] == "EMPIRICAL_REFERENCE"
    with pytest.raises(ContractError, match="RAW_READ_REQUEST_REQUIRED"):
        tuple(adapter.iter_canonical(CanonicalReadRequest(source_family="opensky_state_vectors")))
