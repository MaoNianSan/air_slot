from __future__ import annotations

from collections import defaultdict
from math import isnan
from statistics import median

from exp.common.metrics_v2 import brier_score, crps_from_samples, paired_top1_disagreement


EXP1_HEADLINE_METRICS = (
    "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK",
    "SELECTED_TOP1_ACTION",
    "TOP1_ACTION_DISAGREEMENT",
    "CRPS_PRIMITIVE_TARGET",
    "BRIER_PRINCIPAL_DELAY_EVENT",
    "CALIBRATION",
)


def exp1a_metrics(*, reference_actions, comparison_actions, reference_risk=None, comparison_risk=None):
    """Evaluate Exp1A without treating replay as a causal action outcome."""
    keys = tuple(sorted(set(reference_actions) & set(comparison_actions)))
    disagreement = paired_top1_disagreement(reference_actions, comparison_actions)
    risk_difference = None
    if reference_risk is not None and comparison_risk is not None and keys:
        risk_difference = sum(
            float(comparison_risk[key]) - float(reference_risk[key])
            for key in keys
        ) / len(keys)
    return {
        "TOP1_ACTION_DISAGREEMENT": disagreement,
        "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK": risk_difference,
        "replay_interpretation": "EX_POST_MODEL_IMPLIED_RESIDUAL_RISK_UNDER_FROZEN_ACTION_RESPONSE",
    }


def exp1b_metrics(*, predictive_samples=None, observations=None, probabilities=None, events=None):
    """Return standard prediction metrics for the history-only contrast."""
    samples = predictive_samples or ()
    observations = observations or ()
    scores = tuple(
        score for score in (
            crps_from_samples(sample, observation)
            for sample, observation in zip(samples, observations)
        )
        if score is not None
    )
    return {
        "CRPS_PRIMITIVE_TARGET": sum(scores) / len(scores) if scores else None,
        "BRIER_PRINCIPAL_DELAY_EVENT": brier_score(probabilities or (), events or ()),
        "CALIBRATION": "AVAILABLE_FROM_RELIABILITY_TABLE" if probabilities and events else None,
    }


def scenario_grid_probability(value: float, scenario_count: int) -> float:
    if scenario_count <= 0:
        raise ValueError("EXP1_SCENARIO_COUNT_MUST_BE_POSITIVE")
    return round(float(value) * scenario_count) / scenario_count


def _ordered_rows(rows):
    return sorted(rows, key=lambda row: float(row["lead_time_minutes"]), reverse=True)


def _supported_pair_scores(rows, *, probability_key: str, step_minutes: int = 5):
    """Return the maximum two-node score and its earliest lead time."""
    ordered = _ordered_rows(rows)
    best_score = None
    best_lead = None
    previous = None
    for row in ordered:
        probability = row.get(probability_key)
        if row.get("warning_support_state") != "SUPPORTED" or probability is None or (
            isinstance(probability, float) and isnan(probability)
        ):
            previous = None
            continue
        if previous is not None:
            gap = float(previous["lead_time_minutes"]) - float(row["lead_time_minutes"])
            if abs(gap - step_minutes) <= 1e-9:
                score = min(float(previous[probability_key]), float(probability))
                if best_score is None or score > best_score:
                    best_score = score
                    best_lead = float(previous["lead_time_minutes"])
        previous = row
    return best_score, best_lead


def sustained_warning_lead_time(rows, *, probability_key: str, threshold: float,
                                step_minutes: int = 5) -> float:
    score, lead = _supported_pair_scores(
        rows, probability_key=probability_key, step_minutes=step_minutes)
    return lead if score is not None and score >= threshold else 0.0


def episode_operating_point(rows, *, probability_key: str, threshold: float,
                            step_minutes: int = 5) -> dict:
    ordered = _ordered_rows(rows)
    supported_pairs = 0
    previous = None
    any_warning = False
    first_warning_lead = None
    for row in ordered:
        probability = row.get(probability_key)
        if row.get("warning_support_state") != "SUPPORTED" or probability is None or (
            isinstance(probability, float) and isnan(probability)
        ):
            previous = None
            continue
        if float(probability) >= threshold:
            any_warning = True
            if first_warning_lead is None:
                first_warning_lead = float(row["lead_time_minutes"])
        if previous is not None:
            gap = float(previous["lead_time_minutes"]) - float(row["lead_time_minutes"])
            if abs(gap - step_minutes) <= 1e-9:
                supported_pairs += 1
        previous = row
    score, sustained_lead = _supported_pair_scores(
        rows, probability_key=probability_key, step_minutes=step_minutes)
    return {
        "evaluable": supported_pairs > 0,
        "abstain_insufficient_supported_sequence": supported_pairs == 0,
        "any_warning": any_warning,
        "sustained_warning": score is not None and score >= threshold,
        "sustained_score": score,
        "warning_lead_minutes": first_warning_lead,
        "sustained_warning_lead_minutes": (
            sustained_lead if score is not None and score >= threshold else None
        ),
        "supported_pair_count": supported_pairs,
    }


def evaluate_episode_rows(rows, *, probability_key: str, threshold: float,
                          step_minutes: int = 5) -> dict:
    if not rows:
        raise ValueError("EXP1_EPISODE_ROWS_EMPTY")
    result = episode_operating_point(
        rows, probability_key=probability_key, threshold=threshold,
        step_minutes=step_minutes)
    result["realized_event_positive"] = rows[0].get("realized_event_positive")
    result["episode_id"] = rows[0]["episode_id"]
    return result


def summarize_operating_point(rows, *, probability_key: str, threshold: float,
                              step_minutes: int = 5) -> dict:
    by_episode = defaultdict(list)
    for row in rows:
        by_episode[row["episode_id"]].append(row)
    evaluations = [
        evaluate_episode_rows(items, probability_key=probability_key,
                              threshold=threshold, step_minutes=step_minutes)
        for items in by_episode.values()
    ]
    positives = [item for item in evaluations if item["realized_event_positive"] is True]
    negatives = [item for item in evaluations if item["realized_event_positive"] is False]
    positive_evaluable = [item for item in positives if item["evaluable"]]
    negative_evaluable = [item for item in negatives if item["evaluable"]]
    positive_abstain = [item for item in positives if not item["evaluable"]]
    negative_abstain = [item for item in negatives if not item["evaluable"]]
    leads = [item["sustained_warning_lead_minutes"] for item in positive_evaluable
             if item["sustained_warning_lead_minutes"] is not None]
    ordered_leads = sorted(leads)
    q1 = ordered_leads[int((len(ordered_leads) - 1) * 0.25)] if ordered_leads else None
    q3 = ordered_leads[int((len(ordered_leads) - 1) * 0.75)] if ordered_leads else None
    return {
        "threshold": threshold,
        "achieved_episode_fpr": (
            sum(item["sustained_warning"] for item in negative_evaluable)
            / len(negative_evaluable) if negative_evaluable else None
        ),
        "episode_recall": (
            sum(item["any_warning"] for item in positive_evaluable)
            / len(positive_evaluable) if positive_evaluable else None
        ),
        "sustained_warning_recall": (
            sum(item["sustained_warning"] for item in positive_evaluable)
            / len(positive_evaluable) if positive_evaluable else None
        ),
        "median_risk_lead_minutes": median(leads) if leads else None,
        "iqr_risk_lead_minutes": q3 - q1 if leads else None,
        "p_risk_lead_gt_0": sum(value > 0 for value in leads) / len(leads) if leads else None,
        "p_risk_lead_ge_15": sum(value >= 15 for value in leads) / len(leads) if leads else None,
        "p_risk_lead_ge_30": sum(value >= 30 for value in leads) / len(leads) if leads else None,
        "false_warning_episode_count": sum(item["sustained_warning"] for item in negative_evaluable),
        "negative_total": len(negatives),
        "negative_evaluable": len(negative_evaluable),
        "negative_abstain": len(negative_abstain),
        "positive_total": len(positives),
        "positive_evaluable": len(positive_evaluable),
        "positive_abstain": len(positive_abstain),
        "negative_evaluation_coverage": len(negative_evaluable) / len(negatives) if negatives else None,
        "positive_evaluation_coverage": len(positive_evaluable) / len(positives) if positives else None,
        "episode_evaluations": evaluations,
    }


def select_threshold(rows, *, probability_key: str, target_fpr: float,
                     scenario_count: int, step_minutes: int = 5) -> dict:
    if not 0 <= target_fpr <= 1:
        raise ValueError("EXP1_TARGET_FPR_OUT_OF_RANGE")
    by_episode = defaultdict(list)
    for row in rows:
        by_episode[row["episode_id"]].append(row)
    evaluations = [
        evaluate_episode_rows(items, probability_key=probability_key,
                              threshold=0.0, step_minutes=step_minutes)
        for items in by_episode.values()
    ]
    negatives = [item for item in evaluations if item["realized_event_positive"] is False]
    evaluable = [item for item in negatives if item["evaluable"]]
    chosen = achieved = None
    for index in range(scenario_count + 1):
        threshold = index / scenario_count
        false_count = sum(
            item["sustained_score"] is not None
            and round(float(item["sustained_score"]) * scenario_count) >= index
            for item in evaluable
        )
        fpr = false_count / len(evaluable) if evaluable else None
        if fpr is not None and fpr <= target_fpr:
            chosen, achieved = threshold, fpr
            break
    return {
        "target_fpr": target_fpr,
        "threshold": chosen,
        "achieved_fpr": achieved,
        "negative_evaluable_n": len(evaluable),
        "fpr_step": 1 / len(evaluable) if evaluable else None,
        "operating_point_status": "PASS" if chosen is not None else "INFEASIBLE",
    }


def decision_window_gain(rows, *, adaptive_key: str = "adaptive_probability",
                         fixed_key: str = "fixed_probability",
                         adaptive_threshold: float, fixed_threshold: float) -> dict:
    by_episode = defaultdict(list)
    for row in rows:
        if row.get("material_risk") or row.get("realized_event_positive") is True:
            by_episode[row["episode_id"]].append(row)
    gains = []
    for episode_rows in by_episode.values():
        adaptive = sustained_warning_lead_time(
            episode_rows, probability_key=adaptive_key, threshold=adaptive_threshold)
        fixed = sustained_warning_lead_time(
            episode_rows, probability_key=fixed_key, threshold=fixed_threshold)
        gains.append(adaptive - fixed)
    if not gains:
        return {"DecisionWindowGain": None, "episode_denominator": 0}
    return {
        "DecisionWindowGain": sum(gains) / len(gains),
        "median": median(gains),
        "share_gt_0": sum(value > 0 for value in gains) / len(gains),
        "share_ge_15": sum(value >= 15 for value in gains) / len(gains),
        "share_ge_30": sum(value >= 30 for value in gains) / len(gains),
        "episode_denominator": len(gains),
    }


def warning_recall_at_fixed_fpr(rows, *, probability_key: str, threshold: float) -> dict[float, float]:
    by_lead = defaultdict(list)
    for row in rows:
        if row.get("material_risk") or row.get("realized_event_positive") is True:
            by_lead[float(row["lead_time_minutes"])].append(float(row[probability_key]) >= threshold)
    return {lead: sum(values) / len(values) for lead, values in sorted(by_lead.items(), reverse=True)}


def episode_false_warning_rate(rows, *, probability_key: str, threshold: float) -> float | None:
    summary = summarize_operating_point(rows, probability_key=probability_key, threshold=threshold)
    return summary["achieved_episode_fpr"]
