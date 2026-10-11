"""Supplementary E1 Delay+Exposure score adapters.

These adapters consume the existing delay comparator ``P^D`` and train-frozen
reference values.  They do not alter Stage-I selection or the formal
consequence registry.  The passenger-time and downstream-exposure views are
reported separately so their incremental effects remain identifiable.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from model.M2.contracts import ScientificContextValue
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import SupportState
from model.common.errors import ContractError


PASSENGER_TIME_FORMULA = "P^D * expected_passengers_per_flight"
DOWNSTREAM_EXPOSURE_FORMULA = "P^D * expected_downstream_exposure"


@dataclass(frozen=True)
class DelayExposureScore:
    """One typed supplementary score with explicit reference lineage."""

    score_id: str
    formula: str
    unit: str
    score: float | None
    support: SupportState
    status: TypedStatus
    reason_codes: tuple[str, ...]
    reference_lineage: tuple[str, ...]


def _reference_value(
    reference: ScientificContextValue, *, field_name: str
) -> tuple[float | None, SupportState, TypedStatus, tuple[str, ...]]:
    if reference.support_state is SupportState.ABSTAIN:
        return (
            None,
            SupportState.ABSTAIN,
            TypedStatus.ABSTAIN_NO_EVIDENCE,
            (f"{field_name}_ABSTAIN",),
        )
    try:
        value = float(reference.value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"E1_{field_name}_VALUE_NOT_NUMERIC") from exc
    if not isfinite(value) or value < 0.0:
        raise ContractError(f"E1_{field_name}_VALUE_INVALID")
    status = (
        TypedStatus.DEGRADED
        if reference.support_state is SupportState.DEGRADED
        else TypedStatus.SUPPORTED
    )
    return value, reference.support_state, status, (reference.lineage_hash,)


def _score(
    *,
    signal: PrioritySignal,
    reference: ScientificContextValue,
    field_name: str,
    score_id: str,
    formula: str,
    unit: str,
) -> DelayExposureScore:
    if signal.signal_type is not SignalKind.DELAY:
        raise ContractError("E1_DELAY_EXPOSURE_REQUIRES_DELAY_SIGNAL")
    reference_value, reference_support, reference_status, lineage = _reference_value(
        reference, field_name=field_name
    )
    if signal.support is SupportState.ABSTAIN or signal.score is None:
        return DelayExposureScore(
            score_id=score_id,
            formula=formula,
            unit=unit,
            score=None,
            support=SupportState.ABSTAIN,
            status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
            reason_codes=("P_D_ABSTAIN",),
            reference_lineage=lineage,
        )
    if reference_value is None:
        return DelayExposureScore(
            score_id=score_id,
            formula=formula,
            unit=unit,
            score=None,
            support=SupportState.ABSTAIN,
            status=reference_status,
            reason_codes=(f"{field_name}_ABSTAIN",),
            reference_lineage=lineage,
        )
    support = (
        SupportState.DEGRADED
        if signal.support is SupportState.DEGRADED
        or reference_support is SupportState.DEGRADED
        else SupportState.SUPPORTED
    )
    status = (
        TypedStatus.DEGRADED
        if support is SupportState.DEGRADED
        else TypedStatus.SUPPORTED
    )
    return DelayExposureScore(
        score_id=score_id,
        formula=formula,
        unit=unit,
        score=float(signal.score) * reference_value,
        support=support,
        status=status,
        reason_codes=signal.reason_codes,
        reference_lineage=lineage,
    )


def build_delay_exposure_scores(
    signal: PrioritySignal,
    *,
    expected_passengers_per_flight: ScientificContextValue,
    expected_downstream_exposure: ScientificContextValue,
) -> tuple[DelayExposureScore, DelayExposureScore]:
    """Return the approved passenger and downstream views in fixed order."""

    return (
        _score(
            signal=signal,
            reference=expected_passengers_per_flight,
            field_name="EXPECTED_PASSENGERS",
            score_id="DELAY_EXPOSURE_PASSENGER_TIME",
            formula=PASSENGER_TIME_FORMULA,
            unit="passenger_minutes_proxy",
        ),
        _score(
            signal=signal,
            reference=expected_downstream_exposure,
            field_name="EXPECTED_DOWNSTREAM_EXPOSURE",
            score_id="DELAY_EXPOSURE_DOWNSTREAM",
            formula=DOWNSTREAM_EXPOSURE_FORMULA,
            unit="exposure_minutes_proxy",
        ),
    )


__all__ = [
    "DOWNSTREAM_EXPOSURE_FORMULA",
    "DelayExposureScore",
    "PASSENGER_TIME_FORMULA",
    "build_delay_exposure_scores",
]
