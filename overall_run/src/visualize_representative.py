from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .visualize_common import CHANNELS, STAGES, save_figure


def _select_representative_flight(
    pred: pd.DataFrame,
    m2: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[str | None, str]:
    if pred.empty or m2.empty or candidates.empty:
        return None, "insufficient inputs"
    stages_by_flight = pred.groupby("flight_id")["snapshot_stage"].agg(lambda x: set(x.astype(str)))
    complete = stages_by_flight[stages_by_flight.map(lambda x: set(STAGES).issubset(x))].index.astype(str)
    retained_flights = set(
        candidates.loc[
            candidates["action_id"].astype(str).ne("A00")
            & candidates["candidate_flag"].fillna(False).astype(bool),
            "flight_id",
        ].astype(str)
    )
    common = sorted(
        set(complete) & set(m2["flight_id"].astype(str)) & retained_flights
    )
    if not common:
        return None, "no complete t1/t2/t3 flight with a non-null retained action"
    risk = (
        pred[pred["flight_id"].astype(str).isin(common)]
        .groupby("flight_id")["p_exceed_15"]
        .mean()
        .sort_values(kind="mergesort")
    )
    if risk.empty:
        return None, "risk summary unavailable"
    median_value = float(risk.median())
    selected = sorted(risk.index.astype(str), key=lambda flight: (abs(float(risk.loc[flight]) - median_value), flight))[0]
    return selected, (
        "median flight-level mean p_exceed_15 among complete t1/t2/t3 flights "
        "with at least one non-null retained action; deterministic flight_id tie-break; "
        "selection does not use action score or method advantage"
    )


def _figure_representative(
    pred: pd.DataFrame,
    m2: pd.DataFrame,
    candidates: pd.DataFrame,
    rankings: pd.DataFrame,
    metrics_dir: Path,
    out: Path,
) -> None:
    flight_id, rule = _select_representative_flight(pred, m2, candidates)
    if flight_id is None:
        return
    selection = pd.DataFrame([{"flight_id": flight_id, "selection_rule": rule}])
    selection.to_parquet(metrics_dir / "representative_episode_selection.parquet", index=False)

    fig, axes = plt.subplots(4, 1, figsize=(10.6, 9.4), sharex=True)
    p = pred[pred["flight_id"].astype(str).eq(flight_id)].copy()
    p["_stage"] = pd.Categorical(p["snapshot_stage"], STAGES, ordered=True)
    p = p.sort_values("_stage")
    axes[0].plot(p["snapshot_stage"], p["p_exceed_15"], "o-", label="Pr(Y > 15)")
    if "p_window" in p:
        win = p["p_window"].to_numpy(float)
        win_missing = np.isnan(win) | (win < 0)
        # 可用点用实线连接
        x_vals = np.arange(len(p))
        for i in range(len(x_vals) - 1):
            if not win_missing[i] and not win_missing[i + 1]:
                axes[0].plot(p["snapshot_stage"].iloc[[i, i + 1]], win[[i, i + 1]], "s-", color="C1")
        avail = ~win_missing
        if avail.any():
            axes[0].plot(p["snapshot_stage"].iloc[avail], win[avail], "s-", color="C1",
                         markerfacecolor="none", label="Window risk")
        if win_missing.any():
            for idx in np.where(win_missing)[0]:
                axes[0].annotate("NA", (p["snapshot_stage"].iloc[idx], 0.5),
                                 ha="center", va="center", fontsize=8, color="gray")
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Probability")
    axes[0].set_title("A. M1 execution risk")
    axes[0].legend(frameon=False)

    q = m2[m2["flight_id"].astype(str).eq(flight_id)].copy()
    q["_stage"] = pd.Categorical(q["snapshot_stage"], STAGES, ordered=True)
    q = q.sort_values("_stage")
    for channel in CHANNELS:
        column = f"cost_rmb_mean_{channel}"
        if column in q:
            axes[1].plot(q["snapshot_stage"], q[column], "o-", label=channel)
    axes[1].set_ylabel("Expected cost (RMB)")
    axes[1].set_title("B. M2 pre-action channel costs")
    axes[1].legend(frameon=False)

    c = candidates[candidates["flight_id"].astype(str).eq(flight_id) & candidates["action_id"].astype(str).ne("A00")]
    count_table = []
    for stage in STAGES:
        subset = c[c["snapshot_stage"].astype(str).eq(stage)]
        count_table.append((
            stage,
            int(subset["physical_feasible"].sum()) if len(subset) else 0,
            int((subset["physical_feasible"] & subset["decision_value_pass"]).sum()) if len(subset) else 0,
            int(subset["candidate_flag"].sum()) if len(subset) else 0,
        ))
    count_frame = pd.DataFrame(count_table, columns=["stage", "physical", "decision", "retained"])
    # grouped bars 替代折线图
    x_bar = np.arange(len(STAGES))
    width = 0.25
    for i, (column, label) in enumerate([("physical", "Physical"), ("decision", "DV-pass"), ("retained", "Evaluated")]):
        axes[2].bar(x_bar + (i - 1) * width, count_frame[column], width, label=label)
    axes[2].set_xticks(x_bar, STAGES)
    axes[2].set_ylabel("Non-null action count")
    axes[2].set_title("C. M4 screening")
    axes[2].legend(frameon=False, ncol=3)

    r = rankings[rankings["flight_id"].astype(str).eq(flight_id)].copy()
    if not r.empty:
        for stage in STAGES:
            subset = r[r["snapshot_stage"].astype(str).eq(stage)].nsmallest(5, "score")
            if subset.empty:
                continue
            x = np.full(len(subset), STAGES.index(stage), dtype=float)
            axes[3].scatter(x, subset["score"], color="0.45")
            for ranked in subset.sort_values("rank").itertuples(index=False):
                axes[3].annotate(
                    f"@{int(ranked.rank)} {ranked.action_id}",
                    (STAGES.index(stage), float(ranked.score)),
                    xytext=(4, 2), textcoords="offset points", fontsize=7,
                )
            recommended = subset[subset["recommended"].fillna(False).astype(bool)]
            if len(recommended):
                rec = recommended.iloc[0]
                axes[3].scatter([STAGES.index(stage)], [float(rec["score"])],
                                marker="*", s=100, color="black", zorder=3)
    axes[3].set_xticks(range(len(STAGES)), STAGES)
    axes[3].set_ylabel("Mean–CVaR score (RMB)")
    axes[3].set_title("D. Ranking@1/@2/@3/@5 within the top five (star = @1)")
    short_id = str(flight_id)[:8] + "..." if len(str(flight_id)) > 8 else str(flight_id)
    fig.suptitle(f"Representative rolling episode: {short_id}")
    fig.tight_layout()
    save_figure(fig, out)


