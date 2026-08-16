from __future__ import annotations

import warnings


DEPRECATION_MESSAGE = "DEPRECATED: use Exp1-Exp4 protocol runners"


def overall_run(*args, formal_pipeline, reporter=None, **kwargs):
    """Compatibility wrapper: formal pipeline plus compact end-to-end reporting."""
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    result = formal_pipeline(*args, **kwargs)
    return reporter(result) if reporter is not None else result


def overall_adv(*_args, **_kwargs):
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    raise RuntimeError("OVERALL_ADV_DEPRECATED_USE_EXP1_EXP4")


def part_adv(*_args, **_kwargs):
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    raise RuntimeError("PART_ADV_DEPRECATED_USE_EXP2_EXP4")
