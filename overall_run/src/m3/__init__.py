from __future__ import annotations

from .artifact import M3Artifact
from .catalog import load_actions, load_m3_contract
from .compatibility import M2CompatibilityResult, validate_m2_compatibility
from .contracts import (
    COST_CHANNELS,
    EXPECTED_ACTION_IDS,
    FORBIDDEN_ACTION_IDS,
    M2_SUBITEM_CONTRACT_VERSION,
    M3_ACTION_LIBRARY_VERSION,
    M3_CONTRACT_VERSION,
    M3_RESPONSE_CONTRACT_VERSION,
    SUBITEMS_M2_V2,
    ActionCatalogEntry,
    ActionCostSpec,
    ActionFootprintSpec,
    ActionResponseParameterSpec,
    FootprintRole,
    M3ContractBundle,
    OutcomeCoverage,
    ParameterStatus,
)
from .evaluation import evaluate_m3_structure, sample_count_stability
from .footprint import footprint_counts, footprint_frame, footprint_matrix
from .parameters import SYNTHETIC_FIXTURE_VERSION, synthetic_test_parameters
from .sampling import generate_m3_library, generate_test_fixture_library


__all__ = [
    "COST_CHANNELS",
    "EXPECTED_ACTION_IDS",
    "FORBIDDEN_ACTION_IDS",
    "M2_SUBITEM_CONTRACT_VERSION",
    "M3_ACTION_LIBRARY_VERSION",
    "M3_CONTRACT_VERSION",
    "M3_RESPONSE_CONTRACT_VERSION",
    "SUBITEMS_M2_V2",
    "ActionCatalogEntry",
    "ActionCostSpec",
    "ActionFootprintSpec",
    "ActionResponseParameterSpec",
    "FootprintRole",
    "M2CompatibilityResult",
    "M3Artifact",
    "M3ContractBundle",
    "OutcomeCoverage",
    "ParameterStatus",
    "SYNTHETIC_FIXTURE_VERSION",
    "evaluate_m3_structure",
    "footprint_counts",
    "footprint_frame",
    "footprint_matrix",
    "generate_m3_library",
    "generate_test_fixture_library",
    "load_actions",
    "load_m3_contract",
    "sample_count_stability",
    "synthetic_test_parameters",
    "validate_m2_compatibility",
]
