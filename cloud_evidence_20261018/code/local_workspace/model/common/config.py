from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import FreezeState


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScientificParameter(StrictModel):
    freeze_state: FreezeState
    value: Any | None = None

    @model_validator(mode="after")
    def unresolved_has_no_value(self):
        if self.freeze_state in {FreezeState.DEVELOPMENT_FROZEN, FreezeState.UNSUPPORTED} \
                and self.value is not None:
            raise ValueError("unresolved scientific parameter cannot have a value")
        return self


class ScientificConfig(StrictModel):
    schema_version: str
    parameters: dict[str, ScientificParameter]


class ReproducibilityConfig(StrictModel):
    schema_version: str
    seed: int
    fixture_only: bool = True


class EngineeringConfig(StrictModel):
    schema_version: str
    device: str
    workers: int = Field(ge=1)
    logging: str
    raw_roots: dict[str, str | None]


class ConfigLayers(StrictModel):
    scientific: ScientificConfig
    reproducibility: ReproducibilityConfig
    engineering: EngineeringConfig


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_config_layers(root: Path) -> ConfigLayers:
    return ConfigLayers(
        scientific=ScientificConfig.model_validate(_load(root / "scientific/foundation.yaml")),
        reproducibility=ReproducibilityConfig.model_validate(
            _load(root / "reproducibility/smoke.yaml")),
        engineering=EngineeringConfig.model_validate(
            _load(root / "engineering/local.example.yaml")),
    )
