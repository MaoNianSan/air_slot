from __future__ import annotations

from typing import NoReturn

from .failures import M2ContractMismatch


def fit_artifacts(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M2ContractMismatch(
        "M2_CONTRACT_MISMATCH: the retired M1 artifact fit path is disabled"
    )
