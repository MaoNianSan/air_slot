from __future__ import annotations

from typing import NoReturn

from .failures import M3ContractMismatch


def fit_artifacts(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: the retired global fit path cannot consume M2 V2 outputs"
    )
