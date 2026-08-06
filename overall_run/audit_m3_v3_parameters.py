from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "overall_run"
sys.path.insert(0, str(MODULE))

from src.config import load_config  # noqa: E402
from src.legacy.m3_v3_audit import _parameter_rows, load_actions  # noqa: E402


def _v2_parameters() -> tuple[pd.DataFrame, dict[str, dict]]:
    raw = yaml.safe_load((MODULE / "config" / "m3_response_v2_20260726.yaml").read_text(encoding="utf-8"))
    rows = []
    metadata = {str(item["id"]): item for item in raw["m3"]["actions"]}
    defaults = raw["m3"]["response_defaults"]
    for action_id, item in raw["m3"]["response_parameters"].items():
        rows.append({
            "action_id": action_id,
            **{f"mu_{channel}": float(item["mu"][index]) for index, channel in enumerate("FPR")},
            **{f"kbar_rmb_{channel}": float(item["kbar_rmb"][index]) for index, channel in enumerate("FPR")},
            "kappa_eta": float(item.get("recovery_concentration", defaults["recovery_concentration"])),
            "CV_K": float(item.get("cost_cv", defaults["cost_cv"])),
            "p_fail": float(item.get("failure_probability", defaults["failure_probability"])),
        })
    return pd.DataFrame(rows), metadata


def _development_validation_loss() -> tuple[pd.DataFrame, pd.DataFrame]:
    raise RuntimeError(
        "M2_CONTRACT_MISMATCH: migrate this M3 audit to the M1 joint-sample contract"
    )


def _dominance(v3: pd.DataFrame, actions: dict) -> pd.DataFrame:
    rows = []
    numeric = [f"mu_{c}" for c in "FPR"] + [f"kbar_rmb_{c}" for c in "FPR"] + ["p_fail"]
    indexed = v3.set_index("action_id")
    for left in indexed.index:
        for right in indexed.index:
            if left == right:
                continue
            a, b = indexed.loc[left], indexed.loc[right]
            recovery_better = all(a[f"mu_{c}"] >= b[f"mu_{c}"] for c in "FPR")
            burden_better = all(a[f"kbar_rmb_{c}"] <= b[f"kbar_rmb_{c}"] for c in "FPR") and a["p_fail"] <= b["p_fail"]
            same_gates = (
                actions[left].resource_requirement == actions[right].resource_requirement
                and actions[left].authority_requirement == actions[right].authority_requirement
                and actions[left].compatibility_requirement == actions[right].compatibility_requirement
                and actions[left].capacity_required == actions[right].capacity_required
                and actions[left].lead_time_requirement <= actions[right].lead_time_requirement
            )
            scale = np.maximum(np.abs(indexed[numeric]).median().to_numpy(float), 1e-6)
            distance = float(np.linalg.norm((a[numeric].to_numpy(float) - b[numeric].to_numpy(float)) / scale))
            rows.append({
                "action_left": left, "action_right": right,
                "recovery_weakly_better": recovery_better,
                "burden_and_failure_weakly_better": burden_better,
                "gate_weakly_no_stricter": same_gates,
                "unconditional_dominance": bool(recovery_better and burden_better and same_gates),
                "normalized_parameter_distance": distance,
                "near_duplicate": bool(distance < 0.35),
            })
    return pd.DataFrame(rows)


def main() -> None:
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    cfg = load_config(MODULE, "fast")
    actions = load_actions(cfg.scientific)
    v3 = _parameter_rows(actions, cfg.scientific)
    v2, _ = _v2_parameters()
    delta = v3.merge(v2, on="action_id", how="outer", suffixes=("_v3", "_v2"), indicator=True)
    for base in [f"mu_{c}" for c in "FPR"] + [f"kbar_rmb_{c}" for c in "FPR"] + ["kappa_eta", "CV_K", "p_fail"]:
        if f"{base}_v3" in delta and f"{base}_v2" in delta:
            delta[f"delta_{base}"] = delta[f"{base}_v3"] - delta[f"{base}_v2"]
    delta.to_csv(reports / "M3_V2_V3_PARAMETER_DELTA.csv", index=False)
    dominance = _dominance(v3, actions)
    dominance.to_csv(reports / "M3_V3_DOMINANCE_AUDIT.csv", index=False)
    devval, composition = _development_validation_loss()
    stage = devval.groupby(["split", "snapshot_stage"], observed=True)["pre_action_loss"].agg(
        count="size", mean="mean", p05=lambda x: x.quantile(.05), p50="median", p95=lambda x: x.quantile(.95)
    ).reset_index()
    v2_index = v2.set_index("action_id")
    ratio_rows = []
    case_means = devval[["split", "snapshot_stage", "loss_F", "loss_P", "loss_R", "pre_action_loss"]].dropna()
    for action_id, p in v2_index.iterrows():
        recovery = sum(case_means[f"loss_{c}"] * p[f"mu_{c}"] for c in "FPR")
        burden = sum(float(p[f"kbar_rmb_{c}"]) for c in "FPR")
        recovery_ratio = recovery / case_means["pre_action_loss"].clip(lower=1e-9)
        burden_ratio = burden / recovery.clip(lower=1e-9)
        pnb = (recovery > burden).astype(float) * (1.0 - float(p["p_fail"]))
        ratio_rows.append({
            "action_id": action_id, "recovery_ratio_p50": recovery_ratio.median(),
            "recovery_ratio_p90": recovery_ratio.quantile(.9), "burden_ratio_p50": burden_ratio.median(),
            "positive_net_benefit_probability_mean": pnb.mean(),
            "passes_current_r0_b0_q0_share": ((recovery_ratio >= .2) & (burden_ratio <= 1.0) & (pnb >= .6)).mean(),
        })
    ratios = pd.DataFrame(ratio_rows)
    table = v3[["action_id", *[f"mu_{c}" for c in "FPR"], *[f"kbar_rmb_{c}" for c in "FPR"], "kappa_eta", "CV_K", "p_fail"]].copy()
    for field in ["capacity_required", "window_type", "resource_requirement", "authority_requirement", "lead_time_requirement", "priority"]:
        table[field] = table["action_id"].map({key: getattr(value, field) for key, value in actions.items()})
    report = [
        "# M3 V3 Parameter Proposal", "", "Generated: 2026-07-31", "",
        "## Selection contract", "",
        "- Parameter-selection evidence is restricted to PRE `train` and `validation` rows. The script aborts if a test row enters the selection frame.",
        "- The frozen M2 structure is applied to observed development/validation execution loss to estimate F/P/R pre-action composition. Existing final-test M4 outputs are not read by this audit.",
        "- Intensities increase recovery only together with higher burden, failure probability, lead time, authority, compatibility, capacity, or typed-resource restrictions.",
        "- Aircraft, crew, cancellation, and network-reset families have explicit typed gates and are intentionally not universally feasible.",
        "- S01/S02 retain the former burden-only semantics as unit-test/audit fixtures and are absent from this formal table.", "",
        "## Development/validation F/P/R composition", "", composition.to_markdown(index=False), "",
        "## Stage pre-action loss distribution", "", stage.to_markdown(index=False), "",
        "## Current V2 r0/b0/q0 proxy on development/validation", "", ratios.to_markdown(index=False), "",
        "The proxy uses the configured V2 response means and the frozen development/validation M2 channel costs. It is descriptive calibration evidence, not a final-test result.", "",
        "## Proposed V3 parameters and requirements", "", table.to_markdown(index=False), "",
        "## Dominance and duplication status", "",
        f"- Unconditional dominance pairs: {int(dominance['unconditional_dominance'].sum())}.",
        f"- Near-duplicate pairs: {int(dominance['near_duplicate'].sum())}.",
        "- Full pairwise details are in `M3_V3_DOMINANCE_AUDIT.csv`; V2/V3 deltas are in `M3_V2_V3_PARAMETER_DELTA.csv`.", "",
        "## Scientific status", "", "`STOP_AND_REVIEW`: formal development/validation rerun of PRE and M4 typed gates is required before these parameters can be declared scientifically accepted.",
    ]
    (reports / "M3_V3_PARAMETER_PROPOSAL.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"actions": len(actions), "dominance_pairs": int(dominance['unconditional_dominance'].sum()), "near_duplicates": int(dominance['near_duplicate'].sum())}))


if __name__ == "__main__":
    main()
