from __future__ import annotations

import hashlib
import json
from typing import Any


FORMAL_TARGET_COLUMN = "y_movement_raw"
SENSITIVITY_TARGET_COLUMN = "y_movement_model"
FORMAL_TARGET_CONTRACT_VERSION = "Y_MOVEMENT_RAW_V1_20260725"


def _definition_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def target_contract_metadata(cfg: dict[str, Any]) -> dict[str, Any]:
    labels = cfg["labels"]
    transform = labels["sensitivity_transform"]
    formal_definition = {
        "column": FORMAL_TARGET_COLUMN,
        "role": "FORMAL",
        "unit": "minutes",
        "source": "observed_movement_time - reference_movement_time",
        "transform": "NONE",
        "contract_version": FORMAL_TARGET_CONTRACT_VERSION,
    }
    sensitivity_definition = {
        "column": SENSITIVITY_TARGET_COLUMN,
        "role": "SENSITIVITY_ONLY",
        "unit": "minutes",
        "source": FORMAL_TARGET_COLUMN,
        "transform": transform["method"],
        "clip_quantiles": [float(value) for value in transform["clip_quantiles"]],
        "fit_split": transform["fit_split"],
    }
    return {
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_role": "FORMAL",
        "formal_target_transform": "NONE",
        "sensitivity_target_column": SENSITIVITY_TARGET_COLUMN,
        "sensitivity_target_role": "SENSITIVITY_ONLY",
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": _definition_hash(formal_definition),
        "sensitivity_target_definition_hash": _definition_hash(sensitivity_definition),
        "target_lineage": {
            FORMAL_TARGET_COLUMN: {
                "role": "FORMAL_TARGET",
                "evidence_status": "OBSERVED",
                "unit": "minutes",
                "transformation": "NONE",
            },
            SENSITIVITY_TARGET_COLUMN: {
                "role": "SENSITIVITY_TARGET",
                "evidence_status": "DERIVED",
                "unit": "minutes",
                "source": FORMAL_TARGET_COLUMN,
                "transformation": transform["method"],
            },
        },
    }
