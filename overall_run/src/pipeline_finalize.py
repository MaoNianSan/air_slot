from __future__ import annotations

from typing import NoReturn

from .failures import M2ContractMismatch


def finalize_experiment(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M2ContractMismatch(
        "M2_CONTRACT_MISMATCH: retired M1 output finalization is disabled"
    )
