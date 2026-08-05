from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pre.src.core.contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, SCHEMA_VERSION


M1_CONTRACT_ID = "M1_CHAIN_DYNAMIC_DISTRIBUTION_V1"
REQUIRED_TARGETS = {"R_IB", "R_OB", "T_TX"}


class DownstreamContractMismatch(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: str | Path | Mapping[str, Any], label: str) -> tuple[dict[str, Any], Path | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    path = Path(value)
    if not path.is_file():
        raise DownstreamContractMismatch(f"{label}_MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DownstreamContractMismatch(f"{label}_INVALID")
    return payload, path


def require_m1_ready(
    pre_manifest: str | Path | Mapping[str, Any],
    m1_manifest: str | Path | Mapping[str, Any],
    required_stage: str,
) -> dict[str, str]:
    pre, pre_path = _mapping(pre_manifest, "PRE_MANIFEST")
    m1, _ = _mapping(m1_manifest, "M1_MANIFEST")
    expected_pre = {
        "contract_id": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "research_code_revision": RESEARCH_CODE_REVISION,
    }
    for key, expected in expected_pre.items():
        if pre.get(key) != expected:
            raise DownstreamContractMismatch(f"PRE_{key.upper()}_MISMATCH")

    identity = m1.get("pre_bundle_identity", {})
    if not isinstance(identity, Mapping):
        raise DownstreamContractMismatch("M1_PRE_IDENTITY_MISSING")
    for key, expected in expected_pre.items():
        if identity.get(key) != expected:
            raise DownstreamContractMismatch(f"M1_PRE_{key.upper()}_MISMATCH")
    expected_hash = _sha256(pre_path) if pre_path is not None else pre.get("pre_manifest_hash")
    if expected_hash and identity.get("pre_manifest_hash") != expected_hash:
        raise DownstreamContractMismatch("PRE_MANIFEST_HASH_MISMATCH")
    if m1.get("m1_contract_id") != M1_CONTRACT_ID:
        raise DownstreamContractMismatch("M1_CONTRACT_MISMATCH")
    if not m1.get("model_version"):
        raise DownstreamContractMismatch("M1_MODEL_VERSION_MISSING")
    if m1.get("engineering_status") != "PASS":
        raise DownstreamContractMismatch("M1_ENGINEERING_NOT_READY")

    support = m1.get("target_support_status", {})
    if not isinstance(support, Mapping) or not REQUIRED_TARGETS.issubset(support):
        raise DownstreamContractMismatch("M1_TARGET_SUPPORT_INCOMPLETE")
    if any(support[name] == "UNSUPPORTED" for name in REQUIRED_TARGETS):
        raise DownstreamContractMismatch("M1_SCIENTIFIC_NOT_READY")

    stage_fields = {
        "training": "training_status",
        "calibration": "calibration_status",
        "evaluation": "evaluation_status",
        "m2": "m2_interface_status",
    }
    field = stage_fields.get(required_stage)
    if field is None:
        raise ValueError(f"M1_REQUIRED_STAGE_INVALID:{required_stage}")
    if m1.get(field) != "PASS":
        code = "M2_CONTRACT_MISMATCH" if required_stage == "m2" else f"M1_{required_stage.upper()}_NOT_READY"
        raise DownstreamContractMismatch(code)
    return {
        "PRE_IDENTITY": "PASS",
        "M1_ENGINEERING_STATUS": "PASS",
        "M1_TARGET_SUPPORT_STATUS": "PASS",
        "REQUIRED_STAGE": required_stage,
    }


def require_downstream_v2_migration() -> None:
    raise DownstreamContractMismatch(
        "M2_CONTRACT_MISMATCH: M2-M4 have not migrated to the M1 joint-sample contract"
    )
