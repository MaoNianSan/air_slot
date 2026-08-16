from __future__ import annotations

from exp.common.stratification import apply_frozen_strata


def decompose_principal_outputs(principal_rows, *, development_frozen_strata):
    return apply_frozen_strata(principal_rows, strata=development_frozen_strata)
