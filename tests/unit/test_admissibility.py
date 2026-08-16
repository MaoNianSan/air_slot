from datetime import datetime, timezone
import pytest
from model.common.errors import ContractError
from model.PRE.evidence.admissibility import EvidenceCandidate, latest_legal


UTC = timezone.utc


def test_latest_legal_rejects_future_and_requires_known_replay_lag():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=UTC)
    candidates = [
        EvidenceCandidate(record_id="old", availability_time=datetime(2019, 1, 1, 10, tzinfo=UTC), priority=1, value="a"),
        EvidenceCandidate(record_id="legal", availability_time=datetime(2019, 1, 1, 11, tzinfo=UTC), priority=1, value="b"),
        EvidenceCandidate(record_id="future", availability_time=datetime(2019, 1, 1, 13, tzinfo=UTC), priority=1, value="c"),
    ]
    assert latest_legal(candidates, cutoff=cutoff, replay_lag_minutes=0).record_id == "legal"
    with pytest.raises(ContractError): latest_legal(candidates, cutoff=cutoff, replay_lag_minutes=None)


def test_equal_priority_conflict_abstains_explicitly():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=UTC)
    same = datetime(2019, 1, 1, 11, tzinfo=UTC)
    with pytest.raises(ContractError, match="EQUAL_PRIORITY_CONFLICT"):
        latest_legal([EvidenceCandidate(record_id="a", availability_time=same, priority=1, value="A"), EvidenceCandidate(record_id="b", availability_time=same, priority=1, value="B")], cutoff=cutoff, replay_lag_minutes=0)


def test_selector_does_not_apply_replay_lag_twice():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=UTC)
    candidate = EvidenceCandidate(record_id="lagged-once", availability_time=cutoff,
                                  priority=1, value="legal")
    assert latest_legal([candidate], cutoff=cutoff, replay_lag_minutes=5).record_id == "lagged-once"
