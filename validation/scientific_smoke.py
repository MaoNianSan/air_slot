"""Retired legacy smoke boundary.

P0/P1 removed the scientific validity of injecting placeholder D1-D5 context
and DEV-1 valuation into an M2-to-M4 chain. A new real smoke is intentionally
blocked until the user separately authorizes the scientific freeze.
"""

from model.common.errors import ContractError


def run_scientific_smoke(*args, **kwargs):
    raise ContractError(
        "SCIENTIFIC_SMOKE_BLOCKED_PENDING_D1_D5_FREEZE_AND_TYPED_CONTRACT_INPUTS"
    )


def main():
    raise SystemExit(
        "SCIENTIFIC_SMOKE_BLOCKED_PENDING_D1_D5_FREEZE_AND_TYPED_CONTRACT_INPUTS"
    )


if __name__ == "__main__":
    main()
