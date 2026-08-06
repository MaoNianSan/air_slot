from __future__ import annotations

from typing import NoReturn

from .failures import M3ParameterNotFrozen


def fit_artifacts(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise M3ParameterNotFrozen(
        "M3_PARAMETER_NOT_FROZEN: formal downstream fit requires frozen M3 parameters"
    )
