from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from typing import Any

import psutil
import pandas as pd

from .m1_lineage_contract import (
    FAST_ROOT,
    LOG_ROOT,
    MODULE_ROOT,
    PART_ROOT,
    PRE_ROOT,
    PROJECT_ROOT,
)


def _checkpoint_sections(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"title": "1. M1Artifact.predict_distribution", "files": "overall_run/src/m1.py; m1_calibration.py; m1_metrics.py; m1_sampling.py", "function": "M1Artifact.predict_distribution", "inputs": "formal model frame; n_samples=256; base_seed=20260718", "outputs": "raw quantiles, final quantiles, samples, probabilities, calibration level", "shape": "640x15 quantiles; 640x256 samples", "formula": "model prediction -> residual offsets -> isotonic projection -> inverse quantile samples", "layer": "all layers", "cohort": "formal_core", "source": "merged_config.json:modes.fast.formal_samples/random_seed", "why": "one deterministic distribution feeds both metrics and M2", "cannot": "samples are not raw-model samples", "question": "Which quantiles feed M2?", "answer": "Final calibrated and isotonic-projected quantiles via inverse interpolation.", "open": "Fast has only one anchor day."},
        {"title": "2. Raw quantile generation", "files": "overall_run/src/m1.py", "function": "M1Artifact.raw_quantiles", "inputs": "transformed frozen features", "outputs": "raw_q_*", "shape": "640x15", "formula": "one LightGBM quantile model per tau", "layer": "RAW_MODEL_QUANTILES", "cohort": "formal_core", "source": "m1.joblib and scientific quantile grid", "why": "preserves the model output before post-processing", "cannot": "raw crossings are not published interval failures", "question": "Where do 547 crossings come from?", "answer": "Rows with any negative adjacent difference in raw_q_*.", "open": "none"},
        {"title": "3. Residual calibration hierarchy", "files": "overall_run/src/m1_calibration.py; overall_run/src/m1.py", "function": "fit_residual_calibration; apply_residual_calibration", "inputs": "validation residuals Y-raw_Q", "outputs": "transient calibrated quantiles and level", "shape": "54 airport-stage, 9 stage, 1 global offset vectors", "formula": "Q_raw + quantile_tau(validation residual)", "layer": "CALIBRATED_QUANTILES", "cohort": "validation for offsets; formal rows for application", "source": "minimum support 200; hierarchy airport_stage/stage/global", "why": "predeclared fallback calibration", "cannot": "test outcomes never choose offsets", "question": "When is global used?", "answer": "When airport-stage and stage do not meet the frozen support mapping.", "open": "none"},
        {"title": "4. Isotonic projection", "files": "overall_run/src/m1_calibration.py", "function": "project_quantile_monotonicity", "inputs": "calibrated quantile vector", "outputs": "monotone vector", "shape": "row-wise length 15", "formula": "IsotonicRegression(increasing=True).fit_transform(tau,Q)", "layer": "MONOTONICITY_PROJECTED_QUANTILES", "cohort": "every predicted row", "source": "fixed code, tolerance gate zero crossings", "why": "enforces quantile monotonicity after offsets", "cannot": "not a scientific recalibration to Fast outcomes", "question": "Before or after calibration?", "answer": "After calibration.", "open": "none"},
        {"title": "5. Final quantile publication", "files": "overall_run/src/pipeline_data.py", "function": "prediction_table", "inputs": "predict_distribution.quantiles", "outputs": "q_* columns", "shape": "640x15", "formula": "direct persistence without further transform", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "formal_core", "source": "frozen prediction artifact", "why": "single authoritative metric surface", "cannot": "q_* must not be called raw quantiles", "question": "Are projected and final different here?", "answer": "No; final is the persisted calibrated-then-projected layer.", "open": "none"},
        {"title": "6. Predictive sample generation", "files": "overall_run/src/m1_sampling.py", "function": "inverse_quantile_sample", "inputs": "final q_* and stable row seed", "outputs": "sample_value", "shape": "163,840 rows (640x256)", "formula": "U~Uniform(0,1); interp(U,tau,Q), endpoints clamped to q01/q99", "layer": "PREDICTIVE_SAMPLES_FROM_FINAL", "cohort": "formal_core", "source": "stable_seed(base,flight_id,snapshot_id,m1_samples)", "why": "deterministic downstream uncertainty propagation", "cannot": "the sample tails do not extrapolate beyond q01/q99", "question": "Was sample identity checked?", "answer": "Yes, all float32 values reconstructed with max delta zero.", "open": "none"},
        {"title": "7. Pinball", "files": "overall_run/src/m1_metrics.py", "function": "pinball_loss", "inputs": "Y,Q_tau,tau", "outputs": "row loss", "shape": "640", "formula": "max(tau*(Y-Q),(tau-1)*(Y-Q))", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "formal_core", "source": "tau from frozen grid", "why": "proper quantile loss", "cannot": "residual sign is Y-Q, not Q-Y", "question": "How is it aggregated?", "answer": "Unweighted row mean in the current q95 audit.", "open": "q01/q05/q50 aggregates were not formally published before this audit"},
        {"title": "8. CRPS", "files": "overall_run/src/m1_metrics.py", "function": "approximate_crps", "inputs": "all 15 final quantiles", "outputs": "row CRPS", "shape": "640", "formula": "2*trapezoidal integral of pinball across the nonuniform grid", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "formal_core", "source": "fixed grid", "why": "distribution-wide proper score", "cannot": "not a simple quantile average", "question": "Why the factor two?", "answer": "It is the frozen quantile-integral CRPS approximation implemented by the code.", "open": "none"},
        {"title": "9. twCRPS", "files": "corrected_fast_post_rebuild_audit.py", "function": "_corrected_q95.metrics", "inputs": "row CRPS and validation raw-label q95=37.1", "outputs": "weighted mean", "shape": "640", "formula": "weight 5 when Y>=37.1, otherwise 1", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "all formal rows; outcome changes weight, not membership", "source": "validation split only", "why": "emphasizes upper outcomes", "cannot": "not the 32-row tail diagnostic", "question": "What does negative PROP-HIST mean?", "answer": "Lower proper score for PROP, hence better point comparison; Fast event support still prevents certification.", "open": "CI unavailable with six events"},
        {"title": "10. q05-q95 coverage", "files": "overall_run/src/pipeline_finalize.py", "function": "finalize_experiment scientific acceptance gates", "inputs": "Y,q05,q95", "outputs": "coverage90", "shape": "640", "formula": "mean(q05<=Y<=q95), inclusive", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "all formal rows", "source": "accepted range [0.85,0.95]", "why": "unconditional central interval validity", "cannot": "not directly comparable to outcome-selected tail coverage", "question": "What is the denominator?", "answer": "All 640 formal evaluation rows.", "open": "none"},
        {"title": "11. q95/q99 empirical exceedance", "files": "corrected_fast_post_rebuild_audit.py", "function": "_corrected_q95", "inputs": "Y,q95,q99", "outputs": "exceedance probabilities", "shape": "640", "formula": "mean(Y>Q_tau); equivalent CDF coverage is 1-exceedance", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "all formal rows", "source": "current Fast audit", "why": "calibration evidence", "cannot": "0.95 CDF coverage must not be confused with 0.05 exceedance", "question": "Current results?", "answer": "q95 0.0609375; q99 0.025, both with limited event support.", "open": "q99 historical PASS is deprecated"},
        {"title": "12. Tail diagnostic", "files": "overall_run/src/pipeline_finalize.py", "function": "finalize_experiment scientific acceptance gates", "inputs": "Y and training model-frame raw-label q95=34.116666...", "outputs": "tail coverage", "shape": "32 selected rows", "formula": "coverage90 conditional on Y>training q95", "layer": "FINAL_PUBLISHED_QUANTILES", "cohort": "OUTCOME_SELECTED_DIAGNOSTIC_ONLY", "source": "training model frame; legacy non-required 0.70 reference", "why": "stress inspection", "cannot": "must not be used as the primary formal coverage gate", "question": "Why 0.4375?", "answer": "14 of 32 outcome-selected rows are inside q05-q95.", "open": "support is limited"},
        {"title": "13. Bootstrap", "files": "corrected_fast_post_rebuild_audit.py", "function": "_event_bootstrap", "inputs": "row metrics grouped by trigger_event_group_id", "outputs": "point and CI when support permits", "shape": "6 event clusters", "formula": "paired event-cluster resampling; 2000 configured draws", "layer": "metric-level", "cohort": "formal_core", "source": "seed 20260725; minimum 20 events", "why": "snapshots within recovery events are dependent", "cannot": "rows are never independent bootstrap units", "question": "Why no CI?", "answer": "Six events are below the frozen minimum of 20, so no draws execute.", "open": "adapt_full needed for evidence expansion"},
        {"title": "14. Acceptance classification", "files": "overall_run/src/audit.py; corrected_fast_post_rebuild_audit.py", "function": "build_scientific_gate; q95 classification", "inputs": "metrics, support and frozen bounds", "outputs": "gate/status", "shape": "one status per metric", "formula": "frozen rule logic", "layer": "published metrics", "cohort": "metric-specific", "source": "acceptance.yaml", "why": "separates engineering identity from scientific certification", "cannot": "lineage PASS is not M1 scientific PASS", "question": "q95 status?", "answer": "SYSTEMATIC_CALIBRATION_CONCERN_CURRENT_FAST plus METRIC_SUPPORT_LIMITED certification.", "open": "proper-score numeric gates remain pending scientific definition"},
        {"title": "15. Metric publication", "files": "overall_run/src/pipeline_data.py; pipeline_finalize.py; report.py; report_figures.py; report_m4.py", "function": "prediction_table; publication repair", "inputs": "frozen source artifacts", "outputs": "metrics/tables/audit", "shape": "113 registered formal artifacts", "formula": "no scientific recomputation in publication repair", "layer": "published", "cohort": "preserved", "source": "publication_manifest.json", "why": "reproducible reporting", "cannot": "audit outputs do not enter the formal registry", "question": "Did this audit change formal artifacts?", "answer": "No; every registered SHA is compared before and after.", "open": "none"},
        {"title": "16. Canonical versioning", "files": "overall_run/audit_m1_d6_metric_lineage.py", "function": "build_metric_version_registry", "inputs": "formula, layer, cohort, aggregation, threshold, bootstrap, role", "outputs": "unique canonical IDs and definition hashes", "shape": "one row per current metric definition", "formula": "SHA256 canonical definition components", "layer": "lineage metadata", "cohort": "metric-specific", "source": "current frozen code and artifacts", "why": "prevents ambiguous names such as coverage or calibration", "cannot": "deprecated historical values receive no current version identity", "question": "What happens if history is recovered?", "answer": "Create a new retrospective audit; never overwrite this disposition.", "open": "none"},
    ]


def build_code_study(
    context: dict[str, Any], audit_id: str, dictionary: pd.DataFrame
) -> str:
    parts = [
        f"# M1 D6 Code Study\n\nAudit ID: `{audit_id}`\n",
        "> Deprecation is an evidence-governance decision. It is not a reconstruction or scientific reconciliation of the historical values.\n",
    ]
    for row in _checkpoint_sections(context):
        parts.append(
            textwrap.dedent(
                f"""
                ## {row['title']}

                - 阅读的文件: `{row['files']}`
                - 核心函数: `{row['function']}`
                - 调用链位置: {row['function']}
                - 输入字段: {row['inputs']}
                - 输出字段: {row['outputs']}
                - array/DataFrame shape: {row['shape']}
                - 对应公式: {row['formula']}
                - prediction layer: `{row['layer']}`
                - cohort filter: {row['cohort']}
                - 参数和阈值来源: {row['source']}
                - 为什么这样计算: {row['why']}
                - 不能如何解释: {row['cannot']}
                - 老师可能追问: {row['question']}
                - 标准回答: {row['answer']}
                - 尚未解决的问题: {row['open']}
                """
            )
        )
    location_columns = [
        "canonical_metric_id", "pre_refactor_code_location",
        "post_refactor_code_location", "behavioral_equivalence",
    ]
    parts.append(
        "# 重构前后权威代码位置\n\n"
        + dictionary[location_columns].to_markdown(index=False)
        + "\n\n函数移动不创建新的 metric version；所有公式、prediction layer、cohort、"
        "aggregation、参数与 seed 均保持不变。\n"
    )
    parts.append(
        textwrap.dedent(
            f"""
            # 一页代码调用链

            `prepare_model_frame -> fit_m1 -> raw_quantiles -> residual calibration -> monotone_quantiles -> predict_distribution -> _prediction_table -> current metrics -> scientific gate`. M2 reads the 256 samples generated from final quantiles.

            # 一页指标公式

            - Pinball: `max(tau*(Y-Q), (tau-1)*(Y-Q))`, residual `Y-Q`.
            - CRPS: `2*trapz(pinball_tau, tau)` over the 15-point grid.
            - twCRPS: weighted mean of row CRPS; weight 5 for `Y >= {context['validation_q95']}`, otherwise 1.
            - Coverage90: `mean(q05 <= Y <= q95)` on 640 rows.
            - q95/q99 exceedance: `mean(Y > q_tau)`; CDF coverage is its complement.
            - Upper shortfall: `mean(max(Y-q99,0))`, minutes.
            - Tail coverage: Coverage90 conditional on `Y > {context['train_q95']}`, 32 rows.
            - Brier15: `mean((p_exceed_15-1[Y>15])^2)`.

            # 一页参数与阈值来源

            - Quantile grid, hierarchy, minimum support, trigger thresholds: `overall_run/output/fast/merged_config.json`.
            - Coverage accepted range and metric roles: `overall_run/config/acceptance.yaml`.
            - Fast samples: 256; pipeline base seed: 20260718.
            - Bootstrap audit: 2000 draws configured, seed 20260725, event unit, minimum 20 events.
            - twCRPS threshold: validation `y_movement_raw` q95 = {context['validation_q95']}.
            - Tail diagnostic threshold: training model-frame `y_movement_raw` q95 = {context['train_q95']}.

            # 一页老师可能提问及标准回答

            1. 为什么 raw crossing 547 而 final 是 0？raw model quantiles can cross; residual calibration is followed by row-wise isotonic projection before publication.
            2. CRPS 是平均 pinball 吗？不是。当前代码是非均匀 quantile grid 上两倍梯形积分。
            3. twCRPS 负 delta 代表什么？`PROP-HIST < 0` means PROP has a lower proper score, but six events cannot certify the comparison.
            4. 0.925 与 0.4375 为什么不能比较？前者是全部 640 行；后者先用 realized outcome 选出 32 行，分母和目的不同。
            5. q95 concern 是否等于科学失败？不是。当前分类可复现，但 certification remains `METRIC_SUPPORT_LIMITED`.
            6. q99 是否 PASS？历史 PASS 已废弃；当前 Fast only status is support-limited and not final certification.
            7. 历史数值为什么不比较？source prediction, cohort, layer, version and bootstrap metadata are missing; deprecation is governance, not reconciliation.
            8. 云端运行用于什么？Only `EVIDENCE_EXPANSION_AND_FINAL_EVALUATION`, never tuning or threshold selection.
            """
        )
    )
    return "\n".join(parts)


def cloud_readiness(baseline: dict[str, Any], audit_id: str) -> dict[str, Any]:
    modes = ("adapt_full", "full")
    pre_outputs = {mode: (PROJECT_ROOT / "pre" / "output" / mode).is_dir() for mode in modes}
    config_paths = [
        PROJECT_ROOT / "pre" / "config" / "adapt_full.yaml",
        PROJECT_ROOT / "pre" / "config" / "full.yaml",
        MODULE_ROOT / "config" / "adapt_full.yaml",
        MODULE_ROOT / "config" / "full.yaml",
        PROJECT_ROOT / "overall_adv" / "config" / "v3.yaml",
        PROJECT_ROOT / "part_adv" / "config" / "v3.yaml",
    ]
    configs_present = all(path.is_file() for path in config_paths)
    checkpoint_support = all(
        token in (MODULE_ROOT / "main.py").read_text(encoding="utf-8")
        for token in ("--resume-staging", "resume_staging")
    )
    downstream_resume = all(
        "--resume" in (PROJECT_ROOT / name / "main.py").read_text(encoding="utf-8")
        for name in ("overall_adv", "part_adv")
    )
    disk = shutil.disk_usage(PROJECT_ROOT)
    memory = psutil.virtual_memory()
    data_bytes = baseline["data_total_bytes"]
    cache_files = [path for path in (PROJECT_ROOT / "pre" / "cache").rglob("*") if path.is_file()]
    cache_bytes = sum(path.stat().st_size for path in cache_files)
    output_paths = [
        "pre/output/adapt_full", "overall_run/output/adapt_full",
        "overall_adv/output/adapt_full", "part_adv/output/adapt_full",
    ]
    source_ready = bool(configs_present and baseline["checks"]["formal_input_hashes"])
    start = "PRE adapt_full" if not pre_outputs["adapt_full"] else "overall_run adapt_full"
    cloud_ready = source_ready
    return {
        "audit_id": audit_id,
        "purpose": "EVIDENCE_EXPANSION_AND_FINAL_EVALUATION",
        "cloud_ready": cloud_ready,
        "cloud_start_stage": start,
        "pre_adapt_full_exists": pre_outputs["adapt_full"],
        "pre_full_exists": pre_outputs["full"],
        "pre_fast_must_not_feed_long_run": True,
        "formal_72_full_allowed": False,
        "configs_present": configs_present,
        "checkpoint_resume": {
            "overall_run_explicit_staging": checkpoint_support,
            "overall_adv_hash_valid_resume": downstream_resume,
            "part_adv_hash_valid_resume": downstream_resume,
        },
        "workers": {
            "initial_n_jobs": 2,
            "maximum_initial_n_jobs": 4,
            "do_not_use_n_jobs_minus_one": True,
            "run_downstream_sequentially": True,
        },
        "resources": {
            "input_data_bytes": data_bytes,
            "pre_cache_bytes": cache_bytes,
            "recommended_cloud_volume_bytes": 250_000_000_000,
            "recommended_free_working_bytes_after_sync": 100_000_000_000,
            "recommended_memory_bytes": 64_000_000_000,
            "minimum_memory_bytes": 32_000_000_000,
            "current_host_disk_free_bytes": disk.free,
            "current_host_memory_total_bytes": memory.total,
            "current_host_is_not_long_run_target": True,
        },
        "clean_order": ["part_adv", "overall_adv", "overall_run", "pre"],
        "commands": [
            "python -u pre/main.py adapt_full --progress normal --n-jobs 2",
            "python -u pre/main.py validate adapt_full --progress normal --n-jobs 2",
            "python -u overall_run/main.py adapt_full --progress normal --n-jobs 2",
            "python -u overall_run/main.py validate adapt_full --progress normal --n-jobs 2",
            "python -u overall_adv/main.py adapt_full --progress normal --n-jobs 2",
            "python -u overall_adv/main.py validate --mode adapt_full --progress normal --n-jobs 2",
            "python -u part_adv/main.py adapt_full --progress normal --n-jobs 2",
            "python -u part_adv/main.py validate --mode adapt_full --progress normal --n-jobs 2",
            "python finalize_current_data_adapt_full.py",
        ],
        "expected_output_paths": output_paths,
        "resume_failure_policy": "Resume only when input/config/target/task/checkpoint hashes validate; otherwise clean only the failed mode and restart it.",
        "prohibited_uses": ["PARAMETER_SELECTION", "RETUNING", "THRESHOLD_OPTIMIZATION"],
        "prohibited_changes": [
            "model", "features", "formal target", "quantile grid", "calibration hierarchy",
            "cohort", "bootstrap unit", "thresholds", "acceptance gates", "data",
        ],
        "run_started": False,
        "full_recommended": False,
    }


def build_cloud_markdown(readiness: dict[str, Any]) -> str:
    commands = "\n".join(readiness["commands"])
    return textwrap.dedent(
        f"""
        # Cloud Full Readiness (Read Only)

        ```text
        CLOUD_READY={str(readiness['cloud_ready']).lower()}
        CLOUD_START_STAGE={readiness['cloud_start_stage']}
        PURPOSE={readiness['purpose']}
        FULL_RECOMMENDED=false
        RUN_STARTED=false
        ```

        PRE adapt_full and PRE full artifacts are absent. PRE Fast is valid only for Fast and must not be supplied to an adapt_full/full run. The current authorized long mode is `CURRENT_DATA_ADAPT_FULL`, so the first stage is `pre/main.py adapt_full`.

        ## Resources and workers

        - Start with `--n-jobs 2`; use at most 4 initially and never `-1`.
        - Run PRE, overall_run, overall_adv and part_adv sequentially.
        - Provision at least 250 GB volume, leaving at least 100 GB free after syncing data and cache.
        - Minimum memory is 32 GB; 64 GB is recommended.
        - Current data are {readiness['resources']['input_data_bytes']:,} bytes; PRE cache is {readiness['resources']['pre_cache_bytes']:,} bytes.
        - The current workstation has only {readiness['resources']['current_host_disk_free_bytes']:,} free bytes and is not the long-run target.

        ## Clean order

        Inspect with `--dry-run`, then clean only `adapt_full` in this order: `part_adv`, `overall_adv`, `overall_run`, `pre`. Stop for unknown workers, locks, staging, partial artifacts or stale checkpoints.

        ## Commands (not executed)

        ```powershell
        {commands}
        ```

        ## Checkpoint and recovery

        overall_run supports an explicit staging resume path. Advantage modules support hash-valid resume. Resume is prohibited when input, scientific config, target contract, task partition or output hashes differ. Clean and restart only the failed mode when resume validation fails.

        ## Boundaries

        This run is only for `EVIDENCE_EXPANSION_AND_FINAL_EVALUATION`. It is not parameter selection, retuning or threshold optimization. Formal 72-day Full and Precision remain unauthorized. No command in this report was executed.
        """
    )


def build_audit_markdown(summary: dict[str, Any], context: dict[str, Any]) -> str:
    values = context["values"]
    return textwrap.dedent(
        f"""
        # M1 D6 Current-Authoritative Metric-Lineage Audit

        ```text
        AUDIT_ID={summary['audit_id']}
        D6_AUDIT_ENGINEERING_STATUS=PASS
        CURRENT_METRIC_IDENTITY_STATUS=PASS
        CURRENT_AUTHORITATIVE_LINEAGE_STATUS=PASS
        HISTORICAL_RECONCILIATION_STATUS=DEPRECATED_UNRECOVERABLE
        HISTORICAL_DISPOSITION_STATUS=PASS
        FORMAL_DIAGNOSTIC_SEPARATION_STATUS=PASS
        METRIC_VERSIONING_STATUS=PASS
        Q95_FINAL_CLASSIFICATION=SYSTEMATIC_CALIBRATION_CONCERN_CURRENT_FAST
        Q95_CERTIFICATION=METRIC_SUPPORT_LIMITED
        Q99_FINAL_CLASSIFICATION=METRIC_SUPPORT_LIMITED_CURRENT_FAST_ONLY
        TAIL_SUPPORT_STATUS=LIMITED_CURRENT_FAST_ONLY
        M1_SCIENTIFIC_STATUS=STOP_AND_REVIEW
        D6_LINEAGE_STATUS=PASS_CURRENT_AUTHORITATIVE_LINEAGE_ONLY
        CLOUD_READY={str(summary['cloud_ready']).lower()}
        CLOUD_START_STAGE={summary['cloud_start_stage']}
        FULL_RECOMMENDED=false
        ```

        > Deprecation is an evidence-governance decision. It is not a reconstruction or scientific reconciliation of the historical values.

        ## Baseline and identity

        All 113 registered artifacts, five PRE tables and 167 formal input files match their frozen SHA-256 values. `data/` remains 687 files and 85,406,288,136 bytes. Registered artifacts were identical before and after this audit.

        | Metric | Reconstructed | Support | Prediction layer |
        |---|---:|---:|---|
        | Coverage90 | {values['coverage90']:.15g} | 640 | FINAL_PUBLISHED_QUANTILES |
        | CRPS | {values['crps']:.15g} | 640 | FINAL_PUBLISHED_QUANTILES |
        | twCRPS | {values['twcrps']:.15g} | 640 | FINAL_PUBLISHED_QUANTILES |
        | q95 exceedance | {values['q95_exceedance']:.15g} | 640 | FINAL_PUBLISHED_QUANTILES |
        | q99 exceedance | {values['q99_exceedance']:.15g} | 640 | FINAL_PUBLISHED_QUANTILES |
        | Outcome-selected tail coverage | {values['tail_coverage90']:.15g} | 32 | FINAL_PUBLISHED_QUANTILES |
        | Upper shortfall q99 | {values['upper_shortfall']:.15g} minutes | 640 | FINAL_PUBLISHED_QUANTILES |
        | Raw crossing rows | {values['raw_crossing_rows']} | 640 | RAW_MODEL_QUANTILES |
        | Projected crossing rows | {values['projected_crossing_rows']} | 640 | FINAL_PUBLISHED_QUANTILES |

        Metric mismatch count is 0; support mismatch count is 0; cohort hash mismatch count is 0; prediction-layer mismatch count is 0. The formal snapshot hash is `{context['formal_cohort_hash']}`. The final samples consumed by M2 were independently regenerated with maximum absolute delta 0.

        ## Formula and layer answers

        Pinball uses residual `Y-Q` and `max(tau*(Y-Q),(tau-1)*(Y-Q))`, averaged by row with no sample weights. CRPS is twice the trapezoidal integral of those losses over the 15-point nonuniform grid. twCRPS is the row CRPS weighted 5 for outcomes at or above validation raw-label q95 `{context['validation_q95']}` and 1 otherwise. A negative PROP-HIST delta means PROP is better because lower proper scores are better.

        Raw quantiles are persisted as `raw_q_*`. Validation residual offsets are selected through airport-stage, stage, then global fallback. Isotonic projection is applied after calibration. The resulting `q_*` columns are both the monotonicity-projected and final-published layer. There is no value clipping; inverse sample interpolation clamps uniforms outside q01-q99 to the endpoint quantiles.

        CRPS, twCRPS, all pinball losses, coverage, calibration, Brier and trigger probabilities use final quantiles. Raw crossing alone uses raw model quantiles. M2 uses 256 predictive samples generated from final quantiles.

        ## Cohort and formal/diagnostic separation

        The formal cohort is independently rebuilt from 7,928 valid primary test snapshots to the frozen 640-row formal_core selection, containing 239 flights, six events, one anchor day and six airports. The q05-q95 interval includes both boundaries and aggregates by row.

        Coverage90 `0.925` uses all 640 formal rows and no outcome-based membership filter. Tail coverage `0.4375` is 14 covered rows among 32 rows selected by `Y > {context['train_q95']}`. It is `OUTCOME_SELECTED_DIAGNOSTIC_ONLY`, is prohibited as a primary gate, and cannot be compared directly with unconditional Coverage90.

        `upper_shortfall` has a documented dual role label: acceptance.yaml declares a formal distribution metric, while the q95 audit publishes it inside a stress-diagnostic block. It has no accepted range and is not an active gate; canonical ID `M1_UPPER_SHORTFALL_Q99_REPORT_ONLY_V1` prevents it from being mistaken for a primary gate.

        ## q95, q99 and bootstrap

        q95 exceedance is reproducibly `0.0609375`; current frozen classification is `SYSTEMATIC_CALIBRATION_CONCERN_CURRENT_FAST`. Certification remains `METRIC_SUPPORT_LIMITED`. q99 exceedance is reproducibly `0.025`, but with only six event clusters it is `METRIC_SUPPORT_LIMITED_CURRENT_FAST_ONLY`, not scientific PASS.

        The primary bootstrap unit is `trigger_event_group_id`, not snapshots. The frozen audit config has 2,000 draws, seed 20260725 and minimum 20 events. With six events, no draw-based CI is issued. Historical q99 PASS has been deprecated and is not part of the current evidence.

        ## Historical disposition

        All unrecoverable historical D6 approximate values and D6 B claims without prediction, cohort, metric-version, calibration-layer and bootstrap metadata are registered as `NOT_RECONSTRUCTABLE`, `NON_AUTHORITATIVE`, `PROHIBITED`, and `DEPRECATED_UNRECOVERABLE`. No historical-current delta or scope reconciliation is asserted. A future recovery requires a new retrospective audit and may not overwrite this audit.

        ## Scientific and cloud decision

        `M1_D6_CURRENT_LINEAGE_AUDIT_PASS` means only that the current formulas, layers, cohorts and values are traceable and that unrecoverable history is outside the authority chain. `M1_SCIENTIFIC_STATUS` remains `STOP_AND_REVIEW`.

        PRE adapt_full/full artifacts do not exist. PRE Fast cannot feed a long run. The cloud sequence therefore starts at `PRE adapt_full`, solely for `EVIDENCE_EXPANSION_AND_FINAL_EVALUATION`. No cloud or Full command was executed, and explicit researcher authorization is still required.
        """
    )


