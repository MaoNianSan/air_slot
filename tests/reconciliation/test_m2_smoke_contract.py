"""M2 smoke contract: development adapters never produce formal CU."""

from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.common.cu_normalization import CUNormalizationStatus
from model.common.estimand import FormalEstimandStatus
from tests.fixtures.p0_p1_contracts import scope_fixture
from tests.m2.test_mapping import context, scenario, supported


def test_valuation_smoke_never_returns_formal_cu_rows():
    scope = scope_fixture(cu_normalization_registry_id="DEV-1")
    mapper = M2Mapper(ValuationRegistry.smoke(), scope)
    output = mapper.map_scenarios(
        (scenario(),),
        context(turnaround_reference=supported("turnaround_reference", 5)),
    )[0]
    assert all(
        row.cu_status is CUNormalizationStatus.CU_NOT_FROZEN
        for row in output.component_vector.rows
        if row.support_state != "ABSTAIN"
    )
    assert output.formal_estimand_value.status is FormalEstimandStatus.VALUATION_NOT_FROZEN
