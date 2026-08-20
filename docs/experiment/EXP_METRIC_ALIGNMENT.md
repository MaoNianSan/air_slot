# Experiment Metric Alignment

Classification applies to the metric implementation, not to historical numerical results.

## Required metrics

| Family | Required metric | Current implementation | Classification | Migration requirement |
| --- | --- | --- | --- | --- |
| Prediction | CRPS | `validation/m1_horizon_accuracy_quick_20260818.py::crps_energy` only | `CHANGE` | move/formalize the tested formula under `exp/`; consume current V2 weighted scenarios and record units/support |
| Prediction | Brier | not found | `CHANGE` | add a declared binary-event definition and proper weighted probability score |
| Prediction | calibration | M1 temperature fitting and limited diagnostics; old Exp1 ECE | `CHANGE` | separate fitting from evaluation; report reliability/error by declared target/horizon without refitting on evaluation data |
| Prediction | coverage | quantile coverage diagnostics exist, but “coverage” is also used for support/material coverage | `CHANGE` | implement predictive interval coverage with explicit nominal level and rename support coverage fields unambiguously |
| Decision | action disagreement | `exp/exp2/metrics.py::top1_disagreement` | `KEEP` after typed-input guard | compare supported rankings only; report abstain/non-comparable denominator |
| Decision | ranking change | pairwise reversal, top-3 overlap, top-1 agreement, and risk-sensitive episode rate exist | `CHANGE` | choose one frozen primary definition; preserve ties, support and ranking authority |
| Decision | risk difference | no aligned implementation | `CHANGE` | compute paired differences from M4 `residual_risk_objective` or declared risk field only; never from raw CU |
| System | runtime | scattered elapsed/training/inference timers | `CHANGE` | standardize PRE/M1/M2/M3/M4/report and end-to-end durations, repetitions and environment metadata |
| System | latency | `exp/exp4/metrics.py::latency_percentiles` | `KEEP` with instrumentation changes | define request boundary, warm/cold state, units, concurrency, failures and p50/p95/p99 denominator |

## Existing supplementary metrics

| Existing metric group | Classification | Reason |
| --- | --- | --- |
| episode bootstrap / paired episode-cluster bootstrap | `KEEP` | correct independent unit is episode; must retain all repeated nodes/scenarios within sampled episodes |
| Exp2 consequence distortion | `KEEP` as supplementary | useful for representation sufficiency if computed from current typed M2 output |
| action-gap distortion / selection penalty | `CHANGE` | old implementation consumes arbitrary action-value dictionaries; must use supported M4 risk values |
| old Exp1 warning lead, recall and FPR metrics | `REMOVE` from primary new Exp1 | answer the former warning-window question; may remain historical diagnostics |
| Exp3 formal lane/coverage/LLM metrics | `REMOVE` from new Exp3 | answer the former support-boundary question |
| raw rank agreement from Exp234 | `REMOVE` | based on legacy raw-CU action maps and scenario-only response |

## Metric artifact minimum contract

Every metric row should record:

- experiment ID, variant ID and comparison/reference variant;
- metric ID, version, definition, direction, unit and aggregation level;
- dataset ID/role, split, cohort hash and episode/node/scenario denominators;
- estimate, uncertainty interval and bootstrap unit/replicates where applicable;
- model/artifact/scenario/M2/M3/M4 hashes and seed stream;
- support state, ranking authority, reason codes and abstention count;
- whether the value is predictive, decision, system, diagnostic, conditional, or authoritative.

## Prohibitions

- Do not name a raw-CU difference “risk difference.”
- Do not compute Brier without a frozen event definition.
- Do not pool decision nodes or scenarios as independent observations.
- Do not omit unsupported cases from the denominator without reporting them.
- Do not use calibration/evaluation data to tune a metric threshold after the protocol freeze.

`METRIC_STATUS = PARTIAL_REUSABLE_HELPERS_MISSING_ALIGNED_SUITE`

