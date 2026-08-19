"""M1 horizon predictive-accuracy QUICK DIAGNOSTIC (2026-08-18).

READ-ONLY. Reuses ONLY existing frozen artifacts:
  - M1_SIGNED_DEVELOPMENT_SCENARIOS_V1 (node.parquet + scenario.parquet)
  - M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1.npz (frozen realized labels)
No PRE rebuild, no M1 retraining, no H/W rerun, no Exp1 rerun, no final-test access.

Outputs (written by a second step):
  - artifacts/diagnostics/M1_HORIZON_ACCURACY_QUICK_20260818.json
  - docs/diagnostics/M1_HORIZON_ACCURACY_QUICK_20260818.md
This script only computes and dumps the M1 part as JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
SCENARIO_DIR = FREEZE / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
CACHE_NPZ = FREEZE / "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1.npz"
SCENARIO_MANIFEST = FREEZE / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1_MANIFEST.json"
CACHE_MANIFEST = FREEZE / "M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1_MANIFEST.json"
OUT_JSON = ROOT / "artifacts" / "diagnostics" / "M1_HORIZON_ACCURACY_QUICK_20260818.json"

HORIZONS = (30, 60, 120, 180, 240, 300, 360, 420, 480)
TOLERANCES = (5, 10, 15, 30)
TARGETS = ("R_IB", "DELTA_OB", "T_TX")


# ---------------------------------------------------------------------------
# Frozen bin contracts (exact mirror of model/M1/contracts.py TargetBinContract
# with the frozen scientific parameter values; verified below by round-trip).
# ---------------------------------------------------------------------------
class _Bin:
    def __init__(self, name, width, finite_min, finite_max, signed):
        self.name = name
        self.width = width
        self.finite_min = finite_min
        self.finite_max = finite_max
        self.signed = signed

    @property
    def class_count(self):
        finite = (self.finite_max - self.finite_min) // self.width + 1
        return finite + (2 if self.signed else 1)

    @property
    def underflow_index(self):
        return 0 if self.signed else None

    @property
    def finite_start_index(self):
        return 1 if self.signed else 0

    @property
    def overflow_index(self):
        return self.class_count - 1

    def representative(self, index):
        if self.signed and index == self.underflow_index:
            return self.finite_min - self.width / 2, True, False
        if index == self.overflow_index:
            return self.finite_max + self.width, False, True
        start = self.finite_min + (index - self.finite_start_index) * self.width
        return start + self.width / 2, False, False

    def encode(self, value):
        if self.signed:
            if value < self.finite_min:
                return self.underflow_index
            if value >= self.finite_max + self.width:
                return self.overflow_index
            return self.finite_start_index + min(
                int((value - self.finite_min) // self.width),
                self.overflow_index - self.finite_start_index - 1,
            )
        if value >= self.finite_max + self.width:
            return self.overflow_index
        return min(int(value // self.width), self.overflow_index - 1)


BINS = {
    "R_IB": _Bin("R_IB", 5, 0, 360, False),
    "DELTA_OB": _Bin("DELTA_OB", 5, -180, 180, True),
    "T_TX": _Bin("T_TX", 5, 0, 60, False),
}


def _verify_contracts() -> None:
    checks = {
        "R_IB": [(0, 2.5), (26, 132.5), (72, 362.5), (73, 365.0)],
        "DELTA_OB": [(0, -182.5), (37, 2.5), (55, 92.5), (73, 182.5), (74, 185.0)],
        "T_TX": [(0, 2.5), (11, 57.5), (12, 62.5), (13, 65.0)],
    }
    for name, rows in checks.items():
        contract = BINS[name]
        for index, expected in rows:
            value, _u, _o = contract.representative(index)
            assert abs(value - expected) < 1e-9, (name, index, value, expected)
            assert contract.encode(value) == index, (name, index)
    # observed dev label extrema round-trip
    assert BINS["DELTA_OB"].representative(74)[0] == 185.0


def nearest_horizon(values: np.ndarray) -> np.ndarray:
    """Deterministic matching onto the canonical 5-min decision grid.

    Realized leads are always of the form integer + k*5 + 2.5 (x.5 minutes),
    so they can never tie with the integer midpoint boundaries.
    """
    boundaries = np.array([(HORIZONS[i] + HORIZONS[i + 1]) / 2.0 for i in range(len(HORIZONS) - 1)])
    return np.array(HORIZONS)[np.sum(values[:, None] > boundaries[None, :], axis=1)]


def crps_energy(draws_sorted: np.ndarray, realized: np.ndarray) -> np.ndarray:
    """CRPS per row: (1/S) sum |x - y| - (1/S^2) sum_{i<j} |x_i - x_j|."""
    s = draws_sorted.shape[1]
    abs_err = np.abs(draws_sorted - realized[:, None]).mean(axis=1)
    weights = 2.0 * np.arange(s) - s + 1.0
    pair_sum = (draws_sorted * weights[None, :]).sum(axis=1)
    return abs_err - pair_sum / (s * s)


def encode_vectorized(values: np.ndarray, contract: _Bin) -> np.ndarray:
    """Vectorized mirror of TargetBinContract.encode."""
    out = np.empty(values.shape, dtype=np.int64)
    if contract.signed:
        finite = np.clip(
            ((values - contract.finite_min) // contract.width).astype(np.int64),
            0,
            contract.overflow_index - contract.finite_start_index - 1,
        ) + contract.finite_start_index
        finite = np.where(values < contract.finite_min, 0, finite)
        finite = np.where(values >= contract.finite_max + contract.width, contract.overflow_index, finite)
        out[...] = finite
    else:
        enc = np.minimum(
            (values // contract.width).astype(np.int64), contract.overflow_index - 1
        )
        enc = np.where(values >= contract.finite_max + contract.width, contract.overflow_index, enc)
        out[...] = enc
    return out


def nll_binned(draws: np.ndarray, realized_label: np.ndarray, contract: _Bin) -> tuple[np.ndarray, float]:
    """-log empirical probability of the realized bin from 250 aligned draws."""
    encoded = encode_vectorized(draws, contract)
    hit = (encoded == realized_label[:, None])
    share = hit.mean(axis=1)
    zero_frac = float((share == 0).mean())
    return -np.log(np.clip(share, 1e-6, 1.0)), zero_frac


def main() -> None:
    _verify_contracts()
    scenario_manifest = json.loads(SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    cache_manifest = json.loads(CACHE_MANIFEST.read_text(encoding="utf-8"))

    # ---- node table -------------------------------------------------------
    nodes = pd.read_parquet(SCENARIO_DIR / "node.parquet")
    assert len(nodes) == 1824
    nodes = nodes.reset_index(drop=True)
    nodes["decision_time"] = pd.to_datetime(nodes["decision_time"], utc=True)
    nodes["scheduled_ob_utc"] = pd.to_datetime(nodes["scheduled_ob_utc"], utc=True)

    # ---- frozen cache labels (development split) --------------------------
    z = np.load(CACHE_NPZ, allow_pickle=True)
    splits = z["sample_splits"].astype(str)
    dev_idx = np.where(splits == "development")[0]
    assert len(dev_idx) == 1824
    assert (nodes["sample_index"].to_numpy() == dev_idx).all(), "node.parquet order != cache dev order"
    cache_node_ids = z["sample_decision_node_ids"][dev_idx]
    assert (nodes["decision_node_id"].to_numpy() == cache_node_ids).all(), "node id mismatch"
    labels = {name: z[f"labels_{name}"][dev_idx].astype(np.int64) for name in TARGETS}
    active = {name: z[f"active_{name}"][dev_idx].astype(bool) for name in TARGETS}

    realized = {}
    tail_flags = {}
    for name in TARGETS:
        contract = BINS[name]
        val = np.full(1824, np.nan)
        under = np.zeros(1824, dtype=bool)
        over = np.zeros(1824, dtype=bool)
        for i in range(1824):
            if active[name][i]:
                v, u, o = contract.representative(int(labels[name][i]))
                val[i], under[i], over[i] = float(v), bool(u), bool(o)
        realized[name] = val
        tail_flags[name] = {"underflow": under, "overflow": over}

    # ---- scenario draws ---------------------------------------------------
    scenarios = pd.read_parquet(SCENARIO_DIR / "scenario.parquet")
    assert len(scenarios) == 1824 * 250
    node_order = {node_id: i for i, node_id in enumerate(nodes["decision_node_id"].to_numpy())}
    scenarios["node_idx"] = scenarios["decision_node_id"].map(node_order).astype(np.int32)
    assert scenarios["node_idx"].notna().all()
    scenarios = scenarios.sort_values(["node_idx", "scenario_id"], kind="stable")
    draw_columns = {
        "R_IB": "r_ib_minutes",
        "DELTA_OB": "delta_ob_minutes",
        "T_TX": "t_tx_minutes",
        "D_TO": "d_to_minutes",
    }
    draws = {
        name: scenarios[col].to_numpy(dtype=np.float64).reshape(1824, 250)
        for name, col in draw_columns.items()
    }

    # ---- realized horizons -------------------------------------------------
    lead_to_off_block = (
        (nodes["scheduled_ob_utc"] - nodes["decision_time"]).dt.total_seconds().to_numpy() / 60.0
        + realized["DELTA_OB"]
    )
    lead_to_takeoff = lead_to_off_block + realized["T_TX"]
    # DELTA_OB inactive nodes (POST_OB_PRE_TO, n=53): use exact observed value for lead math
    lead_to_off_block[~active["DELTA_OB"]] = (
        (nodes.loc[~active["DELTA_OB"], "scheduled_ob_utc"]
         - nodes.loc[~active["DELTA_OB"], "decision_time"])
        .dt.total_seconds().to_numpy() / 60.0
        + nodes.loc[~active["DELTA_OB"], "observed_delta_ob"].to_numpy(dtype=np.float64)
    )

    horizon_map = {
        "R_IB": realized["R_IB"],               # lead time to predecessor in-block
        "DELTA_OB": lead_to_off_block,          # lead time to successor off-block
        "T_TX": lead_to_takeoff,                # lead time to successor takeoff
        "D_TO": lead_to_takeoff,
    }
    horizon_allowed = {
        "R_IB": active["R_IB"],
        "DELTA_OB": active["DELTA_OB"],
        # T_TX / D_TO: exclude POST_OB_PRE_TO nodes (event partially elapsed at decision time)
        "T_TX": active["T_TX"] & (nodes["operational_stage"].to_numpy() != "POST_OB_PRE_TO"),
        "D_TO": active["T_TX"] & (nodes["operational_stage"].to_numpy() != "POST_OB_PRE_TO"),
    }

    # ---- derived realized D_TO (frozen identity) ----------------------------
    taxi_ref = nodes["taxi_reference_minutes"].to_numpy(dtype=np.float64)
    realized_d_to = np.maximum(0.0, realized["DELTA_OB"] + realized["T_TX"] - taxi_ref)
    realized_d_to[~np.isfinite(taxi_ref)] = np.nan
    realized_d_to[~active["T_TX"]] = np.nan  # D_TO only meaningful where joint available

    # ---- per-target aggregation --------------------------------------------
    output = {
        "schema_version": "M1_HORIZON_ACCURACY_QUICK_20260818_V1",
        "classification": ["DEVELOPMENT_ONLY", "QUICK_DIAGNOSTIC", "NOT_FINAL_PAPER_RESULT"],
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "readonly": True,
        "flags": {
            "PRE_REBUILT": False,
            "M1_RETRAINED": False,
            "H_W_RERUN": False,
            "EXP1_RERUN": False,
            "CALIBRATION_REFIT": False,
            "SCENARIO_REGENERATED": False,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        },
        "cohort": {
            "QUICK_DIAGNOSTIC_COHORT": "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1",
            "episodes": int(scenario_manifest["episode_count"]),
            "nodes": int(scenario_manifest["node_count"]),
            "scenarios_per_node": int(scenario_manifest["scenario_count"]),
            "split": scenario_manifest["split"],
            "artifact_hash": scenario_manifest["artifact_hash"],
            "cache_hash": cache_manifest["cache_hash"],
            "repository_sha": scenario_manifest["repository_sha"],
            "temperatures": scenario_manifest["calibration_artifact"]["temperatures"],
        },
        "horizon_matching_rule": (
            "nearest allowed horizon in {30,...,480}; realized leads live on the canonical "
            "5-min grid as integer + k*5 + 2.5 minutes so ties are impossible"
        ),
        "horizon_definition": {
            "R_IB": "realized predecessor in-block time remaining from decision time (minutes)",
            "DELTA_OB": "(scheduled successor off-block - decision time) + realized DELTA_OB (minutes to off-block)",
            "T_TX": "(scheduled successor off-block - decision time) + realized DELTA_OB + realized T_TX (minutes to takeoff)",
            "D_TO": "same lead-to-takeoff as T_TX",
        },
        "realized_label_source": (
            "frozen cache labels M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1 (5-min bin representatives, "
            "verified by the frozen scenario artifact with 0 mismatches vs pinned BTS exacts)"
        ),
        "targets": {},
    }

    for name in TARGETS:
        allowed = horizon_allowed[name]
        hvals = horizon_map[name]
        y = realized[name]
        d = draws[name]
        med = np.median(d, axis=1)
        err = med - y

        support = {
            "total_nodes": 1824,
            "active_nodes": int(active[name].sum()),
            "abstain_nodes": int((~active[name]).sum()),
            "abstain_reason": "target event already realized at decision time (frozen point-collapse)",
        }
        rows = []
        for h in HORIZONS:
            mask = allowed & np.isfinite(hvals) & (nearest_horizon(hvals) == h)
            if not mask.any():
                continue
            ym, em, dm = y[mask], err[mask], d[mask]
            ae = np.abs(em)
            q = np.percentile(dm, [5, 10, 25, 75, 90, 95], axis=1)
            cov50 = np.mean((ym >= q[2]) & (ym <= q[3]))
            cov80 = np.mean((ym >= q[1]) & (ym <= q[4]))
            cov90 = np.mean((ym >= q[0]) & (ym <= q[5]))
            nll, zero_frac = nll_binned(dm, labels[name][mask], BINS[name])
            rows.append({
                "horizon_minutes": h,
                "N": int(mask.sum()),
                "N_episodes": int(nodes.loc[mask, "episode_id"].nunique()),
                "MAE_min": float(np.mean(ae)),
                "MedianAE_min": float(np.median(ae)),
                "RMSE_min": float(np.sqrt(np.mean(em**2))),
                **{f"acc_within_{tol}_min": float(np.mean(ae <= tol)) for tol in TOLERANCES},
                "NLL": float(np.mean(nll)),
                "NLL_zero_bin_share": float(zero_frac),
                "CRPS_min": float(np.mean(crps_energy(np.sort(dm, axis=1), ym))),
                "cov50": float(cov50),
                "cov80": float(cov80),
                "cov90": float(cov90),
                "width50_min": float(np.mean(q[3] - q[2])),
                "width80_min": float(np.mean(q[4] - q[1])),
                "width90_min": float(np.mean(q[5] - q[0])),
                "realized_overflow_count": int(tail_flags[name]["overflow"][mask].sum()),
                "realized_underflow_count": int(tail_flags[name]["underflow"][mask].sum()),
            })
        in_range = allowed & np.isfinite(hvals) & (hvals >= 30) & (hvals <= 480)
        out_of_range = int((allowed & np.isfinite(hvals)).sum() - in_range.sum())
        overall_mask = allowed & np.isfinite(y)
        ae_o = np.abs(err[overall_mask])
        support.update({
            "evaluable_nodes": int(overall_mask.sum()),
            "nodes_with_realized_horizon_in_30_480": int(in_range.sum()),
            "nodes_with_realized_horizon_outside_30_480": out_of_range,
            "note": ("all finite realized horizons are assigned to a bucket by the deterministic "
                     "nearest-horizon rule; this count only reports where the realized lead itself "
                     "falls outside [30, 480]"),
        })
        output["targets"][name] = {
            "unit": "minutes",
            "support": support,
            "overall": {
                "N": int(overall_mask.sum()),
                "N_episodes": int(nodes.loc[overall_mask, "episode_id"].nunique()),
                "MAE_min": float(np.mean(ae_o)),
                "MedianAE_min": float(np.median(ae_o)),
                "RMSE_min": float(np.sqrt(np.mean(err[overall_mask] ** 2))),
                **{f"acc_within_{tol}_min": float(np.mean(ae_o <= tol)) for tol in TOLERANCES},
            },
            "horizons": rows,
        }

    # ---- D_TO (derived, frozen identity only) -------------------------------
    dt_allowed = horizon_allowed["D_TO"] & np.isfinite(realized_d_to)
    dt_h = horizon_map["D_TO"]
    dt_y = realized_d_to
    dt_d = draws["D_TO"]
    dt_med = np.median(dt_d, axis=1)
    dt_err = dt_med - dt_y
    dt_rows = []
    for h in HORIZONS:
        mask = dt_allowed & np.isfinite(dt_h) & (nearest_horizon(dt_h) == h)
        if not mask.any():
            continue
        ym, em = dt_y[mask], dt_err[mask]
        ae = np.abs(em)
        dt_rows.append({
            "horizon_minutes": h,
            "N": int(mask.sum()),
            "N_episodes": int(nodes.loc[mask, "episode_id"].nunique()),
            "MAE_min": float(np.mean(ae)),
            "MedianAE_min": float(np.median(ae)),
            "RMSE_min": float(np.sqrt(np.mean(em**2))),
            **{f"acc_within_{tol}_min": float(np.mean(ae <= tol)) for tol in TOLERANCES},
        })
    output["targets"]["D_TO"] = {
        "status": "DERIVED_FROM_FROZEN_IDENTITY",
        "unit": "minutes",
        "identity": "max(0, realized DELTA_OB + realized T_TX - frozen taxi reference)",
        "caveats": "realized D_TO built from 5-min binned labels (+-2.5 min quantization); taxi reference frozen",
        "overall": {
            "N": int(dt_allowed.sum()),
            "MAE_min": float(np.mean(np.abs(dt_err[dt_allowed]))),
            "MedianAE_min": float(np.median(np.abs(dt_err[dt_allowed]))),
            "RMSE_min": float(np.sqrt(np.mean(dt_err[dt_allowed] ** 2))),
            **{f"acc_within_{tol}_min": float(np.mean(np.abs(dt_err[dt_allowed]) <= tol)) for tol in TOLERANCES},
        },
        "horizons": dt_rows,
    }

    # ---- warning-event (D_TO > 30) operating-point evidence -----------------
    p_hat_dto_gt30 = (draws["D_TO"] > 30.0).mean(axis=1)
    dto_positive = dt_allowed & (realized_d_to > 30.0)
    dto_negative = dt_allowed & (realized_d_to <= 30.0)
    fixed_threshold = 0.384  # frozen Exp1 FIXED_HISTORY operating point at target FPR 0.1

    def _warn_stats(mask: np.ndarray) -> dict:
        p = p_hat_dto_gt30[mask]
        return {
            "N_nodes": int(mask.sum()),
            "N_episodes": int(nodes.loc[mask, "episode_id"].nunique()),
            "median_p_hat_DTO_gt30": float(np.median(p)),
            "mean_p_hat_DTO_gt30": float(np.mean(p)),
            "share_ge_0.384": float(np.mean(p >= fixed_threshold)),
            "share_ge_0.5": float(np.mean(p >= 0.5)),
            "share_ge_0.8": float(np.mean(p >= 0.8)),
        }

    pos_by_horizon = []
    for h in HORIZONS:
        mask = dto_positive & np.isfinite(dt_h) & (nearest_horizon(dt_h) == h)
        if not mask.any():
            continue
        p = p_hat_dto_gt30[mask]
        pos_by_horizon.append({
            "horizon_minutes": h,
            "N_nodes": int(mask.sum()),
            "median_p_hat_DTO_gt30": float(np.median(p)),
            "share_ge_0.384": float(np.mean(p >= fixed_threshold)),
        })
    output["warning_event_evidence"] = {
        "event": "D_TO_POST_GT_30",
        "event_definition": "realized D_TO > 30 minutes (strict)",
        "p_hat_source": "share of the 250 frozen aligned scenario draws with d_to_minutes > 30",
        "frozen_fixed_threshold": fixed_threshold,
        "positive_nodes_realized_DTO_gt_30": _warn_stats(dto_positive),
        "negative_nodes_realized_DTO_le_30": _warn_stats(dto_negative),
        "positive_nodes_by_horizon": pos_by_horizon,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print("WROTE", OUT_JSON)
    for name in ("R_IB", "DELTA_OB", "T_TX"):
        item = output["targets"][name]
        print(name, "support:", item["support"])
        print(name, "overall:", {k: round(v, 3) if isinstance(v, float) else v for k, v in item["overall"].items()})
        for row in item["horizons"]:
            print("  H=%3d N=%4d MAE=%6.2f RMSE=%6.2f ±10=%.3f ±15=%.3f ±30=%.3f cov50=%.3f cov80=%.3f cov90=%.3f"
                  % (row["horizon_minutes"], row["N"], row["MAE_min"], row["RMSE_min"],
                     row["acc_within_10_min"], row["acc_within_15_min"], row["acc_within_30_min"],
                     row["cov50"], row["cov80"], row["cov90"]))
    print("D_TO overall:", output["targets"]["D_TO"]["overall"])


if __name__ == "__main__":
    main()
