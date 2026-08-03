from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib


ARTIFACT_ENTRY_SCHEMA_VERSION = "ARTIFACT_ENTRY_V2_20260731"
CORE_REGISTRY_CONTRACT_ID = "OVERALL_RUN_CORE_REGISTRY_V1_20260731"
PUBLICATION_REGISTRY_CONTRACT_ID = "OVERALL_RUN_PUBLICATION_REGISTRY_V1_20260731"
CORE_REQUIRED_ARTIFACT_IDS = (
    "m1.joblib", "m2.joblib", "m3.joblib", "m4.joblib",
    "run_manifest.json", "run_summary.json", "merged_config.json", "config_sources.json",
    "implementation_manifest.json", "audit.parquet", "failure_records.parquet",
    "scientific_gate.json", "model_contract.json", "action_metadata.parquet",
    "m3_action_library.parquet", "m3_response_parameters.parquet",
    "m3_response_samples.parquet", "m3_response_audit.parquet",
    "m4_action_scores.parquet", "m4_candidate_screen.parquet",
    "m4_rankings.parquet", "m4_recommendations.parquet",
    "m4_ranking_all_k.parquet", "m4_ranking_k1.parquet",
    "m4_ranking_k2.parquet", "m4_ranking_k3.parquet",
    "m4_ranking_k5.parquet",
    "parameter_manifest.parquet", "parameter_manifest.json",
)

class ArtifactContractError(RuntimeError):
    pass


@dataclass
class FrozenArtifacts:
    m1: Any
    m2: Any
    m3: Any
    m4: Any
    registry: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_paths(root: Path) -> dict[str, Path]:
    return {
        "m1": root / "m1.joblib",
        "m2": root / "m2.joblib",
        "m3": root / "m3.joblib",
        "m4": root / "m4.joblib",
        "registry": root / "artifact_registry.json",
    }


def save_model_artifacts(root: Path, *, m1: Any, m2: Any, m3: Any, m4: Any) -> None:
    root.mkdir(parents=True, exist_ok=True)
    paths = artifact_paths(root)
    joblib.dump(m1, paths["m1"])
    joblib.dump(m2, paths["m2"])
    joblib.dump(m3, paths["m3"])
    joblib.dump(m4, paths["m4"])


def artifacts_match(
    root: Path,
    *,
    config_hash: str,
    implementation_hash: str,
    pre_hashes: dict[str, str],
) -> bool:
    try:
        registry = validate_registry(
            root,
            expected_config_hash=config_hash,
            expected_implementation_hash=implementation_hash,
            expected_contract_version=None,
            allowed_scientific_statuses={"PASS", "STOP_AND_REVIEW", "FAIL", "UNRESOLVED"},
            expected_registry_kind="core",
            required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
        )
    except Exception:
        return False
    return registry.get("upstream_artifact_hashes") == pre_hashes


def write_artifact_registry(
    root: Path,
    *,
    mode: str,
    run_id: str,
    config_hash: str,
    implementation_hash: str,
    contract_version: str,
    upstream_artifact_hashes: dict[str, str],
    scientific_status: str,
    artifact_names: list[str],
    registry_kind: str = "core",
    required_artifact_ids: list[str] | tuple[str, ...] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if registry_kind not in {"core", "publication"}:
        raise ArtifactContractError(f"ARTIFACT_REGISTRY_KIND_INVALID:{registry_kind}")
    contract_id = (
        CORE_REGISTRY_CONTRACT_ID
        if registry_kind == "core"
        else PUBLICATION_REGISTRY_CONTRACT_ID
    )
    required = tuple(required_artifact_ids or (
        CORE_REQUIRED_ARTIFACT_IDS if registry_kind == "core" else artifact_names
    ))
    names = tuple(sorted(dict.fromkeys(artifact_names)))
    missing_required = sorted(set(required) - set(names))
    if missing_required:
        raise ArtifactContractError(
            "ARTIFACT_REQUIRED_SET_INCOMPLETE:" + ",".join(missing_required)
        )
    created_at = datetime.now(timezone.utc).isoformat()
    artifacts: list[dict[str, Any]] = []
    for name in names:
        path = root / name
        if not path.exists():
            raise ArtifactContractError(f"REQUIRED_ARTIFACT_MISSING:{path}")
        artifacts.append({
            "artifact_name": name,
            "absolute_path": str(path.resolve()),
            "sha256": sha256_file(path),
            "file_size": path.stat().st_size,
            "created_at": created_at,
            "mode": mode,
            "run_id": run_id,
            "config_hash": config_hash,
            "implementation_hash": implementation_hash,
            "contract_version": contract_version,
            "upstream_artifact_hashes": dict(upstream_artifact_hashes),
            "scientific_status": scientific_status,
            "artifact_entry_schema_version": ARTIFACT_ENTRY_SCHEMA_VERSION,
            "registry_contract_id": contract_id,
            **(metadata or {}),
        })
    census_hash = hashlib.sha256(
        json.dumps(names, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    registry = {
        "mode": mode,
        "run_id": run_id,
        "config_hash": config_hash,
        "implementation_hash": implementation_hash,
        "contract_version": contract_version,
        "upstream_artifact_hashes": dict(upstream_artifact_hashes),
        "scientific_status": scientific_status,
        "registry_kind": registry_kind,
        "registry_contract_id": contract_id,
        "artifact_entry_schema_version": ARTIFACT_ENTRY_SCHEMA_VERSION,
        "required_artifact_ids": sorted(required),
        "artifact_census_count": len(names),
        "artifact_census_hash": census_hash,
        "created_at": created_at,
        "artifacts": artifacts,
        **(metadata or {}),
    }
    (root / "artifact_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return registry


def validate_registry(
    root: Path,
    *,
    expected_config_hash: str,
    expected_implementation_hash: str,
    expected_contract_version: str | None,
    allowed_scientific_statuses: set[str],
    expected_registry_kind: str | None = None,
    required_artifact_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    registry_path = root / "artifact_registry.json"
    if not registry_path.exists():
        raise ArtifactContractError(f"ARTIFACT_REGISTRY_MISSING:{registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("config_hash") != expected_config_hash:
        raise ArtifactContractError("ARTIFACT_CONFIG_HASH_MISMATCH")
    if registry.get("implementation_hash") != expected_implementation_hash:
        raise ArtifactContractError("ARTIFACT_IMPLEMENTATION_HASH_MISMATCH")
    if expected_contract_version is not None and registry.get("contract_version") != expected_contract_version:
        raise ArtifactContractError("ARTIFACT_CONTRACT_VERSION_MISMATCH")
    if registry.get("scientific_status") not in allowed_scientific_statuses:
        raise ArtifactContractError("ARTIFACT_SCIENTIFIC_STATUS_INVALID")
    entries = registry.get("artifacts", [])
    names = {str(entry.get("artifact_name")) for entry in entries}
    registry_kind = str(registry.get("registry_kind", "legacy"))
    if expected_registry_kind is not None and registry_kind not in {expected_registry_kind, "legacy"}:
        raise ArtifactContractError("ARTIFACT_REGISTRY_KIND_MISMATCH")
    required = set(required_artifact_ids or (
        CORE_REQUIRED_ARTIFACT_IDS if expected_registry_kind == "core" else
        registry.get("required_artifact_ids", ("m1.joblib", "m2.joblib", "m3.joblib", "m4.joblib"))
    ))
    missing = required - names
    if missing:
        raise ArtifactContractError("ARTIFACT_REQUIRED_SET_INCOMPLETE:" + ",".join(sorted(missing)))
    if registry_kind != "legacy":
        expected_contract_id = (
            CORE_REGISTRY_CONTRACT_ID
            if registry_kind == "core"
            else PUBLICATION_REGISTRY_CONTRACT_ID
        )
        if registry.get("registry_contract_id") != expected_contract_id:
            raise ArtifactContractError("ARTIFACT_REGISTRY_CONTRACT_MISMATCH")
        if registry.get("artifact_census_count") != len(names):
            raise ArtifactContractError("ARTIFACT_CENSUS_COUNT_MISMATCH")
        census_hash = hashlib.sha256(
            json.dumps(tuple(sorted(names)), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if registry.get("artifact_census_hash") != census_hash:
            raise ArtifactContractError("ARTIFACT_CENSUS_HASH_MISMATCH")
    for entry in entries:
        path = Path(str(entry["absolute_path"]))
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ArtifactContractError(f"ARTIFACT_OUTSIDE_MODE_ROOT:{path}") from exc
        if not path.exists():
            raise ArtifactContractError(f"ARTIFACT_FILE_MISSING:{path}")
        if sha256_file(path) != entry.get("sha256"):
            raise ArtifactContractError(f"ARTIFACT_HASH_MISMATCH:{entry.get('artifact_name')}")
        for key, expected in (
            ("config_hash", expected_config_hash),
            ("implementation_hash", expected_implementation_hash),
            ("contract_version", registry.get("contract_version")),
            ("scientific_status", registry.get("scientific_status")),
        ):
            if entry.get(key) != expected:
                raise ArtifactContractError(f"ARTIFACT_ENTRY_{key.upper()}_MISMATCH:{entry.get('artifact_name')}")
        if registry_kind != "legacy":
            if entry.get("artifact_entry_schema_version") != ARTIFACT_ENTRY_SCHEMA_VERSION:
                raise ArtifactContractError(f"ARTIFACT_ENTRY_SCHEMA_MISMATCH:{entry.get('artifact_name')}")
            if entry.get("registry_contract_id") != registry.get("registry_contract_id"):
                raise ArtifactContractError(f"ARTIFACT_ENTRY_REGISTRY_CONTRACT_MISMATCH:{entry.get('artifact_name')}")
    return registry


def load_artifacts(
    root: Path,
    *,
    expected_config_hash: str,
    expected_implementation_hash: str,
    expected_contract_version: str,
    allowed_scientific_statuses: set[str],
) -> FrozenArtifacts:
    registry = validate_registry(
        root,
        expected_config_hash=expected_config_hash,
        expected_implementation_hash=expected_implementation_hash,
        expected_contract_version=expected_contract_version,
        allowed_scientific_statuses=allowed_scientific_statuses,
        expected_registry_kind="core",
        required_artifact_ids=CORE_REQUIRED_ARTIFACT_IDS,
    )
    paths = artifact_paths(root)
    return FrozenArtifacts(
        m1=joblib.load(paths["m1"]),
        m2=joblib.load(paths["m2"]),
        m3=joblib.load(paths["m3"]),
        m4=joblib.load(paths["m4"]),
        registry=registry,
    )
