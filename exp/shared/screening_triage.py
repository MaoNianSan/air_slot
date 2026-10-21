"""Stage-budget screening, with occurrence-preserving cluster uncertainty."""

from math import ceil
import numpy as np
import pandas as pd
from exp.shared.analytical import ACTIVE_STAGES, COMPONENTS, scores, primary_mask
from exp.shared.resampling import bootstrap_plan, episode_ids, expand_draw


def prepare_canonical_events(frame):
    data = frame.copy() if "NO_F_EXECUTION" in frame else scores(frame)
    data = data[data.operational_stage.isin(ACTIVE_STAGES)].copy()
    data["technical_node_id"] = data.get("technical_node_id", data.decision_node_id)
    instance = "bootstrap_instance_id" if "bootstrap_instance_id" in data else "original_episode_id"
    data = data.sort_values([instance, "operational_stage", "decision_time", "technical_node_id"])
    canonical = data.groupby([instance, "operational_stage"], sort=False).head(1).copy()
    valid = primary_mask(canonical)
    canonical["canonical_event_status"] = np.where(valid, "SUPPORTED", "EXCLUDE_WITH_TYPED_REASON")
    canonical["canonical_event_exclusion_reason"] = np.where(
        valid, "", "PRIMARY_SUPPORT_OR_AGGREGATE_UNSUPPORTED"
    )
    return canonical.reset_index(drop=True), data.reset_index(drop=True)


def _top(values, ids, q):
    n = len(ids)
    if not n or len(set(ids)) != n or not np.isfinite(values).all():
        raise ValueError("EXP4_TOPK_ID_OR_SCORE_INVALID")
    k = ceil(q * n)
    order = np.lexsort((ids, -np.asarray(values)))
    selected = np.zeros(n, dtype=bool)
    selected[order[:k]] = True
    ties = int(np.sum(values == values[order[k-1]]))
    return selected, ties


def _views(group):
    f, p, r = (group[f"S_{c}"].to_numpy(float) for c in ("F", "P", "R"))
    return np.column_stack([
        f, p, r, group.EQUAL_COMPONENT, group.NO_F_EXECUTION,
        .50*f + .25*p + .25*r, .25*f + .50*p + .25*r, .25*f + .25*p + .50*r,
    ])


def _burden(values, selected):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all():
        return None
    total = values.sum()
    return None if total <= 0 else float(values[selected].sum()/total)


def _native_column(group, component):
    for column in (f"{component}_native_cs", f"{component}_native"):
        if column in group:
            return group[column]
    raise ValueError(f"EXP4_NATIVE_COMPONENT_COLUMN_MISSING:{component}")


def evaluate_screening(canonical, capacities=(.05, .10, .20, .30), evidence=False):
    results, proof = [], []
    for stage in ACTIVE_STAGES:
        group = canonical[
            canonical.operational_stage.eq(stage) & canonical.canonical_event_status.eq("SUPPORTED")
        ].reset_index(drop=True)
        n = len(group)
        if not n:
            results.extend({"stage": stage, "q": q, "status": "ABSTAIN_EMPTY_COHORT", "n": 0}
                           for q in capacities)
            continue
        ids = group.technical_node_id.astype(str).to_numpy()
        views = _views(group)
        votes = sum(_top(views[:, i], ids, .10)[0].astype(int) for i in range(8))
        z = group[[f"Z_{c}_cs" for c in COMPONENTS]].to_numpy(float)
        complete = np.isfinite(z).all(axis=1)
        # dominates[j, i]: j weakly exceeds i in every component, strictly in one.
        dominates = ((z[:, None, :] >= z[None, :, :]).all(axis=2)
                     & (z[:, None, :] > z[None, :, :]).any(axis=2)
                     & complete[:, None] & complete[None, :])
        for q in capacities:
            td, dt = _top(group.D.to_numpy(float), ids, q)
            tc, ct = _top(group.S_C.to_numpy(float), ids, q)
            k = int(td.sum())
            row = {"stage": stage, "q": q, "status": "PASS", "n": n, "k": k,
                   "overlap": int((td & tc).sum()), "slots_reassigned": int((td & ~tc).sum()),
                   "reassigned_rate": float((td & ~tc).sum()/k),
                   "delay_boundary_tie_count": dt, "consequence_boundary_tie_count": ct,
                   "delay_boundary_tie_fraction": dt/n, "consequence_boundary_tie_fraction": ct/n}
            for name, values in [
                *[(d, group[f"S_{d}"]) for d in ("F", "P", "R")],
                *[(c, _native_column(group, c)) for c in COMPONENTS],
            ]:
                a, b = _burden(values, td), _burden(values, tc)
                row[f"Capture_D_{name}"], row[f"Capture_C_{name}"] = a, b
                row[f"Delta_Capture_{name}_pp"] = None if a is None or b is None else 100*(b-a)
                row[f"Capture_{name}_status"] = "PASS" if a is not None and b is not None else "ABSTAIN_UNSUPPORTED_OR_ZERO_DENOMINATOR"
            for m in (3, 4, 5):
                robust = votes >= m
                denom = int(robust.sum())
                row[f"robust_count_m{m}"] = denom
                a = None if not denom else float((robust & ~td).sum()/denom)
                b = None if not denom else float((robust & ~tc).sum()/denom)
                row[f"MissRate_D_m{m}"], row[f"MissRate_C_m{m}"] = a, b
                row[f"Delta_Miss_m{m}"] = None if a is None or b is None else b-a
                row[f"robust_status_m{m}"] = "PASS" if denom else "ABSTAIN_EMPTY_ROBUST_SET"
            for method, selected in (("D", td), ("C", tc)):
                reversal = selected & dominates[~selected].any(axis=0)
                denom = int((selected & complete).sum())
                row[f"Pareto_reversal_count_{method}"] = int(reversal.sum())
                row[f"Pareto_rate_{method}"] = None if not denom else float(reversal.sum()/denom)
                row[f"Pareto_complete_selected_{method}"] = denom
                if evidence:
                    for i in np.flatnonzero(reversal):
                        j = np.flatnonzero(dominates[:, i] & ~selected)[0]
                        proof.append({"stage": stage, "q": q, "method": method,
                                      "selected_id": ids[i], "unselected_dominator_id": ids[j]})
            results.append(row)
    return pd.DataFrame(results), pd.DataFrame(proof)


def screen(canonical, q=.10):
    return evaluate_screening(canonical, (q,))[0]


def capture(canonical, q=.10):
    table = screen(canonical, q)
    return table[[c for c in table if c in ("stage", "q", "status", "n", "k") or "Capture" in c]]


def robust_sets(canonical, threshold=4):
    rows = []
    for stage, group in canonical[canonical.canonical_event_status.eq("SUPPORTED")].groupby("operational_stage"):
        ids = group.technical_node_id.astype(str).to_numpy()
        views = _views(group)
        counts = sum(_top(views[:, i], ids, .10)[0].astype(int) for i in range(8))
        out = group[["original_episode_id", "decision_node_id", "technical_node_id"]].copy()
        out["stage"], out["m"], out["view_count"] = stage, threshold, counts
        out["robust_high_consequence"] = counts >= threshold
        rows.append(out)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def robust_missed_nodes(canonical, threshold=4, q=.10):
    rows = []
    for stage, group in canonical[canonical.canonical_event_status.eq("SUPPORTED")].groupby("operational_stage"):
        group = group.reset_index(drop=True)
        ids = group.technical_node_id.astype(str).to_numpy()
        views = _views(group)
        votes = sum(_top(views[:, i], ids, .10)[0].astype(int) for i in range(8))
        delay_selected, _ = _top(group.D.to_numpy(float), ids, q)
        consequence_selected, _ = _top(group.S_C.to_numpy(float), ids, q)
        robust = votes >= threshold
        if robust.any():
            selected = group.loc[robust, ["original_episode_id", "decision_node_id", "technical_node_id"]].copy()
            selected["stage"] = stage
            selected["q"] = q
            selected["m"] = threshold
            selected["view_count"] = votes[robust]
            selected["captured_by_delay"] = delay_selected[robust]
            selected["captured_by_consequence"] = consequence_selected[robust]
            selected["missed_by_delay"] = ~delay_selected[robust]
            selected["missed_by_consequence"] = ~consequence_selected[robust]
            rows.append(selected)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def pareto_reversals(canonical, q=.10):
    table = screen(canonical, q)
    return table[[c for c in table if c in ("stage", "q", "status", "n", "k") or "Pareto" in c]]


def bootstrap_screening(frame, *, replicates=2000, seed=20260906, plan=None):
    # Resample the unfiltered rolling node cohort, not supported canonical events.
    data = frame.copy() if "NO_F_EXECUTION" in frame else scores(frame)
    if plan is None:
        plan = bootstrap_plan(episode_ids(data), replicates, seed)
    output = []
    for replicate, draw in enumerate(plan):
        events, _ = prepare_canonical_events(expand_draw(data, draw))
        stats, _ = evaluate_screening(events)
        stats["replicate"] = replicate
        output.append(stats)
        if (replicate + 1) % 100 == 0:
            print(f"EXP4 bootstrap {replicate+1}/{len(plan)}", flush=True)
    return pd.concat(output, ignore_index=True)
