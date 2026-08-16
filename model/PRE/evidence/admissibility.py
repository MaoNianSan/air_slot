from datetime import datetime
from typing import Any
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


class EvidenceCandidate(FrozenModel):
    record_id: str
    availability_time: datetime
    priority: int
    value: Any


def latest_legal(candidates: list[EvidenceCandidate], *, cutoff: datetime,
                 replay_lag_minutes: int | None) -> EvidenceCandidate:
    if replay_lag_minutes is None:
        raise ContractError("REPLAY_LAG_NOT_FROZEN")
    # Canonicalization has already converted event time to availability time using
    # the declared replay profile. Selection must enforce availability <= cutoff,
    # not apply that lag a second time.
    legal = [candidate for candidate in candidates if candidate.availability_time <= cutoff]
    if not legal:
        raise ContractError("NO_LEGAL_EVIDENCE")
    latest_time = max(candidate.availability_time for candidate in legal)
    latest = [candidate for candidate in legal if candidate.availability_time == latest_time]
    best_priority = min(candidate.priority for candidate in latest)
    best = [candidate for candidate in latest if candidate.priority == best_priority]
    if len({repr(candidate.value) for candidate in best}) > 1:
        raise ContractError("EQUAL_PRIORITY_CONFLICT")
    return sorted(best, key=lambda candidate: candidate.record_id)[0]
