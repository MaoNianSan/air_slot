"""Data2 factual-replay availability policy (Tranche 3).

A realized operational event is a FACTUAL_REPLAY_EVIDENCE candidate only when
the archive can legally claim it was available at the decision time.  Data2
has no real airline-system message-arrival timestamps, so we never claim the
event time IS the production availability time.  A typed policy decides:

- UNRESOLVED: no formal factual replay is enabled (training labels and
  evaluation outcomes continue to exist normally; inference never consumes the
  realized outcome).  This is the current scientific config state
  (DATA2_FACTUAL_REPLAY_AVAILABILITY = HUMAN_DECISION_REQUIRED).
- DECLARED_RULE: ``availability_time = event_time + declared
  lag`` under an explicitly declared retrospective rule; the evidence is legal
  only when ``availability_time <= information_cutoff``.  Future outcomes that
  exist in the archive are still blocked by the cutoff filter.

The same source record keeps multiple roles (TRAIN_LABEL / EVAL_OUTCOME /
FACTUAL_REPLAY_EVIDENCE); the factual-replay role is the only one that may
enter inference, and only through this legality gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from model.common.errors import ContractError


class Data2FactualReplayAvailabilityPolicy(str, Enum):
    """Typed policy for computing realized-event availability in Data2.

    UNRESOLVED                 no formal factual replay (human decision pending)
    DECLARED_RULE              event_time + declared lag under an explicitly
                               declared rule; cutoff-legal replay allowed
    """

    UNRESOLVED = "UNRESOLVED"
    DECLARED_RULE = "DECLARED_RULE"
    DECLARED_RETROSPECTIVE_RULE = "DECLARED_RETROSPECTIVE_RULE"
    DECLARED_EVENT_TIME_REPLAY = "DECLARED_EVENT_TIME_REPLAY"


def factual_availability_time(
    event_time: datetime,
    policy: Data2FactualReplayAvailabilityPolicy | str,
    *,
    declared_lag_minutes: float | None = None,
) -> datetime | None:
    """Return the typed availability time of an operational fact.

    ``UNRESOLVED`` returns None (factual replay cannot be enabled).  Under
    ``DECLARED_RULE`` the availability time is
    ``event_time + declared_lag_minutes`` (a negative/zero lag is allowed only
    when the rule explicitly declares it; the default rule requires a
    nonnegative lag).  The caller must still verify
    ``availability_time <= information_cutoff`` before publication.
    """
    resolved = (policy.value if isinstance(policy, Data2FactualReplayAvailabilityPolicy)
                else str(policy))
    if resolved == Data2FactualReplayAvailabilityPolicy.UNRESOLVED.value:
        return None
    declared_rules = {
        Data2FactualReplayAvailabilityPolicy.DECLARED_RULE.value,
        Data2FactualReplayAvailabilityPolicy.DECLARED_RETROSPECTIVE_RULE.value,
        Data2FactualReplayAvailabilityPolicy.DECLARED_EVENT_TIME_REPLAY.value,
    }
    if resolved not in declared_rules:
        raise ContractError(f"M1_FACTUAL_AVAILABILITY_POLICY_UNKNOWN:{resolved}")
    if declared_lag_minutes is None:
        raise ContractError("M1_FACTUAL_REPLAY_DECLARED_LAG_REQUIRED")
    lag = float(declared_lag_minutes)
    if lag < 0:
        raise ContractError("M1_FACTUAL_REPLAY_NEGATIVE_DECLARED_LAG")
    return event_time + timedelta(minutes=lag)


def factual_replay_legal(
    *,
    event_time: datetime | None,
    availability_time: datetime | None,
    information_cutoff: datetime,
    policy: Data2FactualReplayAvailabilityPolicy | str,
) -> bool:
    """Cutoff legality gate for FACTUAL_REPLAY_EVIDENCE.

    A future outcome that exists in the archive (``event_time > cutoff``) is
    blocked even if the database already contains it; only
    ``availability_time <= information_cutoff`` makes the fact legal.
    """
    resolved = (policy.value if isinstance(policy, Data2FactualReplayAvailabilityPolicy)
                else str(policy))
    if resolved == Data2FactualReplayAvailabilityPolicy.UNRESOLVED.value:
        return False
    if availability_time is None or event_time is None:
        return False
    # Independently gate both timestamps.  This keeps a malformed externally
    # supplied availability record from making a future event visible.
    return event_time <= information_cutoff and availability_time <= information_cutoff
