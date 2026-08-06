from __future__ import annotations

from typing import NoReturn

from .failures import M4ContractMismatch


def finalize_experiment(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M4ContractMismatch(
        "M4_CONTRACT_MISMATCH: global finalization awaits the M4 atomic-subitem migration"
    )
