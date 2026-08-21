"""Train-frozen consequence coarsening contracts for Exp2B.

The coarse representations may never fit against Development/Test rows or
inspect the seven-component values after their transform is constructed.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.identity import content_id


class CoarseResponseContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution: str = Field(pattern=r"^(SCALAR|3CHANNEL)$")
    fit_split: str
    train_population_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    action_response_parameters: dict[str, dict[str, float]]
    source_component_artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contract_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def train_only(self):
        if self.fit_split.lower() != "train":
            raise ValueError("EXP2_COARSE_RESPONSE_TRAIN_ONLY_REQUIRED")
        payload = self.model_dump(mode="json", exclude={"contract_hash"})
        if self.contract_hash != content_id(payload):
            raise ValueError("EXP2_COARSE_RESPONSE_HASH_MISMATCH")
        return self

    @classmethod
    def create(cls, *, resolution: str, train_population_hash: str,
               action_response_parameters: Mapping[str, Mapping[str, float]],
               source_component_artifact_hash: str) -> "CoarseResponseContract":
        payload = {
            "resolution": resolution,
            "fit_split": "train",
            "train_population_hash": train_population_hash,
            "action_response_parameters": {
                str(action): {str(key): float(value) for key, value in parameters.items()}
                for action, parameters in action_response_parameters.items()
            },
            "source_component_artifact_hash": source_component_artifact_hash,
        }
        return cls(**payload, contract_hash=content_id(payload))


def assert_coarse_variant_blind_to_components(payload: Mapping) -> None:
    """Reject residual fine-resolution values at the coarse decision boundary."""
    forbidden = {"component_vector", "components", "seven_component_values"}
    found = forbidden & set(payload)
    if found:
        raise ValueError("EXP2_COARSE_VARIANT_FINE_COMPONENT_ACCESS:" + ",".join(sorted(found)))


__all__ = ["CoarseResponseContract", "assert_coarse_variant_blind_to_components"]
