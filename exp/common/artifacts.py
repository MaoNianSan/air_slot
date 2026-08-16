from __future__ import annotations

from pathlib import Path
import json

from model.common.errors import ContractError


ARTIFACT_NAMESPACES = ("formal", "exp1", "exp2", "exp3", "exp4", "llm_audit", "diagnostics")


def ensure_artifact_namespace(root: Path) -> dict[str, Path]:
    paths = {}
    for name in ARTIFACT_NAMESPACES:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        paths[name] = path
    return paths


def load_frozen_artifact(path: Path) -> dict:
    if not path.is_file():
        raise ContractError("FROZEN_FORMAL_ARTIFACT_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_layer") not in {"FORMAL", "RUNTIME"}:
        raise ContractError("FORMAL_ARTIFACT_LAYER_INVALID")
    if payload.get("immutable") is not True:
        raise ContractError("FORMAL_ARTIFACT_NOT_IMMUTABLE")
    return payload


def write_evaluation_artifact(path: Path, payload: dict, *, formal_output_hash: str) -> Path:
    if not formal_output_hash or formal_output_hash == "UNSET":
        raise ContractError("EVALUATION_FORMAL_HASH_REQUIRED")
    if path.exists():
        raise ContractError("EVALUATION_ARTIFACT_OVERWRITE_REJECTED")
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {**payload, "artifact_layer": "EVALUATION",
              "formal_output_hash": formal_output_hash, "mutates_formal": False}
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return path
