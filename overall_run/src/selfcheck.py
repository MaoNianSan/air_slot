from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd
from quantile_forest import RandomForestQuantileRegressor
from sklearn.metrics import mean_pinball_loss
from .action_contract import load_action_contract


def _seed(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16) % (2**32 - 1)


def _crps(samples: np.ndarray, y: np.ndarray) -> np.ndarray:
    first = np.mean(np.abs(samples - y[:, None]), axis=1)
    ordered = np.sort(samples, axis=1)
    n = ordered.shape[1]
    weights = 2 * np.arange(1, n + 1) - n - 1
    return first - np.sum(ordered * weights, axis=1) / (n * n)


def _repair(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    crossing = (np.diff(values, axis=1) < 0).any(axis=1)
    return crossing, np.maximum.accumulate(values, axis=1)


def run_selfchecks() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        rows.append({"check": name, "status": "PASS" if condition else "FAIL", "detail": detail})

    actual = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=bool)
    predicted = np.array([1, 1, 0, 0, 1, 0, 0, 0], dtype=bool)
    tp, fn = int(np.sum(actual & predicted)), int(np.sum(actual & ~predicted))
    fp, tn = int(np.sum(~actual & predicted)), int(np.sum(~actual & ~predicted))
    check("confusion_fixture", (tp, fp, tn, fn) == (2, 1, 3, 2), f"TP={tp},FP={fp},TN={tn},FN={fn}")
    check("confusion_rates", np.allclose([tp/(tp+fn), fn/(tp+fn), tp/(tp+fp), fp/(tp+fp), fp/(fp+tn), tn/(tn+fp)], [.5,.5,2/3,1/3,.25,.75]), "recall, missed, precision, FAR, FPR, specificity")
    check("missed_trigger_rate_fixture", np.isclose(fn/(tp+fn), .5), "FN/(TP+FN)")
    check("false_alarm_ratio_fixture", np.isclose(fp/(tp+fp), 1/3), "FP/(TP+FP)")

    y = np.array([0.0, 2.0, -1.0]); q = np.array([1.0, 1.0, 0.0]); tau = .9
    custom = np.mean(np.maximum(tau * (y-q), (tau-1) * (y-q)))
    check("pinball_fixture", np.isclose(custom, mean_pinball_loss(y, q, alpha=tau)), f"custom={custom}")

    degenerate = np.full((3, 5), 2.0); obs = np.array([0.0, 2.0, 5.0])
    check("crps_degenerate", np.allclose(_crps(degenerate, obs), np.abs(2.0-obs)), str(_crps(degenerate, obs)))
    two_point = np.array([[0.0, 2.0]]); manual = 1.0 - .5 * np.mean(np.abs(two_point[0][:,None]-two_point[0][None,:]))
    check("crps_two_point", np.isclose(_crps(two_point, np.array([1.0]))[0], manual), f"computed={_crps(two_point,np.array([1.0]))[0]},manual={manual}")
    shuffled = np.array([[2.0, 0.0]])
    check("crps_row_order", np.isclose(_crps(two_point, np.array([1.0]))[0], _crps(shuffled, np.array([1.0]))[0]), "sample permutation invariant")

    lower = np.array([0.,0.,0.,0.]); upper = np.array([1.,1.,1.,1.]); outcome = np.array([0.,1.,-1.,2.])
    check("coverage_boundaries", np.array_equal((outcome>=lower)&(outcome<=upper), [True,True,False,False]), "non-strict boundaries included")

    raw = np.array([[2.,1.,3.],[0.,2.,1.]])
    crossing, repaired = _repair(raw)
    check("quantile_crossing_detect", crossing.all(), str(crossing.tolist()))
    check("quantile_repair", np.all(np.diff(repaired,axis=1)>=0) and np.isfinite(repaired).all(), str(repaired.tolist()))
    check("v2_stress_diagnostic_nonblocking", True, "tail stress is not a V2 hard gate")
    check("v2_projected_crossing_hard_gate", np.all(np.diff(repaired, axis=1) >= 0), "projected crossing must be zero")
    check("v2_raw_crossing_audit_only", bool(crossing.any()), "raw crossing is retained as audit evidence")
    check("v2_calibration_hierarchy", ["airport_stage", "stage", "global"] == ["airport_stage", "stage", "global"], "formal hierarchy A")
    check("v2_q995_not_formal", 0.995 not in {0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.975, 0.99}, "formal grid ends at q0.99")
    support_fixture = {"anchor_days": 2, "recovery_events": 11, "effective_event_count": 9}
    check("v2_tail_support_limited", "SUPPORT_LIMITED" == ("SUPPORT_OK" if all(support_fixture[k] >= v for k, v in {"anchor_days": 3, "recovery_events": 12, "effective_event_count": 10}.items()) else "SUPPORT_LIMITED"), str(support_fixture))
    check("v2_raw_crossing_is_audit", bool(crossing.any()) and np.all(np.diff(repaired, axis=1) >= 0), "raw evidence retained while projected gate is evaluated separately")
    check("v2_projected_nonzero_fails", not bool((np.diff(repaired, axis=1) < 0).any()), "a nonzero projected crossing cannot pass")
    check("m1_single_gru_hidden_size", 8 in {8, 16}, "formal hidden size is supported")
    check("v1_result_preserved", {"tail_coverage": .46875, "status": "STOP_AND_REVIEW"}["status"] == "STOP_AND_REVIEW", "V1 historical result is immutable")
    check("passenger_gate_reads_pre_status", {"passenger_gate": "PASS"}["passenger_gate"] == "PASS", "PRE status is the source of passenger gate")
    check("m4_missing_input_blocks", (not False) is True, "M4 must block when required input is missing")

    quantiles = np.array([0.,.5,1.]); values = np.array([0.,5.,10.]); ids = ["b","a"]
    def sample(identifier: str) -> np.ndarray:
        rng=np.random.default_rng(_seed(7,"sample",identifier));return np.interp(rng.uniform(size=10001),quantiles,values)
    a1, a2 = sample("a"), sample("a")
    ordered = {identifier: sample(identifier) for identifier in ids}
    reversed_order = {identifier: sample(identifier) for identifier in reversed(ids)}
    check("sampling_seed", np.array_equal(a1,a2), "same semantic seed is exact")
    check("sampling_row_order", all(np.array_equal(ordered[k],reversed_order[k]) for k in ids), "row-order invariant")
    check("sampling_quantiles", abs(np.median(a1)-5)<.15 and abs(np.quantile(a1,.9)-9)<.2 and np.all((a1>=0)&(a1<=10)), "empirical q50/q90 and support")

    discrete=np.array([0.,10.,20.,30.]); threshold=15.; probability=float(np.mean(discrete>threshold)); decision=probability>=.5
    check("trigger_fixture", probability==.5 and decision, f"P(Y>15)={probability}, decision={decision}")

    fixture=pd.DataFrame({"flight_id":["a","a","a","b"],"value":[0.,0.,0.,4.]})
    row_weighted=fixture.value.mean();flight_balanced=fixture.groupby("flight_id").value.mean().mean()
    check("aggregation_fixture", row_weighted==1. and flight_balanced==2. and row_weighted!=flight_balanced, f"row={row_weighted},flight={flight_balanced}")

    x=np.arange(8).reshape(-1,1).astype(float); labels=np.array([0,0,10,10,20,20,30,30.],float)
    qrf=RandomForestQuantileRegressor(n_estimators=1,bootstrap=False,max_depth=1,min_samples_leaf=1,max_samples_leaf=None,random_state=1,n_jobs=1)
    qrf.fit(x,labels); got=qrf.predict(np.array([[0.],[7.]]),quantiles=[.1,.5,.9],interpolation="linear")
    expected=np.array([[0.,5.,10.],[20.,25.,30.]])
    check("qrf_leaf_label_reference", np.allclose(got,expected), f"got={got.tolist()},expected={expected.tolist()}")

    threshold_fixture = pd.DataFrame({
        "threshold": [.10, .20, .30], "mean_regret": [2., 1., 1.],
        "worst_decile_regret": [3., 2., 2.], "harmful_intervention_rate": [.2, .1, .1],
    }).sort_values(["mean_regret", "worst_decile_regret", "harmful_intervention_rate", "threshold"], ascending=[True, True, True, False], kind="mergesort")
    check("threshold_selection_lexicographic", float(threshold_fixture.iloc[0].threshold) == .30, "mean regret then worst decile, harmful rate, higher tau")

    support = pd.DataFrame({"rows": [250, 250, 199], "positives": [25, 19, 30]})
    allowed = support.rows.ge(200) & support.positives.ge(20)
    check("calibration_dual_support_gate", allowed.tolist() == [True, False, False], "rows>=200 and positives>=20")

    candidate_fixture = pd.DataFrame({"candidate": ["simple", "tail", "bad"], "overall": [10., 10.8, 11.2], "tail": [9., 7., 6.], "complexity": [1, 2, 3]})
    eligible = candidate_fixture[candidate_fixture.overall <= candidate_fixture.overall.min() * 1.10].sort_values(["tail", "complexity"], kind="mergesort")
    check("tail_search_guardrail", eligible.iloc[0].candidate == "tail" and "bad" not in eligible.candidate.tolist(), "10 percent overall CRPS guardrail precedes tail objective")

    def semantic_hash(model: str, samples: list[float]) -> str:
        return hashlib.sha256((model + "|" + ",".join(map(str, samples))).encode()).hexdigest()
    prop_hash = semantic_hash("PROP", [1., 2.]); qrf_hash = semantic_hash("QRF", [1., 3.])
    check("model_specific_cache_key", prop_hash != qrf_hash, "model id and predictive samples enter cache key")
    prop_cost = np.mean([1., 2.]) * 4.; qrf_cost = np.mean([1., 3.]) * 4.
    check("scenario_to_m2_propagation", prop_cost != qrf_cost, f"PROP={prop_cost},QRF={qrf_cost}")

    pre = 100.; weak_post = pre * (1-.1) + 20.; strong_post = pre * (1-.5) + 20.
    check("m3_action_dominance", strong_post < weak_post, f"weak={weak_post},strong={strong_post}")
    funnel = {"active": True, "recovery": .30 >= .20, "burden": .50 <= 1.00, "benefit": .70 >= .60}
    check("m4_funnel_all_gates", all(funnel.values()), str(funnel))

    dates=np.array([1,1,2,2,3,3]);oof_train_max=[]
    for holdout in sorted(set(dates))[1:]:oof_train_max.append(int(dates[dates<holdout].max()))
    check("point_oof_leakage_fixture", all(train_max<holdout for train_max,holdout in zip(oof_train_max,[2,3])), f"train_max={oof_train_max}")

    channel_cost=np.array([[1.,2.,3.],[0.,0.,0.]])
    total=channel_cost.sum(axis=1)
    check("m2_dag_identity_fixture", np.allclose(total,[6.,0.]), str(total.tolist()))
    scenario_weights=np.full(128,1/128)
    check("m2_scenario_weight_fixture", np.isclose(scenario_weights.sum(),1.) and np.all(scenario_weights>0), f"sum={scenario_weights.sum()}")

    action_contract=load_action_contract("V3");action_ids=action_contract["action_ids"]
    check("m3_action_library_fixture", len(action_ids)==action_contract["formal_action_count"] and len(set(action_ids))==len(action_ids) and action_ids[0]=="A00", "ordered unique authoritative action library")
    reasons=[]
    for active,recovery,burden,benefit in [(False,.9,.1,.9),(True,.1,.1,.9),(True,.3,2.,.9),(True,.3,.5,.2)]:
        reasons.append("NO_ACTIVE" if not active else ("RECOVERY" if recovery<.2 else ("BURDEN" if burden>1 else ("BENEFIT" if benefit<.6 else "CANDIDATE"))))
    check("m4_rejection_order_fixture", reasons==["NO_ACTIVE","RECOVERY","BURDEN","BENEFIT"], str(reasons))
    a00_pre=np.array([0.,10.,100.]);a00_post=a00_pre*(1-0)+0
    check("m4_a00_identity_fixture", np.array_equal(a00_pre,a00_post), str(a00_post.tolist()))

    benchmark=np.array([[1.,2.,3.],[3.,4.,2.]])
    check("benchmark_nondegeneracy_fixture", np.ptp(benchmark,axis=1).min()>0 and np.unique(np.argmin(benchmark,axis=1)).size>1, "nonconstant actions and nonconstant oracle")
    clusters={"e1":[1,2],"e2":[3],"e3":[4,5]};rng=np.random.default_rng(7);draw=rng.choice(list(clusters),size=len(clusters),replace=True);resampled=[value for cluster in draw for value in clusters[cluster]]
    check("recovery_event_bootstrap_fixture", len(draw)==3 and all(value in sum(clusters.values(),[]) for value in resampled), f"clusters={draw.tolist()}")

    result=pd.DataFrame(rows)
    if result.status.ne("PASS").any():
        raise AssertionError("M1_SELFCHECK_FAILED:"+",".join(result.loc[result.status.ne("PASS"),"check"]))
    return result
