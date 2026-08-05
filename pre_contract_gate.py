from __future__ import annotations

from pre.src.core.contracts import CONTRACT_ID


class DownstreamContractMismatch(RuntimeError):
    """Raised while the downstream adapter for the current PRE is absent."""


def require_m1_adapter() -> None:
    raise DownstreamContractMismatch(
        "PRE_CONTRACT_MISMATCH:\n"
        f"{CONTRACT_ID} is the only available PRE contract.\n"
        "The current downstream pipeline still expects the removed PRE contract.\n"
        "Implement or enable the M1 Adapter before running M1-M4."
    )
