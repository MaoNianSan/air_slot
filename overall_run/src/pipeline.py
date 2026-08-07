from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .config import RunConfig
from .failures import (
    M3ContractMismatch,
    M3FormalLibraryNotReady,
    M3ParameterNotFrozen,
    M4ContractMismatch,
)
from .m3 import load_m3_contract, validate_m2_compatibility
from .m2.contracts import M2InputBundle, M2SampleLoss
from .m3.artifact import M3Artifact
from .m4 import M4FormalArtifact, run_m4_formal_stage
from .pipeline_checkpoint import (
    FullBlockedByFastAcceptance,
    mark_running_staging_incomplete,
    prepare_empty_publish_target,
)
from .pipeline_finalize import finalize_experiment
from .pipeline_modes import report_mode, validate_mode
from .pipeline_precision import run_precision


@dataclass(frozen=True)
class M3RuntimeStatus:
    contract_ready: bool
    compatibility_ready: bool
    parameters_frozen: bool
    formal_library_ready: bool
    detail: str = ""


def inspect_m3_runtime_status(cfg: RunConfig) -> M3RuntimeStatus:
    try:
        contract = load_m3_contract(cfg.scientific)
    except (KeyError, TypeError, ValueError) as exc:
        return M3RuntimeStatus(False, False, False, False, str(exc))
    try:
        validate_m2_compatibility(contract, cfg.scientific["m2"])
    except (KeyError, TypeError, RuntimeError, ValueError) as exc:
        return M3RuntimeStatus(True, False, False, False, str(exc))
    return M3RuntimeStatus(
        contract_ready=True,
        compatibility_ready=True,
        parameters_frozen=contract.parameter_freeze_status == "DONE",
        formal_library_ready=contract.formal_library_status == "READY",
    )


def run_experiment(
    cfg: RunConfig,
    mode: str,
    progress_level: str = "normal",
    pre_output: Path | None = None,
    refit: bool = True,
    *,
    override_fast_gate: bool = False,
    output_name: str | None = None,
    resume_staging: Path | None = None,
    m4_inputs: tuple[M2InputBundle, tuple[M2SampleLoss, ...], M3Artifact] | None = None,
    m4_stage_mapping: Mapping[str, str] | None = None,
    m4_stage_mapping_version: str | None = None,
    m4_output_dir: Path | None = None,
) -> Path | M4FormalArtifact:
    del (
        mode,
        progress_level,
        pre_output,
        refit,
        override_fast_gate,
        output_name,
        resume_staging,
    )
    m3_status = inspect_m3_runtime_status(cfg)
    if not m3_status.contract_ready:
        raise M3ContractMismatch(
            "M3_CONTRACT_MISMATCH: M3 V4 contract could not be loaded: "
            + m3_status.detail
        )
    if not m3_status.compatibility_ready:
        raise M3ContractMismatch(m3_status.detail)
    if not m3_status.parameters_frozen:
        raise M3ParameterNotFrozen(
            "M3_PARAMETER_NOT_FROZEN: M3 V4 structure is implemented, but formal "
            "response and cost parameters require development freeze."
        )
    if not m3_status.formal_library_ready:
        raise M3FormalLibraryNotReady(
            "M3_FORMAL_LIBRARY_NOT_READY: the formal response library has not been generated"
        )
    if m4_inputs is None:
        raise M4ContractMismatch(
            "M4_INPUT_ARTIFACTS_REQUIRED: formal M2 V2 losses and the frozen M3 V4 artifact are required"
        )
    if m4_stage_mapping is None or not m4_stage_mapping_version:
        raise M4ContractMismatch(
            "STAGE_CONTRACT_NOT_FROZEN: formal M4 requires an explicit versioned stage mapping"
        )
    m2_input_bundle, sample_losses, m3_artifact = m4_inputs
    artifact = run_m4_formal_stage(
        m2_input_bundle,
        sample_losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping=m4_stage_mapping,
        stage_mapping_version=m4_stage_mapping_version,
        output_dir=m4_output_dir,
        project_root=cfg.root,
    )
    return finalize_experiment(artifact)


__all__ = [
    "FullBlockedByFastAcceptance",
    "mark_running_staging_incomplete",
    "inspect_m3_runtime_status",
    "prepare_empty_publish_target",
    "report_mode",
    "run_experiment",
    "run_precision",
    "validate_mode",
]
