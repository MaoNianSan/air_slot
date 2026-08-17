"""Episode-level evaluation for the Exp1 Development warning protocol."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import statistics

import pyarrow.parquet as pq

from exp.exp1.metrics import episode_operating_point, scenario_grid_probability


TARGET_FPRS = (0.05, 0.10, 0.20)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _variant_files(output_root: Path, mode: str, variant: str) -> list[Path]:
    return sorted((output_root / mode).glob(f"month=*/{variant}/part-*.parquet"))


def _episodes_from_file(
    path: Path,
    *,
    scenarios: int,
    episode_ids: set[str] | None = None,
):
    data = pq.read_table(path).to_pydict()
    current_id = None
    rows = []
    for index, episode_id in enumerate(data["episode_id"]):
        if episode_id != current_id:
            if rows:
                yield rows
            rows = []
            current_id = episode_id
        if episode_ids is not None and episode_id not in episode_ids:
            continue
        row = {name: values[index] for name, values in data.items()}
        probability = row.get("warning_probability")
        if probability is not None:
            row["warning_probability"] = scenario_grid_probability(
                probability,
                scenarios,
            )
        rows.append(row)
    if rows:
        yield rows


def _thresholds_for_variant(
    files: list[Path],
    *,
    scenarios: int,
) -> tuple[dict, dict]:
    negative_histogram = [0] * (scenarios + 1)
    counts = defaultdict(int)
    tail_nodes = tail_episodes = nodes = 0
    for path in files:
        for rows in _episodes_from_file(path, scenarios=scenarios):
            realized = rows[0]["realized_event_positive"]
            evaluation = episode_operating_point(
                rows,
                probability_key="warning_probability",
                threshold=0.0,
            )
            label = (
                "positive"
                if realized is True
                else "negative"
                if realized is False
                else "unknown"
            )
            counts[f"{label}_total"] += 1
            if evaluation["evaluable"]:
                counts[f"{label}_evaluable"] += 1
                if label == "negative":
                    index = int(round(float(evaluation["sustained_score"]) * scenarios))
                    negative_histogram[max(0, min(index, scenarios))] += 1
            else:
                counts[f"{label}_abstain"] += 1
            episode_tail = any(row["tail_representative_used"] for row in rows)
            tail_episodes += int(episode_tail)
            tail_nodes += sum(row["tail_representative_used"] for row in rows)
            nodes += len(rows)

    suffix = [0] * (scenarios + 1)
    running = 0
    for index in range(scenarios, -1, -1):
        running += negative_histogram[index]
        suffix[index] = running

    thresholds = {}
    denominator = counts["negative_evaluable"]
    for target in TARGET_FPRS:
        selected = None
        for index in range(scenarios + 1):
            fpr = suffix[index] / denominator if denominator else None
            if fpr is not None and fpr <= target:
                selected = {
                    "target_fpr": target,
                    "threshold": index / scenarios,
                    "achieved_fpr": fpr,
                    "negative_evaluable_n": denominator,
                    "fpr_step": 1 / denominator,
                    "operating_point_status": "PASS",
                }
                break
        thresholds[str(target)] = selected or {
            "target_fpr": target,
            "threshold": None,
            "achieved_fpr": None,
            "negative_evaluable_n": denominator,
            "fpr_step": 1 / denominator if denominator else None,
            "operating_point_status": "INFEASIBLE",
        }

    coverage = {
        **counts,
        "negative_evaluation_coverage": (
            counts["negative_evaluable"] / counts["negative_total"]
            if counts["negative_total"]
            else None
        ),
        "positive_evaluation_coverage": (
            counts["positive_evaluable"] / counts["positive_total"]
            if counts["positive_total"]
            else None
        ),
        "tail_representative_node_rate": tail_nodes / nodes if nodes else None,
        "tail_representative_episode_rate": tail_episodes
        / (counts["negative_total"] + counts["positive_total"] + counts["unknown_total"]),
    }
    return thresholds, coverage


def _metrics_for_variant(
    files: list[Path],
    *,
    threshold: float,
    scenarios: int,
    episode_ids: set[str] | None = None,
    collect_diagnostics: bool = False,
) -> tuple[dict, dict[str, float], dict[str, dict], dict[tuple[str, str], tuple]]:
    counts = defaultdict(int)
    sustained_leads = []
    per_positive_lead = {}
    episode_status = {}
    node_records = {}
    for path in files:
        for rows in _episodes_from_file(
            path,
            scenarios=scenarios,
            episode_ids=episode_ids,
        ):
            episode_id = rows[0]["episode_id"]
            realized = rows[0]["realized_event_positive"]
            evaluation = episode_operating_point(
                rows,
                probability_key="warning_probability",
                threshold=threshold,
            )
            if collect_diagnostics:
                episode_status[episode_id] = {
                    "evaluable": bool(evaluation["evaluable"]),
                    "sustained_warning": bool(evaluation["sustained_warning"]),
                    "realized_event_positive": realized,
                }
                for row in rows:
                    node_records[(episode_id, row["decision_node_id"])] = (
                        row.get("warning_probability"),
                        row.get("warning_support_state"),
                    )
            if realized is False and evaluation["evaluable"]:
                counts["negative_evaluable"] += 1
                counts["false_warning"] += int(evaluation["sustained_warning"])
            if realized is True and evaluation["evaluable"]:
                counts["positive_evaluable"] += 1
                counts["any_warning"] += int(evaluation["any_warning"])
                counts["sustained_warning"] += int(evaluation["sustained_warning"])
                lead = evaluation["sustained_warning_lead_minutes"]
                per_positive_lead[episode_id] = 0.0 if lead is None else float(lead)
                if lead is not None:
                    sustained_leads.append(float(lead))

    ordered = sorted(sustained_leads)
    q1 = ordered[int((len(ordered) - 1) * 0.25)] if ordered else None
    q3 = ordered[int((len(ordered) - 1) * 0.75)] if ordered else None
    metrics = {
        "threshold": threshold,
        "achieved_episode_fpr": (
            counts["false_warning"] / counts["negative_evaluable"]
            if counts["negative_evaluable"]
            else None
        ),
        "episode_recall": (
            counts["any_warning"] / counts["positive_evaluable"]
            if counts["positive_evaluable"]
            else None
        ),
        "sustained_warning_recall": (
            counts["sustained_warning"] / counts["positive_evaluable"]
            if counts["positive_evaluable"]
            else None
        ),
        "median_risk_lead_minutes": statistics.median(ordered) if ordered else None,
        "iqr_risk_lead_minutes": q3 - q1 if ordered else None,
        "p_risk_lead_gt_0": (
            sum(value > 0 for value in ordered) / len(ordered) if ordered else None
        ),
        "p_risk_lead_ge_15": (
            sum(value >= 15 for value in ordered) / len(ordered) if ordered else None
        ),
        "p_risk_lead_ge_30": (
            sum(value >= 30 for value in ordered) / len(ordered) if ordered else None
        ),
        "false_warning_episode_count": counts["false_warning"],
        "negative_denominator": counts["negative_evaluable"],
        "positive_denominator": counts["positive_evaluable"],
    }
    return metrics, per_positive_lead, episode_status, node_records


def _decision_window_gain(adaptive: dict[str, float], fixed: dict[str, float]) -> dict:
    paired = sorted(set(adaptive) & set(fixed))
    gains = [adaptive[item] - fixed[item] for item in paired]
    return {
        "DecisionWindowGain": sum(gains) / len(gains) if gains else None,
        "median": statistics.median(gains) if gains else None,
        "share_gt_0": sum(value > 0 for value in gains) / len(gains) if gains else None,
        "share_ge_15": (
            sum(value >= 15 for value in gains) / len(gains) if gains else None
        ),
        "share_ge_30": (
            sum(value >= 30 for value in gains) / len(gains) if gains else None
        ),
        "episode_denominator": len(gains),
    }


def _paired_node_diagnostics(
    principal_nodes: dict[tuple[str, str], tuple],
    sensitivity_nodes: dict[tuple[str, str], tuple],
    *,
    threshold: float,
) -> dict:
    common = sorted(set(principal_nodes) & set(sensitivity_nodes))
    probability_differences = []
    warning_disagreements = 0
    support_disagreements = 0
    for key in common:
        principal_probability, principal_support = principal_nodes[key]
        sensitivity_probability, sensitivity_support = sensitivity_nodes[key]
        support_disagreements += int(principal_support != sensitivity_support)
        if (
            principal_support != "SUPPORTED"
            or sensitivity_support != "SUPPORTED"
            or principal_probability is None
            or sensitivity_probability is None
        ):
            continue
        probability_differences.append(
            abs(float(sensitivity_probability) - float(principal_probability))
        )
        warning_disagreements += int(
            (float(principal_probability) >= threshold)
            != (float(sensitivity_probability) >= threshold)
        )
    denominator = len(probability_differences)
    return {
        "common_node_count": len(common),
        "supported_probability_pair_count": denominator,
        "support_state_disagreement_count": support_disagreements,
        "mean_absolute_probability_change": (
            sum(probability_differences) / denominator if denominator else None
        ),
        "max_absolute_probability_change": (
            max(probability_differences) if probability_differences else None
        ),
        "node_warning_classification_disagreement_count": warning_disagreements,
        "node_warning_classification_disagreement_rate": (
            warning_disagreements / denominator if denominator else None
        ),
    }


def _paired_episode_diagnostics(
    principal_status: dict[str, dict],
    sensitivity_status: dict[str, dict],
) -> dict:
    common = sorted(set(principal_status) & set(sensitivity_status))
    evaluable_pairs = 0
    sustained_disagreements = 0
    evaluability_disagreements = 0
    label_disagreements = 0
    for episode_id in common:
        principal = principal_status[episode_id]
        sensitivity = sensitivity_status[episode_id]
        evaluability_disagreements += int(
            principal["evaluable"] != sensitivity["evaluable"]
        )
        label_disagreements += int(
            principal["realized_event_positive"]
            != sensitivity["realized_event_positive"]
        )
        if principal["evaluable"] and sensitivity["evaluable"]:
            evaluable_pairs += 1
            sustained_disagreements += int(
                principal["sustained_warning"] != sensitivity["sustained_warning"]
            )
    return {
        "common_episode_count": len(common),
        "common_evaluable_episode_count": evaluable_pairs,
        "evaluability_disagreement_count": evaluability_disagreements,
        "realized_label_disagreement_count": label_disagreements,
        "sustained_warning_classification_disagreement_count": sustained_disagreements,
        "sustained_warning_classification_disagreement_rate": (
            sustained_disagreements / evaluable_pairs if evaluable_pairs else None
        ),
    }


def _episode_ids(files: list[Path]) -> set[str]:
    result = set()
    for path in files:
        result.update(
            pq.read_table(path, columns=["episode_id"]).column(0).to_pylist()
        )
    return result


def evaluate_principal(
    output_root: Path,
    bundle: dict,
    *,
    scenarios: int,
) -> dict:
    thresholds, coverage, metrics, leads = {}, {}, {}, {}
    for variant in bundle["artifacts"]:
        files = _variant_files(output_root, "principal_s250", variant)
        thresholds[variant], coverage[variant] = _thresholds_for_variant(
            files,
            scenarios=scenarios,
        )
        theta10 = thresholds[variant]["0.1"]["threshold"]
        if theta10 is None:
            raise RuntimeError(f"EXP1_WARNING_OPERATING_POINT_INFEASIBLE:{variant}")
        metrics[variant], leads[variant], _, _ = _metrics_for_variant(
            files,
            threshold=theta10,
            scenarios=scenarios,
        )

    decision_window_gain = _decision_window_gain(
        leads["ADAPTIVE_HISTORY"],
        leads["FIXED_HISTORY"],
    )
    payload = {
        "schema_version": "EXP1_DEVELOPMENT_WARNING_EVIDENCE_V1",
        "status": "PASS",
        "scenario_count": scenarios,
        "thresholds": thresholds,
        "coverage": coverage,
        "metrics": metrics,
        "decision_window_gain": decision_window_gain,
        "artifact_bundle_hash": bundle["manifest_hash"],
        "probability_grid": f"EXACT_EXCEEDANCE_COUNT_OVER_{scenarios}",
        "final_test_access_count": 0,
        "paper_result": False,
    }
    _write_json(output_root / "principal_s250" / "evidence.json", payload)
    return payload


def evaluate_sensitivity(
    output_root: Path,
    principal: dict,
    *,
    scenarios: int,
    subset: bool,
    subset_modulus: int,
) -> dict:
    results = {}
    mode = "sensitivity_s500"
    principal_scenarios = int(principal["scenario_count"])
    subset_ids = _episode_ids(_variant_files(output_root, mode, "CURRENT"))
    principal_leads = {}
    sensitivity_leads = {}
    for variant in principal["metrics"]:
        theta = principal["thresholds"][variant]["0.1"]["threshold"]
        principal_metrics, principal_leads[variant], principal_status, principal_nodes = (
            _metrics_for_variant(
                _variant_files(output_root, "principal_s250", variant),
                threshold=theta,
                scenarios=principal_scenarios,
                episode_ids=subset_ids,
                collect_diagnostics=True,
            )
        )
        sensitivity_metrics, sensitivity_leads[variant], sensitivity_status, sensitivity_nodes = (
            _metrics_for_variant(
            _variant_files(output_root, mode, variant),
            threshold=theta,
            scenarios=scenarios,
                collect_diagnostics=True,
            )
        )
        results[variant] = {
            "frozen_principal_threshold": theta,
            "s250_subset_metrics": principal_metrics,
            "s500_metrics": sensitivity_metrics,
            "achieved_fpr_absolute_change": (
                abs(
                    sensitivity_metrics["achieved_episode_fpr"]
                    - principal_metrics["achieved_episode_fpr"]
                )
                if sensitivity_metrics["achieved_episode_fpr"] is not None
                and principal_metrics["achieved_episode_fpr"] is not None
                else None
            ),
            "probability_and_node_classification_change": _paired_node_diagnostics(
                principal_nodes,
                sensitivity_nodes,
                threshold=theta,
            ),
            "episode_classification_change": _paired_episode_diagnostics(
                principal_status,
                sensitivity_status,
            ),
        }

    principal_gain = _decision_window_gain(
        principal_leads["ADAPTIVE_HISTORY"],
        principal_leads["FIXED_HISTORY"],
    )
    sensitivity_gain = _decision_window_gain(
        sensitivity_leads["ADAPTIVE_HISTORY"],
        sensitivity_leads["FIXED_HISTORY"],
    )
    gain_change = {
        name: (
            sensitivity_gain[name] - principal_gain[name]
            if sensitivity_gain[name] is not None and principal_gain[name] is not None
            else None
        )
        for name in ("DecisionWindowGain", "median", "share_gt_0", "share_ge_15", "share_ge_30")
    }
    payload = {
        "schema_version": "EXP1_WARNING_S500_SENSITIVITY_V2",
        "status": "PASS",
        "comparison_basis": "PAIRED_S250_S500_ON_IDENTICAL_DETERMINISTIC_SUBSET",
        "principal_scenario_count": principal_scenarios,
        "scenario_count": scenarios,
        "subset": subset,
        "subset_rule": (
            None if not subset else f"SHA256_EPISODE_ID_MOD_{subset_modulus}_EQ_0"
        ),
        "subset_episode_count": len(subset_ids),
        "principal_threshold_reselected": False,
        "probability_grids": {
            "principal": f"EXACT_EXCEEDANCE_COUNT_OVER_{principal_scenarios}",
            "sensitivity": f"EXACT_EXCEEDANCE_COUNT_OVER_{scenarios}",
        },
        "results": results,
        "decision_window_gain": {
            "s250_subset": principal_gain,
            "s500_subset": sensitivity_gain,
            "s500_minus_s250": gain_change,
        },
        "materiality_assessment": {
            "status": "NOT_PRE_REGISTERED",
            "binary_material_change_claim": None,
            "reason": "NO_FROZEN_MATERIALITY_THRESHOLD",
        },
        "final_test_access_count": 0,
    }
    _write_json(output_root / mode / "sensitivity.json", payload)
    return payload
