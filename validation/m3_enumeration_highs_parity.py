"""V2 M3 enumeration/HiGHS parity validator (Phase 3 diagnostics).

Builds representative, contract-valid PRE and TURN nodes from synthetic
parity-only inputs, solves Stage II on both the formal exact-enumeration path
and the development-time Pyomo + HiGHS backend, and records the parity result.
This validator is a numerical implementation check, not scientific Train
support: the turnaround/headroom samples below are deliberately synthetic and
are labelled as such in the output.

The validator never reads ``artifacts/experiment/final_test`` and leaves
``FINAL_TEST_ACCESS_COUNT`` unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import highspy  # noqa: E402
import pyomo.version  # noqa: E402

from model.M2.consequence_service import (  # noqa: E402
    ConsequenceReferenceBinding,
    M2ConsequenceService,
)
from model.M2.scientific_registry import load_active_v2_cu_registry  # noqa: E402
from model.M3.solver import solve_with_highs  # noqa: E402
from model.M3.stage2 import solve_recovery  # noqa: E402
from model.M3.transition import TransitionContext  # noqa: E402
from model.common.decision_contracts import (  # noqa: E402
    HeadroomSummary,
    HistoryScope,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage  # noqa: E402


PARITY_SOURCE_ID = "SYNTHETIC_PARITY_INPUT_NOT_SCIENTIFIC_TRAIN_SUPPORT"
TURNAROUND_LOWER_BOUND_Q = 24.0
U_MAX_SYNTHETIC = 45.0
SOBT_MINUTES = 600.0

ROWS = {
    "PRE_PARITY_1": (
        (620.0, 90.0, 15.0, 0.5),
        (650.0, 110.0, 20.0, 0.3),
        (680.0, 130.0, 25.0, 0.2),
    ),
    "TURN_PARITY_1": (
        (560.0, 100.0, 15.0, 0.5),
        (580.0, 120.0, 20.0, 0.3),
        (600.0, 140.0, 25.0, 0.2),
    ),
}

BINDINGS = {
    "PRE_PARITY_1": ConsequenceReferenceBinding(
        reference_id="PRE_PARITY_1",
        turnaround_reference_minutes=TURNAROUND_LOWER_BOUND_Q,
        taxi_reference_minutes=0.0,
        expected_pax=150.0,
        connection_share=0.35,
        downstream_exposure=1.2,
    ),
    "TURN_PARITY_1": ConsequenceReferenceBinding(
        reference_id="TURN_PARITY_1",
        turnaround_reference_minutes=TURNAROUND_LOWER_BOUND_Q,
        taxi_reference_minutes=0.0,
        expected_pax=150.0,
        connection_share=0.35,
        downstream_exposure=1.2,
    ),
}


def _representation() -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _state_set(node_id: str, stage: OperationalStage) -> StateScenarioSet:
    rows = ROWS[node_id]
    scenarios = tuple(
        StateScenario(
            scenario_id=index,
            scenario_weight=weight,
            stage=stage,
            t_ib_minutes=t_ib,
            d_ob_minutes=d_ob,
            d_tx_minutes=d_tx,
            d_to_minutes=d_ob + d_tx,
        )
        for index, (t_ib, d_ob, d_tx, weight) in enumerate(rows)
    )
    return StateScenarioSet(
        episode_id=f"episode-{node_id}",
        chain_id=f"chain-{node_id}",
        node_id=node_id,
        stage=stage,
        representation=_representation(),
        scenarios=scenarios,
    )


def _headroom_summary() -> HeadroomSummary:
    return HeadroomSummary(
        u_max=U_MAX_SYNTHETIC,
        turnaround_lower_bound_q=TURNAROUND_LOWER_BOUND_Q,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id=PARITY_SOURCE_ID,
        floor_to_minutes=5.0,
    )


def run_cases() -> dict:
    registry = load_active_v2_cu_registry()
    service = M2ConsequenceService(registry, BINDINGS)
    summary = _headroom_summary()
    context = TransitionContext(
        sobt_minutes=SOBT_MINUTES,
        turnaround_lower_bound_minutes=TURNAROUND_LOWER_BOUND_Q,
    )

    records = []
    for node_id, stage in (
        ("PRE_PARITY_1", OperationalStage.PRE_IB),
        ("TURN_PARITY_1", OperationalStage.POST_IB_PRE_OB),
    ):
        state_set = _state_set(node_id, stage)
        result = solve_with_highs(
            state_set,
            context=context,
            service=service,
            headroom_summary=summary,
        )
        record = result.to_dict()
        denominator = max(abs(result.j_star_enumeration), 1e-12)
        record["objective_relative_error"] = (
            result.objective_absolute_error / denominator
        )
        records.append(record)

    taxi_source = _state_set("PRE_PARITY_1", OperationalStage.POST_OB_PRE_TO)
    taxi_state = StateScenarioSet(
        episode_id="episode-TAXI_PARITY_1",
        chain_id="chain-TAXI_PARITY_1",
        node_id="TAXI_PARITY_1",
        stage=OperationalStage.POST_OB_PRE_TO,
        representation=taxi_source.representation,
        scenarios=taxi_source.scenarios,
    )
    taxi_decision = solve_recovery(
        taxi_state,
        context=context,
        service=service,
    )

    all_parity = all(
        record["u_star_parity"] and record["objective_parity"]
        for record in records
    )
    taxi_typed = (
        taxi_decision.actionable_status is TypedStatus.NOT_ACTIONABLE
        and taxi_decision.action_grid == (0.0,)
        and taxi_decision.u_star == 0.0
        and taxi_decision.recoverable_value is None
    )
    passed = all_parity and taxi_typed
    return {
        "validator_id": "V2_M3_ENUMERATION_HIGHS_PARITY",
        "scope": "DEVELOPMENT_TIME_PARITY_BACKEND_ONLY",
        "formal_path": "EXACT_ENUMERATION",
        "parity_backend": "PYOMO_HIGHS",
        "pyomo_version": pyomo.version.version,
        "highspy_version": highspy.Highs().version(),
        "input_provenance": PARITY_SOURCE_ID,
        "synthetic_parity_inputs": True,
        "node_stage_classes": ["PRE", "TURN"],
        "representative_nodes": records,
        "all_enumeration_highs_parity_passed": all_parity,
        "taxi_comp_typed_check": {
            "stage": taxi_decision.stage.value,
            "actionable_status": taxi_decision.actionable_status.value,
            "action_grid": list(taxi_decision.action_grid),
            "u_star": taxi_decision.u_star,
            "recoverable_value": taxi_decision.recoverable_value,
            "solver_status": taxi_decision.solver_status.value,
            "passed": taxi_typed,
        },
        "final_test_access_count": 0,
        "final_test_paths_read": [],
        "status": "PASS" if passed else "FAIL",
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate M3 exact-enumeration/HiGHS parity"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "artifacts/diagnostics/v2_phase3/"
            "M3_ENUMERATION_HIGHS_PARITY.json"
        ),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    report = run_cases()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(output)
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
