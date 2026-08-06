from __future__ import annotations

from pathlib import Path
from typing import Any

from .m1.adapter import PublishedPreBundle, load_published_bundle
from .m1.contracts import M1_CONTRACT_ID
from .failures import M3ContractMismatch


FORMAL_TARGET_COLUMN = "M1_JOINT_SAMPLE_CONTRACT"
SENSITIVITY_TARGET_COLUMN = "M1_CAPACITY_SENSITIVITY_CONTRACT"
FORMAL_TARGET_CONTRACT_VERSION = M1_CONTRACT_ID
PreBundle = PublishedPreBundle


def load_pre_bundle(
    pre_output: Path,
    scientific: dict[str, Any],
    require_acceptance: bool = True,
) -> PublishedPreBundle:
    del scientific, require_acceptance
    return load_published_bundle(pre_output)


def normalize_bundle(bundle: PublishedPreBundle) -> dict[str, Any]:
    del bundle
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: legacy global tables are retired; use the M1ScenarioBundle to M2InputBundle adapter"
    )


def validate_bundle(
    bundle: PublishedPreBundle,
    scientific: dict[str, Any],
) -> dict[str, Any]:
    del bundle, scientific
    raise M3ContractMismatch(
        "M3_CONTRACT_MISMATCH: global downstream validation has not migrated to M2 V2 sample loss"
    )
