"""Extract the six-year audited cloud outputs into paper-facing backfill tables.

Source (read-only):
  <SNAP>/artifacts/experiment/jatm_s34/full_20261013/{e1,e2e3,e4}/{year}/

Nothing here recomputes scientific quantities; every number is copied from the
audited artifacts, or is an explicitly labelled arithmetic aggregate of stored
per-case rows (mean/median/share over the same stored cohort).
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

SNAP = Path(
    "D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013"
)
OUT = Path("D:/Local_Projects/airslot/backfill_20261014/extracted")
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
STAGES = ("PRE_IB", "POST_IB_PRE_OB")
STAGE_LABEL = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}
VIEWS = ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM", "CONSEQUENCE")
Q_GRID = (0.05, 0.10, 0.20, 0.30)


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _r(value, nd=6):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), nd)


def e1_extract(year: int) -> dict:
    payload = load(SNAP / "e1" / str(year) / "E1_SUMMARY.json")
    rows = payload["summary_rows"]
    by = {(r["stage"], round(float(r["q"]), 4), r["view"]): r for r in rows}
    nominal = {}
    for stage in STAGES:
        for view in VIEWS:
            r = by[(stage, 0.10, view)]
            nominal.setdefault(STAGE_LABEL[stage], {})[view] = {
                "n": r["n"],
                "k": r["k"],
                "candidate_total": r["candidate_total"],
                "abstain": r["abstain"],
                "overlap": r["overlap"],
                "replacement": r["replacement"],
                "retained_consequence": _r(r["retained_consequence"]),
                "absolute_consequence_gap": _r(r["absolute_consequence_gap"]),
                "attention_loss": _r(r["attention_loss"]),
                "attention_loss_ci": (
                    None
                    if not r.get("bootstrap_ci", {}).get("metrics", {}).get("attention_loss", {}).get("ci_low")
                    is not None
                    else {
                        "low": _r(r["bootstrap_ci"]["metrics"]["attention_loss"]["ci_low"]),
                        "high": _r(r["bootstrap_ci"]["metrics"]["attention_loss"]["ci_high"]),
                    }
                ),
                "retained_consequence_ci": (
                    None
                    if r.get("bootstrap_ci", {}).get("metrics", {}).get("retained_consequence", {}).get("ci_low")
                    is None
                    else {
                        "low": _r(r["bootstrap_ci"]["metrics"]["retained_consequence"]["ci_low"]),
                        "high": _r(r["bootstrap_ci"]["metrics"]["retained_consequence"]["ci_high"]),
                    }
                ),
                "replacement_ci": (
                    None
                    if r.get("bootstrap_ci", {}).get("metrics", {}).get("replacement", {}).get("ci_low")
                    is None
                    else {
                        "low": _r(r["bootstrap_ci"]["metrics"]["replacement"]["ci_low"]),
                        "high": _r(r["bootstrap_ci"]["metrics"]["replacement"]["ci_high"]),
                    }
                ),
                "paired_increment_vs_delay": r.get("paired_increment_vs_delay"),
            }
    grid = [
        {
            "stage": STAGE_LABEL[r["stage"]],
            "q": float(r["q"]),
            "view": r["view"],
            "n": r["n"],
            "k": r["k"],
            "overlap": r["overlap"],
            "replacement": r["replacement"],
            "retained_consequence": _r(r["retained_consequence"]),
            "attention_loss": _r(r["attention_loss"]),
            "ci_low": _r(
                r.get("bootstrap_ci", {}).get("metrics", {}).get("attention_loss", {}).get("ci_low")
            ),
            "ci_high": _r(
                r.get("bootstrap_ci", {}).get("metrics", {}).get("attention_loss", {}).get("ci_high")
            ),
        }
        for r in rows
    ]
    return {
        "year": year,
        "status": payload["status"],
        "artifact_hash": payload["artifact_hash"],
        "node_count": payload["node_count"],
        "common_candidate_counts": {
            STAGE_LABEL[k]: v for k, v in payload["common_candidate_counts"].items()
        },
        "candidate_exclusions": payload.get("candidate_exclusions"),
        "final_test_access_count": payload["final_test_access_count"],
        "bootstrap": payload["bootstrap"],
        "nominal_q010": nominal,
        "q_grid": grid,
    }


def e2_extract(year: int) -> dict:
    payload = load(SNAP / "e2e3" / str(year) / "E2_E3_SUMMARY.json")
    e2 = payload["e2"]
    info = {row["information_component"]: row for row in e2["information_value"]}
    assert info["CROSS_STATE_DEPENDENCE"]["comparator"] == "HISTORY_MARGINAL_EXACT"
    recovery = {row["representation"]: row for row in e2["recovery_rows"]}
    diagnostics = {row["information_component"]: row for row in e2["diagnostics"]}

    def clean(row):
        return {
            "comparator": row["comparator"],
            "L_att": _r(row["L_att"]),
            "L_att_ci_low": _r(row["L_att_ci_low"]),
            "L_att_ci_high": _r(row["L_att_ci_high"]),
            "delta_J": _r(row["delta_J"]),
            "reference_V": _r(row["reference_V"]),
            "L_rec": _r(row["L_rec"]),
            "L_rec_ci_low": _r(row["L_rec_ci_low"]),
            "L_rec_ci_high": _r(row["L_rec_ci_high"]),
            "stage1_reassigned_share": _r(row["stage1_reassigned_share"]),
            "A0": _r(row["A0"]),
            "A5": _r(row["A5"]),
            "missed_activation": row["missed_activation"],
            "false_activation": row["false_activation"],
            "under_recovery": row["under_recovery"],
            "over_recovery": row["over_recovery"],
        }

    stage1 = [
        {
            "stage": row["stage"],
            "q": float(row["q"]),
            "reference": row["reference"],
            "comparator": row["comparator"],
            "N": row["N"],
            "K": row["K"],
            "overlap": row["overlap"],
            "displaced": row["K"] - row["overlap"],
            "L_att": _r(row["L_att"]),
        }
        for row in e2["stage1_rows"]
    ]
    return {
        "year": year,
        "status": payload["status"],
        "artifact_hash": payload["artifact_hash"],
        "chunk_size": payload["chunk_size"],
        "chunk_count": payload["chunk_count"],
        "node_count": payload["node_count"],
        "exact_marginal": payload["exact_marginal"],
        "e2": {
            "estimand": e2["estimand"],
            "reference_cohort_size": e2["reference_cohort_size"],
            "information_candidate_count": e2["information_candidate_count"],
            "information_value": {k: clean(v) for k, v in info.items()},
            "diagnostics": {
                k: {
                    "comparator": v["comparator"],
                    "exact_action_agreement": _r(v["exact_action_agreement"]),
                    "within_5min_agreement": _r(v["within_5min_agreement"]),
                    "missed_activation": v["missed_activation"],
                    "false_activation": v["false_activation"],
                    "under_recovery": v["under_recovery"],
                    "over_recovery": v["over_recovery"],
                    "mean_absolute_action_difference": _r(v["mean_absolute_action_difference"]),
                    "typed_fallback_count": v["typed_fallback_count"],
                }
                for k, v in diagnostics.items()
            },
            "recovery_rows": {
                k: {
                    "L_rec": _r(v["loss"]),
                    "reference_recoverable_value": _r(v["reference_recoverable_value"]),
                    "delta_recovery_objective": _r(v["delta_recovery_objective"]),
                    "typed_fallbacks": v["typed_fallbacks"],
                }
                for k, v in recovery.items()
            },
            "stage1_rows_HM_vs_HJ": stage1,
        },
        "bootstrap": payload["e2"]["bootstrap"],
    }


def e3_extract(year: int) -> dict:
    rows = load(SNAP / "e2e3" / str(year) / "E3_OBJECTIVE_ROWS.json")
    mech = load(SNAP / "e2e3" / str(year) / "E3_MECHANISM_DIAGNOSTICS.json")
    profiles = sorted({r["profile"] for r in rows})
    reps = sorted({r["representation"] for r in rows})
    by_key: dict[tuple, dict] = {}
    for row in rows:
        by_key[(row["profile"], row["representation"], row["node_id"])] = row
    node_ids = sorted({r["node_id"] for r in rows})
    stages = {}
    for row in rows:
        stages[row["node_id"]] = row["stage"]

    profile_summary = {}
    for profile in profiles:
        joint = {nid: by_key[(profile, "HISTORY_JOINT", nid)] for nid in node_ids}
        marg = {
            nid: by_key[(profile, "HISTORY_MARGINAL_EXACT", nid)]
            for nid in node_ids
            if (profile, "HISTORY_MARGINAL_EXACT", nid) in by_key
        }
        agree = sum(1 for nid in marg if joint[nid]["u_star"] == marg[nid]["u_star"])
        dep_sensitive = sum(1 for nid in marg if joint[nid]["u_star"] != marg[nid]["u_star"])
        du = [abs(joint[nid]["u_star"] - marg[nid]["u_star"]) for nid in marg]
        v_joint = [joint[nid]["recoverable_value"] for nid in node_ids]
        act_joint = sum(1 for nid in node_ids if joint[nid]["u_star"] > 0)
        zero_v = sum(1 for v in v_joint if v == 0.0)
        mar_joint = [joint[nid]["decision_margin"] for nid in node_ids if joint[nid]["decision_margin"] is not None]
        per_stage = {}
        for stage in sorted({stages[nid] for nid in node_ids}):
            ids = [nid for nid in node_ids if stages[nid] == stage]
            per_stage[stage] = {
                "N": len(ids),
                "activation_share_joint": _r(
                    sum(1 for nid in ids if joint[nid]["u_star"] > 0) / len(ids)
                ),
                "zero_recoverable_value_share_joint": _r(
                    sum(1 for nid in ids if joint[nid]["recoverable_value"] == 0.0) / len(ids)
                ),
                "median_V_joint": _r(statistics.median(joint[nid]["recoverable_value"] for nid in ids)),
                "agreement_joint_vs_marginal": (
                    None
                    if not any(nid in marg for nid in ids)
                    else _r(
                        sum(1 for nid in ids if nid in marg and joint[nid]["u_star"] == marg[nid]["u_star"])
                        / sum(1 for nid in ids if nid in marg)
                    )
                ),
            }
        profile_summary[profile] = {
            "aggregation_view": joint[node_ids[0]]["aggregation_view"],
            "N": len(node_ids),
            "N_marginal_rows": len(marg),
            "exact_target_agreement_share": _r(agree / len(marg)) if marg else None,
            "dependence_sensitive_share": _r(dep_sensitive / len(marg)) if marg else None,
            "mean_abs_target_change_min": _r(statistics.fmean(du)) if du else None,
            "median_abs_target_change_min": _r(statistics.median(du)) if du else None,
            "max_abs_target_change_min": _r(max(du)) if du else None,
            "activation_share_joint": _r(act_joint / len(node_ids)),
            "zero_recoverable_value_share_joint": _r(zero_v / len(node_ids)),
            "positive_recoverable_value_share_joint": _r(1 - zero_v / len(node_ids)),
            "median_V_joint": _r(statistics.median(v_joint)),
            "mean_V_joint": _r(statistics.fmean(v_joint)),
            "p90_V_joint": _r(sorted(v_joint)[int(0.9 * (len(v_joint) - 1))]),
            "median_decision_margin_joint": _r(statistics.median(mar_joint)) if mar_joint else None,
            "per_stage": per_stage,
        }
    u_star_hist = {}
    for profile in profiles:
        for rep in reps:
            vals = [by_key[(profile, rep, nid)]["u_star"] for nid in node_ids]
            u_star_hist[f"{profile}|{rep}"] = {
                "zero_share": _r(sum(1 for v in vals if v == 0.0) / len(vals)),
                "positive_share": _r(sum(1 for v in vals if v > 0.0) / len(vals)),
                "mean": _r(statistics.fmean(vals)),
                "median": _r(statistics.median(vals)),
                "max": _r(max(vals)),
            }
    mechanism_summary = {
        "N": len(mech),
        "threshold_ablation_CHANGED": sum(1 for r in mech if r["threshold_ablation_status"] == "CHANGED"),
        "threshold_ablation_UNCHANGED": sum(1 for r in mech if r["threshold_ablation_status"] == "UNCHANGED"),
        "headroom_positive_share": _r(sum(1 for r in mech if r["headroom_positive"]) / len(mech)),
        "headroom_u_max_values": sorted({r["headroom_u_max"] for r in mech}),
        "nominal_support_mass_min": _r(min(r["nominal_support_mass"] for r in mech)),
        "nominal_support_mass_median": _r(statistics.median(r["nominal_support_mass"] for r in mech)),
        "full_support_mass_min": _r(min(r["full_support_mass"] for r in mech)),
        "full_support_mass_median": _r(statistics.median(r["full_support_mass"] for r in mech)),
        "headroom_boundary_change_share": _r(
            sum(1 for r in mech if r["threshold_ablation_status"] == "CHANGED") / len(mech)
        ),
    }
    return {
        "year": year,
        "profiles": profiles,
        "representations": reps,
        "cohort_size": len(node_ids),
        "joint_marginal_pair_count": len(rows),
        "profile_summary": profile_summary,
        "u_star_distribution": u_star_hist,
        "mechanism_summary": mechanism_summary,
    }


def e4_extract(year: int) -> dict:
    payload = load(SNAP / "e4" / str(year) / "EVAL_SUMMARY.json")
    manifest = load(SNAP / "e4" / str(year) / "E4_DEVELOPMENT_MANIFEST.json")
    decision = payload["decision"]
    return {
        "year": year,
        "protocol_hash": payload["protocol_hash"],
        "decision_status": decision["status"],
        "failed_instances": decision["failed_instances"],
        "failed_instance_count": len(decision["failed_instances"]),
        "eval_levels": sorted(int(k) for k in payload["years"][str(year)]["eval"]),
        "eval_N4096_status": payload["years"][str(year)]["eval"].get("4096"),
        "n_grid_coverage": manifest["years"][0]["n_grid_coverage"],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {"e1": {}, "e2": {}, "e3": {}, "e4": {}}
    for year in YEARS:
        data["e1"][year] = e1_extract(year)
        data["e2"][year] = e2_extract(year)
        data["e3"][year] = e3_extract(year)
        data["e4"][year] = e4_extract(year)
        print(f"year {year}: "
              f"E1 PRE N={data['e1'][year]['common_candidate_counts']['PRE']} "
              f"TURN N={data['e1'][year]['common_candidate_counts']['TURN']} | "
              f"E2 paired cohort={data['e2'][year]['e2']['reference_cohort_size']} "
              f"info candidates={data['e2'][year]['e2']['information_candidate_count']} | "
              f"E3 cohort={data['e3'][year]['cohort_size']} | "
              f"E4 {data['e4'][year]['decision_status']} fail={data['e4'][year]['failed_instance_count']}")
    for name, table in data.items():
        path = OUT / f"{name}_six_year.json"
        path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
