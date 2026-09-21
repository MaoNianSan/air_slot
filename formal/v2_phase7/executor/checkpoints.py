"""Immutable, hash-validated Phase-7 stage checkpoints.

Every DAG stage writes exactly one checkpoint document under the executor
output root. A checkpoint records

* the frozen schema tag of the stage,
* the content hash of its payload,
* the file hash of the written document, and
* the payload hash of every upstream stage it consumed.

Reading a checkpoint re-validates the content hash, so a downstream stage can
only ever consume an immutable, validated upstream checkpoint. Resume reuses a
checkpoint only when its recorded upstream hashes still match.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..errors import TypedBlocker, _require
from ..materialization import _assert_not_legacy_final_test, _file_sha256, _write_json_atomic
from . import stages as S


def _canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(payload: Mapping[str, Any]) -> str:
    """Content hash of a stage payload (structural equality, not formatting)."""

    from hashlib import sha256

    try:
        body = _canonical_payload_bytes(payload)
    except ValueError as error:  # non-finite float or unserializable value
        raise TypedBlocker(
            "PHASE7_CHECKPOINT_PAYLOAD_NOT_CANONICAL_JSON", str(error)
        ) from error
    return "sha256:" + sha256(body).hexdigest()


@dataclass(frozen=True)
class CheckpointRecord:
    """Location and hashes of one validated stage checkpoint."""

    stage: str
    path: str
    payload_hash: str
    file_sha256: str
    dependencies: Mapping[str, str] = field(default_factory=dict)
    produced_by: str = ""
    reused: bool = False
    schema_version: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "path": self.path,
            "payload_hash": self.payload_hash,
            "file_sha256": self.file_sha256,
            "dependencies": dict(self.dependencies),
            "produced_by": self.produced_by,
            "reused": bool(self.reused),
            "schema_version": self.schema_version,
        }


class CheckpointStore:
    """Filesystem store for the frozen DAG checkpoints."""

    def __init__(self, root: Path, *, namespace: str = "v1") -> None:
        self.root = Path(root)
        self.namespace = str(namespace)
        _assert_not_legacy_final_test(self.root)

    def path_for(self, stage: str) -> Path:
        if stage not in S.SCIENCE_DAG_STAGES:
            raise TypedBlocker("PHASE7_UNKNOWN_DAG_STAGE", stage)
        return self.root / f"{stage}.json"

    # -- writes ---------------------------------------------------------
    def write(
        self,
        stage: str,
        payload: Mapping[str, Any],
        *,
        dependencies: Mapping[str, CheckpointRecord],
        produced_by: str,
    ) -> CheckpointRecord:
        schema = S.schema_version(stage)
        body = dict(payload)
        body["schema_version"] = schema
        body["stage"] = stage
        dependent = {
            name: record.payload_hash for name, record in dependencies.items()
        }
        expected = tuple(S.STAGE_DEPENDENCIES[stage])
        _require(
            set(dependent) == set(expected),
            "PHASE7_CHECKPOINT_DEPENDENCY_SET_MISMATCH",
            {"stage": stage, "expected": list(expected), "actual": sorted(dependent)},
        )
        document = {
            "checkpoint_schema_version": "AIR_SLOT_V2_PHASE7_CHECKPOINT_V1",
            "stage": stage,
            "schema_version": schema,
            "payload_hash": content_hash(body),
            "dependencies": dict(dependent),
            "produced_by": str(produced_by),
            "payload": body,
        }
        target = self.path_for(stage)
        _write_json_atomic(target, document)
        return CheckpointRecord(
            stage=stage,
            path=str(target),
            payload_hash=document["payload_hash"],
            file_sha256=_file_sha256(target),
            dependencies=dependent,
            produced_by=str(produced_by),
            reused=False,
            schema_version=schema,
        )

    # -- reads ----------------------------------------------------------
    def read(self, stage: str) -> dict[str, Any]:
        target = self.path_for(stage)
        _assert_not_legacy_final_test(target)
        _require(target.is_file(), "PHASE7_CHECKPOINT_MISSING", str(target))
        document = json.loads(target.read_text(encoding="utf-8"))
        _require(
            document.get("checkpoint_schema_version")
            == "AIR_SLOT_V2_PHASE7_CHECKPOINT_V1",
            "PHASE7_CHECKPOINT_SCHEMA_MISMATCH",
            str(target),
        )
        _require(
            document.get("stage") == stage,
            "PHASE7_CHECKPOINT_STAGE_MISMATCH",
            str(target),
        )
        _require(
            document.get("schema_version") == S.schema_version(stage),
            "PHASE7_CHECKPOINT_STAGE_SCHEMA_MISMATCH",
            stage,
        )
        payload = document.get("payload")
        _require(
            isinstance(payload, dict),
            "PHASE7_CHECKPOINT_PAYLOAD_MISSING",
            str(target),
        )
        _require(
            document.get("payload_hash") == content_hash(payload),
            "PHASE7_CHECKPOINT_CONTENT_HASH_MISMATCH",
            str(target),
        )
        return payload

    def record(self, stage: str, *, reused: bool = False) -> CheckpointRecord:
        target = self.path_for(stage)
        document = json.loads(target.read_text(encoding="utf-8"))
        payload = document["payload"]
        _require(
            document.get("payload_hash") == content_hash(payload),
            "PHASE7_CHECKPOINT_CONTENT_HASH_MISMATCH",
            str(target),
        )
        return CheckpointRecord(
            stage=stage,
            path=str(target),
            payload_hash=document["payload_hash"],
            file_sha256=_file_sha256(target),
            dependencies=dict(document.get("dependencies", {})),
            produced_by=str(document.get("produced_by", "")),
            reused=reused,
            schema_version=str(document.get("schema_version", "")),
        )

    def has(self, stage: str) -> bool:
        return self.path_for(stage).is_file()

    def is_reusable(
        self, stage: str, dependencies: Mapping[str, CheckpointRecord]
    ) -> bool:
        """True when the stored checkpoint still matches its upstream hashes."""

        if not self.has(stage):
            return False
        target = self.path_for(stage)
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if document.get("schema_version") != S.schema_version(stage):
            return False
        stored = dict(document.get("dependencies", {}))
        expected = {
            name: record.payload_hash for name, record in dependencies.items()
        }
        return stored == expected


__all__ = [
    "CheckpointRecord",
    "CheckpointStore",
    "content_hash",
]
