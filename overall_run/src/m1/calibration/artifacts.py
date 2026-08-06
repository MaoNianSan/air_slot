from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TemperatureArtifact:
    T_IB: float
    T_OB: float
    T_TX: float
    checkpoint_hash: str
    pre_manifest_hash: str
    feature_schema_hash: str
    calibration_episode_ids: tuple[str, ...]
    calibration_split_hash: str
    objective_value: float
    artifact_version: str
    artifact_hash: str
    formal_status: str = "CALIBRATED"
    identity_fixture: bool = False

    @property
    def values(self) -> dict[str, float]:
        return {"R_IB": self.T_IB, "R_OB": self.T_OB, "T_TX": self.T_TX}

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.values.values()):
            raise ValueError("M1_TEMPERATURE_NOT_POSITIVE")
        if not self.calibration_episode_ids:
            raise ValueError("M1_CALIBRATION_EPISODES_MISSING")
        if self.formal_status != "CALIBRATED" and not self.identity_fixture:
            raise ValueError("M1_TEMPERATURE_ARTIFACT_NOT_CALIBRATED")

    @classmethod
    def build(
        cls,
        *,
        values: Mapping[str, float],
        checkpoint_hash: str,
        pre_manifest_hash: str,
        feature_schema_hash: str,
        calibration_episode_ids: tuple[str, ...],
        objective_value: float,
        artifact_version: str,
    ) -> "TemperatureArtifact":
        split_payload = "|".join(sorted(calibration_episode_ids)).encode("utf-8")
        split_hash = hashlib.sha256(split_payload).hexdigest()
        payload = {
            "T_IB": float(values["R_IB"]),
            "T_OB": float(values["R_OB"]),
            "T_TX": float(values["T_TX"]),
            "checkpoint_hash": checkpoint_hash,
            "pre_manifest_hash": pre_manifest_hash,
            "feature_schema_hash": feature_schema_hash,
            "calibration_episode_ids": list(calibration_episode_ids),
            "calibration_split_hash": split_hash,
            "objective_value": float(objective_value),
            "artifact_version": artifact_version,
            "formal_status": "CALIBRATED",
            "identity_fixture": False,
        }
        return cls(artifact_hash=_hash(payload), **payload)

    def as_dict(self) -> dict[str, object]:
        return {
            "T_IB": self.T_IB,
            "T_OB": self.T_OB,
            "T_TX": self.T_TX,
            "checkpoint_hash": self.checkpoint_hash,
            "pre_manifest_hash": self.pre_manifest_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "calibration_episode_ids": list(self.calibration_episode_ids),
            "calibration_split_hash": self.calibration_split_hash,
            "objective_value": self.objective_value,
            "artifact_version": self.artifact_version,
            "artifact_hash": self.artifact_hash,
            "formal_status": self.formal_status,
            "identity_fixture": self.identity_fixture,
        }


def save_temperature_artifact(
    path: str | Path,
    artifact: TemperatureArtifact,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_temperature_artifact(
    path: str | Path,
    *,
    checkpoint_hash: str,
    pre_manifest_hash: str,
    feature_schema_hash: str,
    formal: bool = True,
) -> TemperatureArtifact:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError("M1_TEMPERATURE_ARTIFACT_MISSING")
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["calibration_episode_ids"] = tuple(payload["calibration_episode_ids"])
    artifact = TemperatureArtifact(**payload)
    expected_hash = _hash(
        {key: value for key, value in artifact.as_dict().items() if key != "artifact_hash"}
    )
    if artifact.artifact_hash != expected_hash:
        raise ValueError("M1_TEMPERATURE_ARTIFACT_HASH_MISMATCH")
    if artifact.checkpoint_hash != checkpoint_hash:
        raise ValueError("M1_CALIBRATION_CHECKPOINT_MISMATCH")
    if artifact.pre_manifest_hash != pre_manifest_hash:
        raise ValueError("M1_CALIBRATION_PRE_MANIFEST_MISMATCH")
    if artifact.feature_schema_hash != feature_schema_hash:
        raise ValueError("M1_CALIBRATION_FEATURE_SCHEMA_MISMATCH")
    if formal and artifact.identity_fixture:
        raise ValueError("M1_IDENTITY_TEMPERATURE_FORMAL_PROHIBITED")
    return artifact
