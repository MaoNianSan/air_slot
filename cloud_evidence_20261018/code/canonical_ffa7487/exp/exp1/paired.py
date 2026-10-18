"""Target-specific paired errors and cluster uncertainty (no pooled headline)."""

import numpy as np
import pandas as pd
import torch
from model.M1.lifecycle import M1Lifecycle
from model.M1.development_diagnostics import evaluate_lifecycle, _finite_discrete_crps
from exp.shared.resampling import bootstrap_plan, episode_ids, interval

TARGETS = {"R_IB": "T_IB_REMAINING_HAZARD", "D_OB": "D_OB", "D_TX": "D_TX"}


def hazard_crps_records(lifecycle, examples):
    contract = lifecycle.pipeline.contracts["T_IB_REMAINING_HAZARD"]
    values = [float(contract.representative(i)[0]) for i in range(contract.finite_class_count)]
    result = {}
    for start in range(0, len(examples), 64):
        batch = list(examples[start:start+64])
        x, lengths, _, static = M1Lifecycle._batch(batch, lifecycle.pipeline.contracts)
        with torch.no_grad():
            pmfs = lifecycle.pipeline.predict_distributions(
                x, lengths, static_features=static
            )["T_IB_A00"].detach().cpu().numpy()
        for row, pmf in zip(batch, pmfs):
            target = row.targets.get("T_IB_REMAINING_HAZARD")
            finite = pmf[:-1].astype(float)
            mass = float(finite.sum())
            crps = None
            if (row.active.get("T_IB_REMAINING_HAZARD") and target is not None
                    and target < contract.max_finite_minutes and mass > 0):
                crps = _finite_discrete_crps(values, (finite/mass).tolist(), float(target))
            result[(row.episode_id, row.decision_node_id)] = (crps, mass)
    return result


def paired_records(history_nodes, current_nodes):
    def index(nodes):
        out = {(n["episode_id"], n["decision_node_id"]): n for n in nodes}
        if len(out) != len(nodes):
            raise ValueError("EXP1_DUPLICATE_PAIRED_NODE")
        return out
    h, c = index(history_nodes), index(current_nodes)
    if set(h) != set(c):
        raise ValueError("EXP1_HISTORY_CURRENT_NODE_MISMATCH")
    records = []
    for key in sorted(h):
        for target, internal in TARGETS.items():
            a, b = h[key], c[key]
            if a["active"].get(internal) != b["active"].get(internal):
                raise ValueError("EXP1_TARGET_SUPPORT_MISMATCH")
            y, yc = a["targets"].get(internal), b["targets"].get(internal)
            if y != yc:
                raise ValueError("EXP1_PAIRED_OBSERVATION_MISMATCH")
            field = ("T_IB_A00_remaining_minutes_finite_support" if target == "R_IB"
                     else f"{target}_point_minutes")
            ph, pc = a["predictions"].get(field), b["predictions"].get(field)
            ok = a["active"].get(internal) and all(
                v is not None and np.isfinite(v) for v in (y, ph, pc))
            records.append({
                "episode_id": key[0], "decision_node_id": key[1], "target": target,
                "observation_minutes": y, "History_point": ph, "Current_point": pc,
                "History_AE": abs(ph-y) if ok else None,
                "Current_AE": abs(pc-y) if ok else None,
                "paired_status": "MATCHED_TARGET_SUPPORT" if ok else "ABSTAIN_INACTIVE_OR_UNSUPPORTED",
            })
    return pd.DataFrame(records)


def target_estimate(frame):
    h, c = frame.History_AE.to_numpy(float), frame.Current_AE.to_numpy(float)
    if not len(h):
        return {key: None for key in (
            "History_MAE", "Current_MAE", "Delta_MAE", "History_P90AE", "Current_P90AE")}
    return {"History_MAE": float(h.mean()), "Current_MAE": float(c.mean()),
            "Delta_MAE": float((h-c).mean()),
            "History_P90AE": float(np.quantile(h,.9)), "Current_P90AE": float(np.quantile(c,.9))}


def summarize_targets(records, plan):
    summaries, bootstrap = [], []
    for target in TARGETS:
        frame = records[records.target.eq(target) & records.paired_status.eq("MATCHED_TARGET_SUPPORT")]
        groups = {e: g for e, g in frame.groupby("episode_id")}
        estimate = target_estimate(frame)
        draws = []
        for replicate, draw in enumerate(plan):
            parts = [groups[e] for e in draw if e in groups]
            sample = pd.concat(parts, ignore_index=True) if parts else frame.iloc[:0]
            value = target_estimate(sample)
            if target == "R_IB" and "History_R_IB_CRPS" in sample:
                paired = sample.dropna(subset=["History_R_IB_CRPS", "Current_R_IB_CRPS"])
                for mode in ("History", "Current"):
                    value[f"{mode}_R_IB_finite_support_CRPS"] = paired[f"{mode}_R_IB_CRPS"].mean()
                value["Delta_R_IB_finite_support_CRPS"] = (paired.History_R_IB_CRPS-paired.Current_R_IB_CRPS).mean()
            draws.append(value)
            bootstrap.append({"target": target, "replicate": replicate, **value})
        if target == "R_IB" and "History_R_IB_CRPS" in frame:
            paired = frame.dropna(subset=["History_R_IB_CRPS", "Current_R_IB_CRPS"])
            estimate.update({
                "History_R_IB_finite_support_CRPS": paired.History_R_IB_CRPS.mean(),
                "Current_R_IB_finite_support_CRPS": paired.Current_R_IB_CRPS.mean(),
                "Delta_R_IB_finite_support_CRPS": (paired.History_R_IB_CRPS-paired.Current_R_IB_CRPS).mean(),
                "CRPS_scope": "R_IB_T_IB_FINITE_SUPPORT_CONDITIONAL_ONLY",
            })
        for metric in list(estimate):
            if metric == "CRPS_scope":
                continue
            low, high = interval([d[metric] for d in draws])
            estimate[f"{metric}_ci_low"], estimate[f"{metric}_ci_high"] = low, high
        summaries.append({
            "target": target,
            "raw_record_count": int((records.target == target).sum()),
            "matched_eligible_count": int(len(frame)),
            "N_nodes": int(len(frame)),
            "N_episodes": int(frame.episode_id.nunique()),
            **estimate,
        })
    return pd.DataFrame(summaries), pd.DataFrame(bootstrap)
