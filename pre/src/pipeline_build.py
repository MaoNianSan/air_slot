from __future__ import annotations

from typing import Any

from .pipeline_config import BuildResult
from .stages.context import create_build_context
from .stages.enrichment_stage import run_enrichment_stage
from .stages.episode_stage import run_episode_stage
from .stages.finalization_stage import run_finalization_stage
from .stages.inventory_stage import run_inventory_stage
from .stages.state_stage import run_state_stage
from .stages.validation_stage import run_validation_stage


def build_all(cfg: dict[str, Any]) -> BuildResult:
    """Run the legacy PRE stages without changing its published contract."""
    ctx = create_build_context(cfg)
    try:
        run_inventory_stage(ctx)
        run_episode_stage(ctx)
        run_state_stage(ctx)
        run_enrichment_stage(ctx)
        run_validation_stage(ctx)
        return run_finalization_stage(ctx)
    except Exception:
        ctx.heartbeat.close()
        raise
