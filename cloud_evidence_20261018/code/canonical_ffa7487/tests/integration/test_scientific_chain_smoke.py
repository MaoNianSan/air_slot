import pytest

from model.common.errors import ContractError
from validation.scientific_smoke import run_scientific_smoke


@pytest.mark.skip(reason="SUPERSEDED_P0_P1_TYPED_CONTRACT_NO_UNFROZEN_DEV_VALUATION_CHAIN")
def test_bounded_data2_and_data1_scientific_chain_smoke(tmp_path):
    """Legacy smoke retired: it injected D1-D5 numbers and DEV-1 into M2/M4."""
    from validation.scientific_smoke import run_scientific_smoke

    run_scientific_smoke(tmp_path, scenario_count=8, seed=13)


def test_legacy_scientific_smoke_cannot_inject_unfrozen_values(tmp_path):
    with pytest.raises(ContractError, match="PENDING_D1_D5_FREEZE"):
        run_scientific_smoke(tmp_path, scenario_count=8, seed=13)
