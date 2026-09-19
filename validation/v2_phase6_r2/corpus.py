"""Deterministic non-Test Stage-II validation corpus for Freeze R2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from model.M2.consequence_service import (
    ConsequenceReferenceBinding,
    M2ConsequenceService,
)
from model.M3.stage2 import LAMBDA_GRID, RecoveryPolicy
from model.M3.transition import TransitionContext
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    HeadroomSummary,
    HistoryScope,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage

from validation.v2_phase6_r2.common import PROJECT_ROOT, file_hash


@dataclass(frozen=True)
class Stage2CorpusCase:
    """One complete, contract-valid Stage-II decision input."""

    case_id: str
    fixture_id: str
    state_set: StateScenarioSet
    context: TransitionContext
    service: M2ConsequenceService
    headroom_summary: HeadroomSummary
    policy: RecoveryPolicy
    provenance: str


@dataclass(frozen=True)
class TypedCorpusCase:
    """One non-actionable stage case checked without invoking the solver."""

    case_id: str
    state_set: StateScenarioSet
    context: TransitionContext
    service: M2ConsequenceService
    expected_status: str


@dataclass(frozen=True)
class _Fixture:
    fixture_id: str
    rows: tuple[tuple[int, float, float | None, float | None, float | None], ...]
    sobt_minutes: float
    turnaround_lower_bound_minutes: float
    provenance: str
    binding_mode: str = "GENERAL"


@dataclass(frozen=True)
class _CorpusRegistry:
    scales: dict[str, float]
    registry_id: str = "R2_STAGE2_VALIDATION_CU_REGISTRY"
    registry_hash: str = "sha256:r2-stage2-validation-cu-registry"

    def scale(self, component: str) -> float:
        return self.scales[component]


FIXTURES: tuple[_Fixture, ...] = (
    _Fixture(
        fixture_id="DEFAULT_TURN",
        rows=((0, 1.0, 5.0, 10.0, 0.0),),
        sobt_minutes=0.0,
        turnaround_lower_bound_minutes=0.0,
        provenance="tests/m3/test_stage2_v2.py::_state_set",
        binding_mode="MINIMAL_EXECUTION",
    ),
    _Fixture(
        fixture_id="FRACTIONAL_TURN",
        rows=((0, 1.0, 30.0, 40.0, 10.0),),
        sobt_minutes=100.0,
        turnaround_lower_bound_minutes=20.0,
        provenance="tests/m3/test_stage2_v2.py::test_transition_invariants",
    ),
    _Fixture(
        fixture_id="ZERO_HEADROOM",
        rows=((0, 1.0, 90.0, 10.0, 0.0),),
        sobt_minutes=100.0,
        turnaround_lower_bound_minutes=20.0,
        provenance="tests/m3/test_stage2_v2.py::test_headroom_is_zero",
    ),
    _Fixture(
        fixture_id="PARITY_PRE_ROWS",
        rows=(
            (0, 0.5, 620.0, 90.0, 15.0),
            (1, 0.3, 650.0, 110.0, 20.0),
            (2, 0.2, 680.0, 130.0, 25.0),
        ),
        sobt_minutes=600.0,
        turnaround_lower_bound_minutes=24.0,
        provenance="validation/m3_enumeration_highs_parity.py::ROWS",
    ),
    _Fixture(
        fixture_id="PARITY_TURN_ROWS",
        rows=(
            (0, 0.5, 560.0, 100.0, 15.0),
            (1, 0.3, 580.0, 120.0, 20.0),
            (2, 0.2, 600.0, 140.0, 25.0),
        ),
        sobt_minutes=600.0,
        turnaround_lower_bound_minutes=24.0,
        provenance="validation/m3_enumeration_highs_parity.py::ROWS",
    ),
)

U_MAX_GRID = (0.0, 5.0, 10.0, 25.0, 45.0, 75.0)
SCALE_GRID = (1.0, 2.0, 8.88888888888889)
ACTIONABLE_STAGES = (
    OperationalStage.PRE_IB,
    OperationalStage.POST_IB_PRE_OB,
)
NON_ACTIONABLE_STAGES = (
    OperationalStage.POST_OB_PRE_TO,
    OperationalStage.COMPLETED,
)
CORPUS_SOURCE_FILES = (
    PROJECT_ROOT / "tests" / "m3" / "test_stage2_v2.py",
    PROJECT_ROOT / "validation" / "m3_enumeration_highs_parity.py",
    PROJECT_ROOT / "model" / "M3" / "stage2.py",
    PROJECT_ROOT / "model" / "M3" / "solver.py",
)


def _representation() -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _binding(reference_id: str) -> ConsequenceReferenceBinding:
    return ConsequenceReferenceBinding(
        reference_id=reference_id,
        turnaround_reference_minutes=20.0,
        taxi_reference_minutes=0.0,
        expected_pax=100.0,
        connection_share=0.5,
        downstream_exposure=2.0,
        itinerary_threshold_minutes=45.0,
        service_threshold_minutes=180.0,
    )


def _binding_for_mode(
    reference_id: str, mode: str
) -> ConsequenceReferenceBinding:
    if mode == "GENERAL":
        return _binding(reference_id)
    if mode == "MINIMAL_EXECUTION":
        return ConsequenceReferenceBinding(
            reference_id=reference_id,
            turnaround_reference_minutes=0.0,
            taxi_reference_minutes=0.0,
            expected_pax=1.0,
            connection_share=0.0,
            downstream_exposure=0.0,
            itinerary_threshold_minutes=1000.0,
            service_threshold_minutes=1000.0,
        )
    raise ValueError(f"UNKNOWN_R2_BINDING_MODE:{mode}")


def _service(
    reference_id: str, scale: float, binding_mode: str = "GENERAL"
) -> M2ConsequenceService:
    return M2ConsequenceService(
        _CorpusRegistry(
            scales={component: scale for component in CONSEQUENCE_COMPONENTS}
        ),
        {reference_id: _binding_for_mode(reference_id, binding_mode)},
    )


def _state_set(
    *,
    fixture: _Fixture,
    stage: OperationalStage,
) -> StateScenarioSet:
    scenarios = tuple(
        StateScenario(
            scenario_id=scenario_id,
            scenario_weight=weight,
            stage=stage,
            t_ib_minutes=t_ib,
            d_ob_minutes=d_ob,
            d_tx_minutes=d_tx,
            d_to_minutes=(
                None
                if d_ob is None or d_tx is None
                else float(d_ob) + float(d_tx)
            ),
        )
        for scenario_id, weight, t_ib, d_ob, d_tx in fixture.rows
    )
    return StateScenarioSet(
        episode_id=f"episode-{fixture.fixture_id}",
        chain_id=f"chain-{fixture.fixture_id}",
        node_id=f"node-{fixture.fixture_id}",
        stage=stage,
        representation=_representation(),
        scenarios=scenarios,
    )


def _headroom_summary(
    fixture: _Fixture,
    *,
    u_max: float,
) -> HeadroomSummary:
    return HeadroomSummary(
        u_max=u_max,
        turnaround_lower_bound_q=fixture.turnaround_lower_bound_minutes,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id="R2_NON_TEST_VALIDATION_CORPUS",
        floor_to_minutes=5.0,
    )


def actionable_cases() -> tuple[Stage2CorpusCase, ...]:
    """Return the full deterministic non-Test actionable validation corpus."""

    cases: list[Stage2CorpusCase] = []
    for fixture in FIXTURES:
        for stage in ACTIONABLE_STAGES:
            for u_max in U_MAX_GRID:
                for lambda_policy in LAMBDA_GRID:
                    for scale in SCALE_GRID:
                        case_id = (
                            f"{fixture.fixture_id}|{stage.value}|U{u_max:g}|"
                            f"L{lambda_policy:g}|S{scale:g}"
                        )
                        cases.append(
                            Stage2CorpusCase(
                                case_id=case_id,
                                fixture_id=fixture.fixture_id,
                                state_set=_state_set(fixture=fixture, stage=stage),
                                context=TransitionContext(
                                    sobt_minutes=fixture.sobt_minutes,
                                    turnaround_lower_bound_minutes=(
                                        fixture.turnaround_lower_bound_minutes
                                    ),
                                ),
                                service=_service(
                                    f"node-{fixture.fixture_id}",
                                    scale,
                                    fixture.binding_mode,
                                ),

                                headroom_summary=_headroom_summary(
                                    fixture, u_max=u_max
                                ),
                                policy=RecoveryPolicy(
                                    lambda_policy=lambda_policy
                                ).validate(),
                                provenance=fixture.provenance,
                            )
                        )
    return tuple(sorted(cases, key=lambda item: item.case_id))


def typed_non_actionable_cases() -> tuple[TypedCorpusCase, ...]:
    """Return the exact TAXI/COMP typed-state cases from the solver contract."""

    fixture = FIXTURES[0]
    cases = []
    for stage in NON_ACTIONABLE_STAGES:
        cases.append(
            TypedCorpusCase(
                case_id=f"TYPED|{stage.value}",
                state_set=_state_set(fixture=fixture, stage=stage),
                context=TransitionContext(
                    sobt_minutes=fixture.sobt_minutes,
                    turnaround_lower_bound_minutes=(
                        fixture.turnaround_lower_bound_minutes
                    ),
                ),
                service=_service(
                    f"node-{fixture.fixture_id}", 1.0, fixture.binding_mode
                ),

                expected_status="NOT_ACTIONABLE",
            )
        )
    return tuple(cases)


def corpus_manifest() -> dict[str, object]:
    """Describe the corpus and the non-Test source files that define its scope."""

    actionable = actionable_cases()
    typed = typed_non_actionable_cases()
    return {
        "scope": "ALL_AVAILABLE_NON_TEST_STAGE2_VALIDATION_CASES",
        "source_scope_note": (
            "The corpus is the full factorial closure of every admissible "
            "Stage-II validation fixture found in the repository call sites, "
            "plus the exact TAXI/COMP typed cases. It does not claim a "
            "persisted Test corpus."
        ),
        "fixture_count": len(FIXTURES),
        "actionable_case_count": len(actionable),
        "typed_non_actionable_case_count": len(typed),
        "total_case_count": len(actionable) + len(typed),
        "dimensions": {
            "fixtures": [item.fixture_id for item in FIXTURES],
            "actionable_stages": [item.value for item in ACTIONABLE_STAGES],
            "u_max_grid": list(U_MAX_GRID),
            "lambda_grid": list(LAMBDA_GRID),
            "scale_grid": list(SCALE_GRID),
            "non_actionable_stages": [
                item.value for item in NON_ACTIONABLE_STAGES
            ],
        },
        "source_files": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): file_hash(path)
            for path in CORPUS_SOURCE_FILES
        },
    }


__all__ = [
    "ACTIONABLE_STAGES",
    "CORPUS_SOURCE_FILES",
    "FIXTURES",
    "LAMBDA_GRID",
    "SCALE_GRID",
    "Stage2CorpusCase",
    "TypedCorpusCase",
    "U_MAX_GRID",
    "actionable_cases",
    "corpus_manifest",
    "typed_non_actionable_cases",
]
