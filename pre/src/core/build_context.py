from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import ResumeContract, core_output_root, frozen_config_hash


@dataclass(frozen=True)
class CoreBuildResult:
    output_root: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]
    readiness: dict[str, Any]
    publication_status: str


@dataclass
class BuildContext:
    cfg: dict[str, Any]
    output: Path
    raw_inventory: pd.DataFrame = field(default_factory=pd.DataFrame)
    inventory_status: dict[str, Any] = field(default_factory=dict)
    coverage: pd.DataFrame = field(default_factory=pd.DataFrame)
    flights: pd.DataFrame = field(default_factory=pd.DataFrame)
    airports: pd.DataFrame = field(default_factory=pd.DataFrame)
    metar: pd.DataFrame = field(default_factory=pd.DataFrame)
    passengers: pd.DataFrame = field(default_factory=pd.DataFrame)
    commercial: pd.DataFrame = field(default_factory=pd.DataFrame)
    episodes: pd.DataFrame = field(default_factory=pd.DataFrame)
    events: pd.DataFrame = field(default_factory=pd.DataFrame)
    requests: pd.DataFrame = field(default_factory=pd.DataFrame)
    state_store: Any = None
    extraction: dict[str, Any] = field(default_factory=dict)
    cache_manifest: dict[str, Any] = field(default_factory=dict)
    resume_contract: ResumeContract | None = None
    staging: Path | None = None
    observation_result: Any = None
    membership_result: Any = None
    calibration: pd.DataFrame = field(default_factory=pd.DataFrame)
    evidence: pd.DataFrame = field(default_factory=pd.DataFrame)
    registry: list[dict[str, Any]] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    publication_status: str = "NOT_STARTED"


def create_build_context(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> BuildContext:
    cfg["frozen_config_hash"] = frozen_config_hash(cfg)
    return BuildContext(cfg=cfg, output=core_output_root(cfg, output_override))
