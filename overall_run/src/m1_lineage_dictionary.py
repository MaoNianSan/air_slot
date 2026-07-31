from __future__ import annotations

from typing import Any

import pandas as pd

from .m1_lineage_contract import BOOTSTRAP_DRAWS, FORMAL_TARGET


def metric_specs() -> list[dict[str, Any]]:
    formal = "all current formal evaluation rows"
    final = "FINAL_PUBLISHED_QUANTILES"
    common = {
        "target_field": FORMAL_TARGET,
        "split": "test",
        "current_code_file": "overall_run/src/m1.py",
        "pre_refactor_code_location": "overall_run/src/m1.py",
        "post_refactor_code_location": "overall_run/src/m1_metrics.py",
        "behavioral_equivalence": "EXACT_MATCH",
        "cohort": formal,
        "cohort_filter": "frozen Fast formal_core snapshot keys",
        "aggregation_unit": "row",
        "bootstrap_unit": "NONE",
        "bootstrap_draws": 0,
        "seed_namespace": "NONE",
        "support_definition": "number of formal evaluation snapshots",
        "formal_or_diagnostic": "FORMAL",
        "gate_role": "REPORT_ONLY",
        "prediction_layer": final,
        "threshold": None,
        "prohibited_as_primary_gate": False,
    }

    def spec(metric_id: str, value_key: str, display: str, formula: str, **updates: Any) -> dict[str, Any]:
        row = {
            **common,
            "metric_id": metric_id,
            "canonical_metric_id": metric_id,
            "value_key": value_key,
            "display_name": display,
            "scientific_purpose": updates.pop("scientific_purpose", "distributional evaluation"),
            "formula": formula,
            "formula_version": metric_id,
            "quantile_or_interval": updates.pop("quantile_or_interval", ""),
            "current_function": updates.pop("current_function", ""),
            "acceptance_threshold": updates.pop("acceptance_threshold", None),
            "reported_artifact": updates.pop(
                "reported_artifact", "overall_run/output/fast/audit/q95_audit.json"
            ),
            "historical_aliases": updates.pop("historical_aliases", ""),
        }
        row.update(updates)
        return row

    rows = [
        spec("M1_CRPS_V1", "crps", "CRPS", "mean_i 2*trapz_tau pinball(Y_i,Q_i(tau),tau)", current_function="approximate_crps"),
        spec(
            "M1_TWCRPS_V1", "twcrps", "tail-weighted CRPS",
            "weighted_mean_i(CRPS_i, 5 if Y_i>=validation_raw_label_q95 else 1)",
            current_function="_corrected_q95.metrics", quantile_or_interval="q01-q99 grid",
            threshold="validation raw-label q95", scientific_purpose="tail-emphasized proper score",
            outcome_used_in_weight=True,
        ),
        spec("M1_PINBALL_Q01_V1", "q01_pinball", "q01 pinball", "mean(max(tau*(Y-Q),(tau-1)*(Y-Q))), tau=.01", current_function="pinball_loss", quantile_or_interval="q01", reported_artifact="NOT_PUBLISHED_AGGREGATE"),
        spec("M1_PINBALL_Q05_V1", "q05_pinball", "q05 pinball", "mean(max(tau*(Y-Q),(tau-1)*(Y-Q))), tau=.05", current_function="pinball_loss", quantile_or_interval="q05", reported_artifact="NOT_PUBLISHED_AGGREGATE"),
        spec("M1_PINBALL_Q50_V1", "q50_pinball", "q50 pinball", "mean(max(tau*(Y-Q),(tau-1)*(Y-Q))), tau=.50", current_function="pinball_loss", quantile_or_interval="q50", reported_artifact="NOT_PUBLISHED_AGGREGATE"),
        spec("M1_PINBALL_Q95_V1", "q95_pinball", "q95 pinball", "mean(max(tau*(Y-Q),(tau-1)*(Y-Q))), tau=.95", current_function="pinball_loss", quantile_or_interval="q95"),
        spec("M1_PINBALL_Q99_V1", "q99_pinball", "q99 pinball", "mean(max(tau*(Y-Q),(tau-1)*(Y-Q))), tau=.99", current_function="pinball_loss", quantile_or_interval="q99"),
        spec(
            "M1_INTERVAL_COVERAGE_90_V1", "coverage90", "q05-q95 interval coverage",
            "mean(1[Q(.05)<=Y<=Q(.95)])", current_code_file="overall_run/src/pipeline.py",
            current_function="run_experiment scientific acceptance gates", quantile_or_interval="inclusive q05-q95",
            gate_role="FORMAL_GATE", acceptance_threshold="[0.85,0.95]",
            reported_artifact="overall_run/output/fast/metrics/m1_summary_evaluation.parquet",
        ),
        spec("M1_Q95_EMPIRICAL_EXCEEDANCE_V1", "q95_exceedance", "q95 empirical exceedance", "mean(1[Y>Q(.95)])", current_function="_corrected_q95", quantile_or_interval="q95", threshold=0.05, scientific_purpose="upper-quantile calibration"),
        spec("M1_Q99_EMPIRICAL_EXCEEDANCE_V1", "q99_exceedance", "q99 empirical exceedance", "mean(1[Y>Q(.99)])", current_function="_corrected_q95", quantile_or_interval="q99", threshold=0.01, scientific_purpose="extreme-quantile calibration"),
        spec("M1_Q95_EMPIRICAL_CDF_V1", "q95_empirical_cdf", "q95 empirical cumulative probability", "mean(1[Y<=Q(.95)])", current_function="_corrected_q95", quantile_or_interval="q95", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_Q99_EMPIRICAL_CDF_V1", "q99_empirical_cdf", "q99 empirical cumulative probability", "mean(1[Y<=Q(.99)])", current_function="_corrected_q95", quantile_or_interval="q99", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_Q95_CALIBRATION_SIGNED_V2", "q95_calibration_signed", "q95 signed calibration error", "mean(1[Y<=Q(.95)])-.95", current_function="_corrected_q95", quantile_or_interval="q95", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_Q99_CALIBRATION_SIGNED_V2", "q99_calibration_signed", "q99 signed calibration error", "mean(1[Y<=Q(.99)])-.99", current_function="_corrected_q95", quantile_or_interval="q99", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_Q95_CALIBRATION_ABS_V2", "q95_calibration_absolute", "q95 absolute calibration error", "abs(mean(1[Y<=Q(.95)])-.95)", current_function="_corrected_q95", quantile_or_interval="q95", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_Q99_CALIBRATION_ABS_V2", "q99_calibration_absolute", "q99 absolute calibration error", "abs(mean(1[Y<=Q(.99)])-.99)", current_function="_corrected_q95", quantile_or_interval="q99", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec(
            "M1_OUTCOME_SELECTED_TAIL_COVERAGE_V1", "tail_coverage90", "outcome-selected tail coverage",
            "mean(1[Q(.05)<=Y<=Q(.95)] | Y>training_model_frame_raw_label_q95)",
            current_code_file="overall_run/src/pipeline.py", current_function="run_experiment scientific acceptance gates",
            cohort="realized-outcome-selected stress subset", cohort_filter="formal rows AND Y>training model-frame raw-label q95",
            support_definition="number of outcome-selected tail snapshots", formal_or_diagnostic="DIAGNOSTIC_ONLY",
            gate_role="NON_BLOCKING_STRESS_DIAGNOSTIC", threshold="training model-frame raw-label q95",
            acceptance_threshold="legacy reference >=0.70; non-required", prohibited_as_primary_gate=True,
            reported_artifact="overall_run/output/fast/metrics/m1_summary_evaluation.parquet",
            scientific_purpose="stress diagnostic, not unconditional coverage",
        ),
        spec(
            "M1_UPPER_SHORTFALL_Q99_REPORT_ONLY_V1", "upper_shortfall", "q99 upper shortfall",
            "mean(max(Y-Q(.99),0))", current_function="_corrected_q95", quantile_or_interval="q99",
            gate_role="REPORT_ONLY_NO_ACCEPTED_RANGE", formal_or_diagnostic="FORMAL_DECLARATION_DIAGNOSTIC_USE",
            scientific_purpose="upper-tail stress magnitude",
        ),
        spec("M1_RAW_QUANTILE_CROSSING_ROWS_V1", "raw_crossing_rows", "raw quantile crossing rows", "sum(1[any(diff(raw_Q)<0)])", current_function="_corrected_q95", prediction_layer="RAW_MODEL_QUANTILES", gate_role="AUDIT", reported_artifact="overall_run/output/fast/audit/q95_audit.json"),
        spec("M1_RAW_QUANTILE_CROSSING_RATE_V1", "raw_crossing_rate", "raw quantile crossing rate", "mean(1[any(diff(raw_Q)<0)])", current_function="_corrected_q95", prediction_layer="RAW_MODEL_QUANTILES", gate_role="AUDIT", reported_artifact="DERIVED_FROM_FROZEN_PREDICTIONS"),
        spec("M1_PROJECTED_QUANTILE_CROSSING_ROWS_V1", "projected_crossing_rows", "projected quantile crossing rows", "sum(1[any(diff(final_Q)<0)])", current_function="_corrected_q95", gate_role="FORMAL_GATE", acceptance_threshold="0", reported_artifact="overall_run/output/fast/audit/q95_audit.json"),
        spec("M1_PROJECTED_QUANTILE_CROSSING_RATE_V1", "projected_crossing_rate", "projected quantile crossing rate", "mean(1[any(diff(final_Q)<0)])", current_code_file="overall_run/src/pipeline.py", current_function="run_experiment scientific acceptance gates", gate_role="FORMAL_GATE", acceptance_threshold="0", reported_artifact="overall_run/output/fast/metrics/m1_summary_evaluation.parquet"),
        spec("M1_EXCEEDANCE_BRIER_15_V1", "brier15", "15-minute exceedance Brier score", "mean((P(Y>15)-1[Y>15])^2)", current_code_file="overall_run/src/metric.py", current_function="m1_metric_table", scientific_purpose="probability calibration", threshold=15.0, reported_artifact="IMPLEMENTED_NOT_PUBLISHED_CURRENT_FAST"),
        spec("M1_TRIGGER_RATE_V1", "trigger_rate", "M1 trigger rate", "mean(1[p_exceed_15>.5 OR finite(p_window) AND p_window>.5])", current_code_file="overall_run/src/pipeline.py", current_function="_trigger", scientific_purpose="operational trigger prevalence", threshold="strict >0.5", gate_role="OPERATIONAL_INTERMEDIATE", reported_artifact="metrics/m1_predictions_evaluation.parquet:trigger"),
        spec("M1_TWCRPS_PROP_MINUS_HIST_V1", "twcrps_prop_minus_hist", "twCRPS PROP-HIST delta", "weighted_mean(CRPS_PROP-CRPS_HIST, tail weights)", current_function="_event_bootstrap", scientific_purpose="comparative proper score; negative favors PROP", bootstrap_unit="trigger_event_group_id", bootstrap_draws=BOOTSTRAP_DRAWS, seed_namespace="CORRECTED_Q95_FAST_SUPPORT_AUDIT:20260725", threshold=0.0),
        spec("M1_PINBALL_Q95_PROP_MINUS_HIST_V1", "q95_pinball_prop_minus_hist", "q95 pinball PROP-HIST delta", "mean(pinball_PROP(.95)-pinball_HIST(.95))", current_function="_event_bootstrap", scientific_purpose="comparative proper score; negative favors PROP", bootstrap_unit="trigger_event_group_id", bootstrap_draws=BOOTSTRAP_DRAWS, seed_namespace="CORRECTED_Q95_FAST_SUPPORT_AUDIT:20260725", threshold=0.0),
        spec("M1_PINBALL_Q99_PROP_MINUS_HIST_V1", "q99_pinball_prop_minus_hist", "q99 pinball PROP-HIST delta", "mean(pinball_PROP(.99)-pinball_HIST(.99))", current_function="_event_bootstrap", scientific_purpose="comparative proper score; negative favors PROP", bootstrap_unit="trigger_event_group_id", bootstrap_draws=BOOTSTRAP_DRAWS, seed_namespace="CORRECTED_Q95_FAST_SUPPORT_AUDIT:20260725", threshold=0.0),
    ]
    for row in rows:
        row.setdefault("outcome_used_in_weight", False)
        pre_location = row["current_code_file"]
        row["pre_refactor_code_location"] = pre_location
        if row["value_key"] == "trigger_rate":
            post_location = "overall_run/src/pipeline_data.py"
        elif pre_location == "overall_run/src/pipeline.py":
            post_location = "overall_run/src/pipeline_finalize.py"
        elif pre_location == "overall_run/src/m1.py":
            post_location = "overall_run/src/m1_metrics.py"
        else:
            post_location = pre_location
        if row["current_function"] in {"_corrected_q95", "_event_bootstrap"}:
            row["pre_refactor_code_location"] = "corrected_fast_post_rebuild_audit.py"
            post_location = "overall_run/src/m1_lineage_reconstruction.py"
        row["post_refactor_code_location"] = post_location
        row["current_code_file"] = post_location
        row["behavioral_equivalence"] = "EXACT_MATCH"
    return rows


def build_metric_dictionary() -> pd.DataFrame:
    frame = pd.DataFrame(metric_specs())
    for column in ("threshold", "acceptance_threshold"):
        frame[column] = frame[column].map(
            lambda value: None if value is None or pd.isna(value) else str(value)
        )
    ordered = [
        "metric_id", "canonical_metric_id", "display_name", "scientific_purpose",
        "formal_or_diagnostic", "current_code_file", "pre_refactor_code_location",
        "post_refactor_code_location", "behavioral_equivalence", "current_function", "formula",
        "formula_version", "prediction_layer", "target_field", "quantile_or_interval",
        "cohort", "cohort_filter", "split", "aggregation_unit", "bootstrap_unit",
        "bootstrap_draws", "seed_namespace", "support_definition", "threshold",
        "acceptance_threshold", "gate_role", "prohibited_as_primary_gate",
        "reported_artifact", "historical_aliases", "outcome_used_in_weight", "value_key",
    ]
    return frame[ordered]


def build_prediction_layer_mapping() -> pd.DataFrame:
    rows = [
        {
            "layer": "RAW_MODEL_QUANTILES",
            "input_artifact": "m1.joblib LightGBM quantile models",
            "persisted_columns": "raw_q_* in metrics/m1_predictions_evaluation.parquet",
            "calibration_level": "NONE",
            "calibration_fallback": "NONE",
            "projection_order": "before calibration and projection",
            "clipping": False,
            "crossing_handling": "not handled; audited directly",
            "consumers": "raw crossing audit",
        },
        {
            "layer": "CALIBRATED_QUANTILES",
            "input_artifact": "RAW_MODEL_QUANTILES + validation residual offsets",
            "persisted_columns": "TRANSIENT_NOT_PERSISTED",
            "calibration_level": "airport_stage -> stage -> global",
            "calibration_fallback": "global",
            "projection_order": "calibration offsets applied before isotonic projection",
            "clipping": False,
            "crossing_handling": "may still cross before projection",
            "consumers": "input to monotone_quantiles only",
        },
        {
            "layer": "MONOTONICITY_PROJECTED_QUANTILES",
            "input_artifact": "transient calibrated quantiles",
            "persisted_columns": "q_* in metrics/m1_predictions_evaluation.parquet",
            "calibration_level": "row-specific persisted calibration_level",
            "calibration_fallback": "global",
            "projection_order": "isotonic regression after calibration",
            "clipping": False,
            "crossing_handling": "row-wise isotonic projection",
            "consumers": "same numerical layer as FINAL_PUBLISHED_QUANTILES",
        },
        {
            "layer": "FINAL_PUBLISHED_QUANTILES",
            "input_artifact": "MONOTONICITY_PROJECTED_QUANTILES",
            "persisted_columns": "q_* in metrics/m1_predictions_evaluation.parquet",
            "calibration_level": "airport_stage -> stage -> global",
            "calibration_fallback": "global",
            "projection_order": "after calibration",
            "clipping": False,
            "crossing_handling": "projected crossings required to be zero",
            "consumers": "coverage, pinball, CRPS, twCRPS, q95/q99, Brier, trigger, M2 samples",
        },
        {
            "layer": "PREDICTIVE_SAMPLES_FROM_FINAL",
            "input_artifact": "FINAL_PUBLISHED_QUANTILES",
            "persisted_columns": "m1_predictive_samples/part.parquet",
            "calibration_level": "inherited from final quantiles",
            "calibration_fallback": "inherited",
            "projection_order": "inverse interpolation after projection",
            "clipping": True,
            "crossing_handling": "input already monotone",
            "consumers": "M2 reconstruction; uniform draws outside q01-q99 clamp to endpoint values",
        },
    ]
    return pd.DataFrame(rows)


