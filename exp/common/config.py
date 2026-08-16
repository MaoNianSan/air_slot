from __future__ import annotations

from pathlib import Path
import yaml

from model.common.errors import ContractError


def load_evaluation_config(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    forbidden = {"forecast_horizons_minutes", "m1_hidden_size", "m4_lambda", "m4_alpha"}
    if forbidden & set(payload):
        raise ContractError("EVALUATION_CONFIG_CONTAINS_SCIENTIFIC_DEFAULT")
    return payload
