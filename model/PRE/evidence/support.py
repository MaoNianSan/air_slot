from typing import Any
from model.common.enums import EvidenceClass, SupportState, weaker_or_equal
from model.common.errors import ContractError
from model.common.value_objects import SupportedValue


def validate_transformation(
    output: EvidenceClass, input_ceiling: EvidenceClass
) -> None:
    if not weaker_or_equal(output, input_ceiling):
        raise ContractError("SUPPORT_UPGRADE_FORBIDDEN")


def publish_value(
    value: Any,
    state: SupportState,
    *,
    reason_code: str | None = None,
    evidence_class: EvidenceClass = EvidenceClass.DIRECT,
    support_ceiling: EvidenceClass = EvidenceClass.DIRECT,
    fallback_used: bool = False,
    fallback_registered: bool = False,
    unit: str = "canonical",
) -> SupportedValue:
    if fallback_used and not fallback_registered:
        raise ContractError("UNREGISTERED_FALLBACK")
    return SupportedValue(
        value=value,
        unit=unit,
        evidence_class=evidence_class,
        support_ceiling=support_ceiling,
        support_state=state,
        reason_code=reason_code,
    )
