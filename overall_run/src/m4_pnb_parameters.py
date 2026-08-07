from __future__ import annotations

LEGACY_M4_NOT_FORMAL = True

import json
from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_formula import nonnull_triggered_rows


def build_physical_gate_audit(frame: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    triggered = nonnull_triggered_rows(candidates)
    metadata = {
        "capacity": ("PRE rules + action cap * reference span", "flow-pressure units"),
        "window": ("PRE action_window_margin and action library window", "minutes"),
        "resource": ("PRE explicit resource values or declared resource profile", "availability ratio"),
        "authority": ("PRE authority profile/allowed rule", "boolean/profile"),
        "lead": ("PRE lead_time_margin and action library lead", "minutes"),
    }
    rows: list[dict[str, Any]] = []
    for gate, (source, unit) in metadata.items():
        status_column = f"gate_{gate}_status"
        status_counts = triggered[status_column].astype(str).value_counts().sort_index().to_dict()
        family_rates = (
            triggered.groupby("action_family", observed=True)[f"gate_{gate}"]
            .mean()
            .sort_index()
            .to_dict()
        )
        rows.append(
            {
                "gate": gate,
                "threshold_source": source,
                "threshold_unit": unit,
                "provenance": "operational-rule-derived / scenario-declared action library",
                "pass_rate": float(triggered[f"gate_{gate}"].mean()),
                "pass_count": int(triggered[f"gate_{gate}"].sum()),
                "fail_count": int((~triggered[f"gate_{gate}"].astype(bool)).sum()),
                "missing_input_count": int(
                    triggered[status_column].astype(str).eq("MISSING").sum()
                ),
                "status_distribution": json.dumps(status_counts, sort_keys=True),
                "action_family_pass_rate": json.dumps(family_rates, sort_keys=True),
                "distance_to_threshold_status": (
                    "UNAVAILABLE_FROM_FROZEN_FAST_ARTIFACT; PRE read prohibited"
                ),
                "missing_input_behavior": "reject non-null action",
                "optimization_status": "SEMANTIC_AND_DISTRIBUTION_AUDIT_ONLY",
            }
        )
    return pd.DataFrame(rows)


def build_parameter_role_audit(
    sensitivity: dict[str, Any],
    physical: pd.DataFrame,
) -> pd.DataFrame:
    oat = sensitivity["all_oat"]
    physical_rates = physical.set_index("gate")["pass_rate"].to_dict()
    specifications = [
        ("b0", 1.00, "M4", "maximum expected implementation / expected recovery ratio", True, False, "scenario-declared", "scientific.yaml:m4.decision_value", "before formal evaluation", 0.895),
        ("q0", 0.60, "M4", "minimum P(recovered RMB > implementation RMB)", True, False, "scenario-declared", "scientific.yaml:m4.decision_value", "before formal evaluation", 0.1794444444),
        ("lambda", 0.25, "M4", "Mean-CVaR risk-aversion weight", False, True, "scenario-declared", "scientific.yaml:m4.risk_aversion", "before formal evaluation", np.nan),
        ("alpha", 0.90, "M4", "CVaR tail probability level", False, True, "scenario-declared", "scientific.yaml:m4.cvar_alpha", "before formal evaluation", np.nan),
        ("near_equivalent_relative", 0.02, "M4", "relative score tolerance for alternative set", False, False, "engineering-only", "scientific.yaml:m4.near_equivalent_relative", "before formal evaluation", np.nan),
    ]
    rows: list[dict[str, Any]] = []
    for item in specifications:
        parameter = item[0]
        parameter_rows = oat[oat["parameter"].eq(parameter)]
        priority = float(
            max(
                parameter_rows["candidate_set_disagreement_vs_formal"].max(),
                parameter_rows["recommendation_disagreement_vs_formal"].max(),
            )
        )
        rows.append(
            {
                "parameter": parameter,
                "formal_value": str(item[1]),
                "formal_value_numeric": float(item[1]),
                "module": item[2],
                "mathematical_role": item[3],
                "source_type": item[6],
                "source_detail": item[7],
                "frozen_stage": item[8],
                "directly_affects_candidate_set": item[4],
                "directly_affects_final_ranking": item[5],
                "data_estimated_or_declared": "declared",
                "current_empirical_pass_rate": item[9],
                "current_sensitivity_priority": priority,
            }
        )
    for gate in ("capacity", "window", "lead"):
        rows.append(
            {
                "parameter": f"physical_{gate}",
                "formal_value": "per-row rule/action value",
                "formal_value_numeric": np.nan,
                "module": "M3/M4 physical screening",
                "mathematical_role": f"{gate} feasibility gate",
                "source_type": "operational-rule-derived",
                "source_detail": "PRE rule fields + frozen action library",
                "frozen_stage": "PRE/action-library publication",
                "directly_affects_candidate_set": True,
                "directly_affects_final_ranking": False,
                "data_estimated_or_declared": "rule-derived and declared",
                "current_empirical_pass_rate": physical_rates[gate],
                "current_sensitivity_priority": np.nan,
            }
        )
    return pd.DataFrame(rows)


