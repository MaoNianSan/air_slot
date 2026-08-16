from __future__ import annotations

from pathlib import Path
import json

from model.common.errors import ContractError


def load_frozen_artifact(path: Path) -> dict:
    if not path.is_file():
        raise ContractError("FROZEN_FORMAL_ARTIFACT_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_layer") not in {"FORMAL", "RUNTIME"}:
        raise ContractError("FORMAL_ARTIFACT_LAYER_INVALID")
    if payload.get("immutable") is not True:
        raise ContractError("FORMAL_ARTIFACT_NOT_IMMUTABLE")
    return payload
