from __future__ import annotations

from typing import NoReturn

from .failures import M3ContractMismatch


def finalize_experiment(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: global finalization awaits M3 and M4 contract migration"
    )
