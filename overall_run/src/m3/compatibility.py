from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping

from .contracts import M3ContractBundle


@dataclass(frozen=True)
class M2CompatibilityResult:
    status: str
    m2_contract_version: str
    subitem_contract_version: str
    constructed_unit_version: str
    valuation_version: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return value
    raise RuntimeError("M3_M2_CONTRACT_MISMATCH:unsupported compatibility input")


def _mismatch(reason: str) -> RuntimeError:
    return RuntimeError(f"M3_M2_CONTRACT_MISMATCH:{reason}")


def validate_m2_compatibility(
    contract: M3ContractBundle,
    m2_source: Mapping[str, Any] | Any,
) -> M2CompatibilityResult:
    m2 = _mapping(m2_source)
    if "m2" in m2:
        m2 = _mapping(m2["m2"])
    identity = str(m2.get("identity", m2.get("m2_contract_version", "")))
    if identity != contract.required_m2["contract_version"]:
        raise _mismatch("m2 contract")
    subitem_contract = str(m2.get("subitem_contract_version", ""))
    if subitem_contract != contract.required_m2["subitem_contract_version"]:
        raise _mismatch("subitem contract")
    constructed = _mapping(m2.get("constructed_units", {}))
    cu_version = str(m2.get("constructed_unit_version", constructed.get("version", "")))
    if cu_version != contract.required_m2["constructed_unit_version"]:
        raise _mismatch("constructed unit version")
    valuation = str(m2.get("valuation_version", ""))
    if valuation != contract.required_m2["valuation_version"]:
        raise _mismatch("valuation version")
    return M2CompatibilityResult(
        status="PASS",
        m2_contract_version=identity,
        subitem_contract_version=subitem_contract,
        constructed_unit_version=cu_version,
        valuation_version=valuation,
    )
