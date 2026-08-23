"""Fail-closed helpers shared by the four official experiment entry points."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from model.common.errors import ContractError


FROZEN_BINDING = Path(
    "artifacts/diagnostics/exp1_formal_execution_preparation/"
    "EXP1_M1_V2_ARTIFACT_BINDING.json"
)
CHECKPOINT = Path(
    "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/"
    "M1_V2_FAST_TRAIN_MODE.pt"
)
CACHE_MANIFEST = Path(
    "artifacts/diagnostics/m1_v2_feature_gate_b2/"
    "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
)
SUPPORT_MANIFEST = Path(
    "artifacts/diagnostics/m1_v2_positive_tail_policy_freeze_v2/"
    "M1_V2_TARGET_SUPPORT_MANIFEST.json"
)
M2_REGISTRY = Path("registries/m2_data2_formal_cu_v1.json")
ACTION_REGISTRY = Path("registries/action_templates.yaml")
RESPONSE_REGISTRY = Path("registries/m3_response_scenarios.yaml")
MAPPING_REGISTRY = Path("registries/m4_cu_rmb_mapping_candidate_v1.json")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"OFFICIAL_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"OFFICIAL_ARTIFACT_MISSING:{path.as_posix()}")
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def require_hash(value: Any, code: str) -> str:
    rendered = str(value or "")
    if not rendered.startswith("sha256:") or len(rendered) != 71:
        raise ContractError(code)
    return rendered


def require_development_safety(payload: dict[str, Any], *, label: str) -> None:
    safety = payload.get("safety", payload)
    final_count = safety.get(
        "FINAL_TEST_ACCESS_COUNT", safety.get("final_test_access_count", 0)
    )
    paper_full = safety.get("PAPER_FULL_RUN", safety.get("paper_full_run", False))
    if final_count != 0:
        raise ContractError(f"{label}_FINAL_TEST_ACCESS_NONZERO")
    if paper_full is not False:
        raise ContractError(f"{label}_PAPER_FULL_FORBIDDEN")
    if safety.get("FULL") is True:
        raise ContractError(f"{label}_FULL_EXECUTION_FORBIDDEN")


def require_active_path(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ContractError(f"OFFICIAL_PATH_OUTSIDE_REPOSITORY:{resolved}") from exc
    if relative.parts and relative.parts[0].lower() == "archive":
        raise ContractError(f"OFFICIAL_ARCHIVE_FALLBACK_FORBIDDEN:{relative.as_posix()}")
    return resolved


@dataclass(frozen=True)
class OfficialFrozenBinding:
    model_hash: str
    schema_hash: str
    cache_hash: str
    support_hash: str
    m2_registry_hash: str
    action_registry_hash: str
    response_registry_hash: str
    mapping_hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "model_hash": self.model_hash,
            "schema_hash": self.schema_hash,
            "cache_hash": self.cache_hash,
            "support_hash": self.support_hash,
            "m2_registry_hash": self.m2_registry_hash,
            "action_registry_hash": self.action_registry_hash,
            "response_registry_hash": self.response_registry_hash,
            "mapping_hash": self.mapping_hash,
        }


def load_official_frozen_binding(root: Path | None = None) -> OfficialFrozenBinding:
    root = (root or repository_root()).resolve()
    paths = {
        "binding": require_active_path(root / FROZEN_BINDING, root),
        "checkpoint": require_active_path(root / CHECKPOINT, root),
        "cache_manifest": require_active_path(root / CACHE_MANIFEST, root),
        "support": require_active_path(root / SUPPORT_MANIFEST, root),
        "m2_registry": require_active_path(root / M2_REGISTRY, root),
        "action_registry": require_active_path(root / ACTION_REGISTRY, root),
        "response_registry": require_active_path(root / RESPONSE_REGISTRY, root),
        "mapping": require_active_path(root / MAPPING_REGISTRY, root),
    }
    if not all(path.is_file() for path in paths.values()):
        missing = [name for name, path in paths.items() if not path.is_file()]
        raise ContractError("OFFICIAL_FROZEN_INPUT_MISSING:" + ",".join(missing))

    binding = load_json(paths["binding"])
    cache = load_json(paths["cache_manifest"])
    support = load_json(paths["support"])
    mapping = load_json(paths["mapping"])
    require_development_safety(binding, label="OFFICIAL_M1_BINDING")
    require_development_safety(cache, label="OFFICIAL_CACHE")
    require_development_safety(support, label="OFFICIAL_SUPPORT")
    if binding.get("status") != "BOUND_FROZEN_M1_V2":
        raise ContractError("OFFICIAL_M1_BINDING_STATUS_INVALID")
    if binding.get("model_id") != "M1_V2_GRU_H32" or binding.get("hidden_size") != 32:
        raise ContractError("OFFICIAL_M1_MODEL_NOT_FROZEN_H32")

    contracts = binding.get("frozen_contracts", {})
    model_hash = require_hash(binding.get("checkpoint", {}).get("sha256"), "OFFICIAL_MODEL_HASH_MISSING")
    schema_hash = require_hash(contracts.get("feature_schema_hash"), "OFFICIAL_SCHEMA_HASH_MISSING")
    cache_hash = require_hash(contracts.get("cache_hash"), "OFFICIAL_CACHE_HASH_MISSING")
    support_hash = require_hash(contracts.get("support_hash"), "OFFICIAL_SUPPORT_HASH_MISSING")
    if file_sha256(paths["checkpoint"]) != model_hash:
        raise ContractError("OFFICIAL_MODEL_HASH_MISMATCH")
    if cache.get("cache_hash") != cache_hash or cache.get("feature_schema_hash") != schema_hash:
        raise ContractError("OFFICIAL_CACHE_CONTRACT_MISMATCH")
    if support_hash not in {
        support.get("artifact_hash"), support.get("support_hash"), file_sha256(paths["support"])
    }:
        raise ContractError("OFFICIAL_SUPPORT_HASH_MISMATCH")
    component_mappings = mapping.get("component_mappings", {})
    if len(component_mappings) != 7:
        raise ContractError("OFFICIAL_MAPPING_COMPONENT_COUNT_INVALID")
    for component_id, item in component_mappings.items():
        parameters = {
            parameter.get("parameter_name"): parameter.get("value")
            for parameter in item.get("parameters", ())
        }
        if item.get("component_id") != component_id or parameters.get("rmb_per_cu") != 1.0:
            raise ContractError(f"OFFICIAL_MAPPING_BASELINE_DRIFT:{component_id}")

    return OfficialFrozenBinding(
        model_hash=model_hash,
        schema_hash=schema_hash,
        cache_hash=cache_hash,
        support_hash=support_hash,
        m2_registry_hash=file_sha256(paths["m2_registry"]),
        action_registry_hash=file_sha256(paths["action_registry"]),
        response_registry_hash=file_sha256(paths["response_registry"]),
        mapping_hash=file_sha256(paths["mapping"]),
    )


def require_files(paths: Iterable[Path], *, code: str) -> None:
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ContractError(f"{code}:" + ",".join(missing))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


__all__ = [
    "OfficialFrozenBinding",
    "file_sha256",
    "load_json",
    "load_official_frozen_binding",
    "repository_root",
    "require_active_path",
    "require_development_safety",
    "require_files",
    "require_hash",
    "write_json",
]
