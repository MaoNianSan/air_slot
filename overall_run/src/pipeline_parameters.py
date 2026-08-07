from __future__ import annotations

from typing import Any

import pandas as pd

from .config import RunConfig


def parameter_manifest(
    cfg: RunConfig,
    m1: Any,
    m2: Any,
    m3: Any,
    m4: Any,
) -> pd.DataFrame:
    """Publish parameter provenance without recomputing model results."""
    rows: list[dict[str, Any]] = []

    def add(
        module: str,
        parameter: str,
        value: Any,
        unit: str,
        role: str,
        source_type: str,
        source_detail: str,
        frozen_stage: str,
        used_by: str,
        config_path: str,
    ) -> None:
        rows.append({
            "module": module,
            "parameter": parameter,
            "value": value,
            "unit": unit,
            "role": role,
            "source_type": source_type,
            "source_detail": source_detail,
            "frozen_stage": frozen_stage,
            "used_by": used_by,
            "config_path": config_path,
        })

    for key, value in dict(getattr(m1, "selected_config", {})).items():
        add("M1", key, value, "model parameter", "quantile-model configuration", "validation-frozen", "blocked development/validation selection", "before formal evaluation", "M1", f"m1_tuning.curated_configs.{key}")
    for edge, value in m2.graph_edges.items():
        add("M2", f"graph_edges.{edge}", value, "exposure loading", "cross-channel loss coupling", "literature-calibrated", "frozen primary specification", "before formal evaluation", "M2", f"m2.graph_edges.{edge}")
    for channel in ("F", "P", "R"):
        add("M2", f"common_unit_scale_{channel}", m2.unit_scales[channel], "raw quantity per internal unit", "raw-to-common-unit conversion", "development-estimated", "positive episode-mean median", "development fit", "M2", "fitted artifact")
        add("M2", f"unit_cost_rmb_{channel}", m2.unit_costs_rmb[channel], "RMB/internal unit", "common-unit-to-RMB conversion", "baseline-assumption", "current identity mapping", "before formal evaluation", "M2-M4", f"m2.unit_costs_rmb.{channel}")
    for section in ("flight", "passenger", "resource", "resource_stress"):
        for key, value in cfg.scientific["m2"].get(section, {}).items():
            add("M2", f"{section}.{key}", value, "declared", "quantity mapping", "scenario-declared", "frozen primary specification", "before formal evaluation", "M2", f"m2.{section}.{key}")
    for row in m3.parameter_table.to_dict("records"):
        action_id = str(row["action_id"])
        for key, value in row.items():
            if key in {"action_id", "parameter_source", "parameter_version"}:
                continue
            unit = "probability/rate" if key.startswith("mu_") or key == "failure_probability" else ("RMB" if key.startswith("kbar_rmb_") else "distribution parameter")
            add("M3", f"{action_id}.{key}", value, unit, "generic action-response distribution", str(row["parameter_source"]), str(row["parameter_version"]), "before formal evaluation", "M3-M4", f"m3.response_parameters.{action_id}.{key}")
    del m4
    m4_config = cfg.scientific["m4"]
    for key, value in m4_config["risk"].items():
        add(
            "M4",
            f"risk.{key}",
            value,
            "weight/probability",
            "weighted Mean-CVaR risk contract",
            "predeclared",
            "M4_CONTEXTUAL_RESIDUAL_RISK_V2",
            "before formal evaluation",
            "M4",
            f"m4.risk.{key}",
        )
    for key, value in m4_config["draw_pairing"].items():
        add(
            "M4",
            f"draw_pairing.{key}",
            value,
            "contract",
            "shared draw-index identity",
            "predeclared",
            "STABLE_SHARED_DRAW_INDEX",
            "before formal evaluation",
            "M4",
            f"m4.draw_pairing.{key}",
        )
    add("COMPUTE", "formal_samples", cfg.mode()["formal_samples"], "draws", "Monte Carlo budget", "engineering", "mode configuration", "run start", "M1-M4", f"modes.{cfg.mode_name}.formal_samples")
    return pd.DataFrame(rows)
