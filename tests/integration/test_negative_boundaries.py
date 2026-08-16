from datetime import datetime, timezone
import pytest
from model.common.enums import EvidenceClass
from model.common.errors import ContractError
from model.PRE.adapters.base import CanonicalReadRequest
from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.evidence.admissibility import EvidenceCandidate, latest_legal
from model.PRE.evidence.support import publish_value, validate_transformation
from model.PRE.episode.membership import validate_episode_membership
from model.PRE.adapters.base import AdapterDescription
from pydantic import ValidationError


def test_negative_foundation_boundaries_are_explicit():
    assert not validate_episode_membership("X", "P", "S")
    with pytest.raises(ContractError): validate_transformation(EvidenceClass.DIRECT, EvidenceClass.DERIVED)
    with pytest.raises(ContractError, match="RAW_READ_REQUEST_REQUIRED"):
        tuple(Data1Adapter().iter_canonical(CanonicalReadRequest(source_family="opensky_state_vectors")))


def test_future_leakage_silent_missing_and_dataset_mixing_are_rejected():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=timezone.utc)
    future = EvidenceCandidate(record_id="future", availability_time=datetime(2019, 1, 1, 13, tzinfo=timezone.utc), priority=1, value=0)
    with pytest.raises(ContractError, match="NO_LEGAL_EVIDENCE"):
        latest_legal([future], cutoff=cutoff, replay_lag_minutes=0)
    with pytest.raises(ValidationError): publish_value(None, "SUPPORTED")
    with pytest.raises(ValidationError):
        AdapterDescription(dataset_instance_id="data1+data2", source_families=("mixed",))
