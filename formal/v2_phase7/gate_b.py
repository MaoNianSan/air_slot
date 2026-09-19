"""Gate-B release validation and the bound Phase-7 scientific executor.

The callback boundary stays explicit: ``execute_gate_b`` still refuses to open
an access epoch unless a pipeline is supplied. The *production* pipeline is now
bound to the real sealed executor
(:mod:`formal.v2_phase7.executor.pipeline`), which materializes
``CANONICAL_NODES`` exactly once through the authorized raw entry and then runs
the frozen nine-stage DAG from immutable checkpoints.

Binding this callback does not authorize anything by itself: no release is
created, no epoch is opened and no raw source is read until a human release is
validated and the epoch is opened by the caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import constants as C
from .access_audit import (
    mark_access_read_completed,
    mark_access_read_started,
    open_access_epoch,
)
from .errors import TypedBlocker
from .materialization import _read_json
from .release import validate_release_schema
from .stage2_authority import (
    production_solver_metadata,
    validate_stage2_production_authority,
)


def execute_gate_b(
    *,
    release_path: Path,
    audit_path: Path | None = None,
    pipeline: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    use_production_executor: bool = False,
) -> dict[str, Any]:
    """Validate a human release and run an explicitly supplied executor.

    Gate A deliberately leaves ``pipeline`` unbound. This prevents an
    accidental Gate-B run from opening the access epoch without a human
    release and a separately reviewed scientific executor.
    """

    release = _read_json(Path(release_path))
    validated = validate_release_schema(release)
    target_audit = (
        Path(audit_path) if audit_path is not None else C.PHASE7_ACCESS_AUDIT_PATH
    )
    if pipeline is None and use_production_executor:
        pipeline = production_pipeline
    if pipeline is None:
        raise TypedBlocker(
            "GATE_B_SCIENTIFIC_EXECUTOR_NOT_BOUND",
            "human release validated, but no sealed Phase-7 executor was supplied",
        )
    binding = production_binding_record() if use_production_executor else None
    epoch = open_access_epoch(target_audit, release)
    mark_access_read_started(target_audit)
    result = pipeline(
        {
            "release": release,
            "release_validation": validated,
            "access_epoch": epoch,
        }
    )
    mark_access_read_completed(target_audit)
    return {
        "status": "PASS",
        "release_validation": validated,
        "access_epoch": epoch,
        "executor_binding": binding,
        "result": result,
    }


PRODUCTION_EXECUTOR_CALLBACK = "formal.v2_phase7.gate_b:production_pipeline"
PRODUCTION_EXECUTOR_MODULE = "formal.v2_phase7.executor.runner"
GATE_B_PRE_OPEN_STATUS = "PRE_OPEN_AUTHORIZATION_READY_ONLY"
GATE_B_PRE_OPEN_STATUS = "PRE_OPEN_AUTHORIZATION_READY_ONLY"


def production_pipeline(context: dict[str, Any]) -> dict[str, Any]:
    """The bound Phase-7 scientific executor callback.

    The executor modules are imported lazily so that binding the callback can
    never read a Final-Test path at import time. The production callback binds
    the real raw-source adapter; the adapter stays inert until the authorized
    raw entry has validated a human release and an open access epoch.
    """

    from .executor.pipeline import run_sealed_pipeline
    from .executor.raw_source import production_raw_adapter

    return run_sealed_pipeline(context, adapter=production_raw_adapter)


def production_binding_record() -> dict[str, Any]:
    """Describe the bound executor without authorizing or opening anything."""

    from .executor import stages as S

    solver = production_solver_metadata()
    authority = validate_stage2_production_authority()

    return {
        "status": "PRODUCTION_EXECUTOR_BOUND",
        "callback_path": PRODUCTION_EXECUTOR_CALLBACK,
        "executor_module": PRODUCTION_EXECUTOR_MODULE,
        "dag_stages": list(S.SCIENCE_DAG_STAGES),
        "stage2_primary_solver": solver["stage2_primary_solver"],
        "final_test_primary_solver": solver["final_test_primary_solver"],
        "highs_role": solver["highs_role"],
        "highs_required_for_production_rows": solver[
            "highs_required_for_production_rows"
        ],
        "deterministic_tie_break": solver["deterministic_tie_break"],
        "solver_status_semantics": solver["solver_status_semantics"],
        "parity_backend": solver["parity_backend"],
        "parity_scope": solver["parity_scope"],
        "stage2_solver_authority": authority,
        "production_executor_bound": True,
        "production_executor_ready": False,
        "gate_b_authorized": False,
        "pre_open_status": GATE_B_PRE_OPEN_STATUS,
        "human_release_present": C.GATE_B_RELEASE_PATH.exists(),
        "access_audit_present": C.PHASE7_ACCESS_AUDIT_PATH.exists(),
        "raw_adapter_status": "GUARDED_ONE_SHOT_NOT_ACTIVATED",
        "raw_adapter_binding": "PRODUCTION_RAW_SOURCE_ADAPTER_BOUND",
        "raw_adapter_id": C.RAW_SOURCE_ADAPTER_ID,
        "raw_adapter_activation": C.RAW_SOURCE_ADAPTER_ACTIVATION,
        "raw_adapter_local_input_root_env": C.PHASE7_LOCAL_INPUT_ROOT_ENV,
        "historical_final_test_access_total": (
            C.HISTORICAL_FINAL_TEST_ACCESS_TOTAL
        ),
        "current_freeze_run_increment": 0,
        "fixed_window_sensitivity_status": S.FIXED_WINDOW_SENSITIVITY_STATUS,
    }


__all__ = [
    "GATE_B_PRE_OPEN_STATUS",
    "PRODUCTION_EXECUTOR_CALLBACK",
    "PRODUCTION_EXECUTOR_MODULE",
    "execute_gate_b",
    "production_binding_record",
    "production_pipeline",
]
