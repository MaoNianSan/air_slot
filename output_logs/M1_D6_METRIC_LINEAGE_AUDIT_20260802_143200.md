
# M1 D6 Current-Authoritative Metric-Lineage Audit

```text
AUDIT_ID=M1_D6_LINEAGE_AUDIT_20260802_143200
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
CLOUD_READY=true
CLOUD_START_STAGE=PRE acceptance_23d
FULL_RECOMMENDED=false
```

> Deprecation is an evidence-governance decision. It is not a reconstruction or scientific reconciliation of the historical values.

## Baseline and identity

The manifest-defined publication census, five PRE tables and 167 formal input files match their frozen SHA-256 values. Registered artifacts were identical before and after this audit.

| Metric | Reconstructed | Support | Prediction layer |
|---|---:|---:|---|
| Coverage90 | 0.925 | 640 | FINAL_PUBLISHED_QUANTILES |
| CRPS | 11.6842222021244 | 640 | FINAL_PUBLISHED_QUANTILES |
| twCRPS | 34.2681799023801 | 640 | FINAL_PUBLISHED_QUANTILES |
| q95 exceedance | 0.0609375 | 640 | FINAL_PUBLISHED_QUANTILES |
| q99 exceedance | 0.025 | 640 | FINAL_PUBLISHED_QUANTILES |
| Outcome-selected tail coverage | 0.4375 | 32 | FINAL_PUBLISHED_QUANTILES |
| Upper shortfall q99 | 3.49779718094002 minutes | 640 | FINAL_PUBLISHED_QUANTILES |
| Raw crossing rows | 547 | 640 | RAW_MODEL_QUANTILES |
| Projected crossing rows | 0 | 640 | FINAL_PUBLISHED_QUANTILES |

Metric mismatch count is 0; support mismatch count is 0; cohort hash mismatch count is 0; prediction-layer mismatch count is 0. The formal snapshot hash is `8dbfef66bf438a1c13a141a7390b9668ed7c30a59f629c23763dac77c653727b`. The final samples consumed by M2 were independently regenerated with maximum absolute delta 0.

## Formula and layer answers

Pinball uses residual `Y-Q` and `max(tau*(Y-Q),(tau-1)*(Y-Q))`, averaged by row with no sample weights. CRPS is twice the trapezoidal integral of those losses over the 15-point nonuniform grid. twCRPS is the row CRPS weighted 5 for outcomes at or above validation raw-label q95 `37.099999999999994` and 1 otherwise. A negative PROP-HIST delta means PROP is better because lower proper scores are better.

Raw quantiles are persisted as `raw_q_*`. Validation residual offsets are selected through airport-stage, stage, then global fallback. Isotonic projection is applied after calibration. The resulting `q_*` columns are both the monotonicity-projected and final-published layer. There is no value clipping; inverse sample interpolation clamps uniforms outside q01-q99 to the endpoint quantiles.

CRPS, twCRPS, all pinball losses, coverage, calibration, Brier and trigger probabilities use final quantiles. Raw crossing alone uses raw model quantiles. M2 uses 256 predictive samples generated from final quantiles.

## Cohort and formal/diagnostic separation

The formal cohort is independently rebuilt from 7,928 valid primary test snapshots to the frozen 640-row formal_core selection, containing 239 flights, six events, one anchor day and six airports. The q05-q95 interval includes both boundaries and aggregates by row.

Coverage90 `0.925` uses all 640 formal rows and no outcome-based membership filter. Tail coverage `0.4375` is 14 covered rows among 32 rows selected by `Y > 34.11666666666666`. It is `OUTCOME_SELECTED_DIAGNOSTIC_ONLY`, is prohibited as a primary gate, and cannot be compared directly with unconditional Coverage90.

`upper_shortfall` has a documented dual role label: acceptance.yaml declares a formal distribution metric, while the q95 audit publishes it inside a stress-diagnostic block. It has no accepted range and is not an active gate; canonical ID `M1_UPPER_SHORTFALL_Q99_REPORT_ONLY_V1` prevents it from being mistaken for a primary gate.

## q95, q99 and bootstrap

q95 exceedance is reproducibly `0.0609375`; current frozen classification is `SYSTEMATIC_CALIBRATION_CONCERN_CURRENT_FAST`. Certification remains `METRIC_SUPPORT_LIMITED`. q99 exceedance is reproducibly `0.025`, but with only six event clusters it is `METRIC_SUPPORT_LIMITED_CURRENT_FAST_ONLY`, not scientific PASS.

The primary bootstrap unit is `trigger_event_group_id`, not snapshots. The frozen audit config has 2,000 draws, seed 20260725 and minimum 20 events. With six events, no draw-based CI is issued. Historical q99 PASS has been deprecated and is not part of the current evidence.

## Historical disposition

All unrecoverable historical D6 approximate values and D6 B claims without prediction, cohort, metric-version, calibration-layer and bootstrap metadata are registered as `NOT_RECONSTRUCTABLE`, `NON_AUTHORITATIVE`, `PROHIBITED`, and `DEPRECATED_UNRECOVERABLE`. No historical-current delta or scope reconciliation is asserted. A future recovery requires a new retrospective audit and may not overwrite this audit.

## Scientific and cloud decision

`M1_D6_CURRENT_LINEAGE_AUDIT_PASS` means only that the current formulas, layers, cohorts and values are traceable and that unrecoverable history is outside the authority chain. `M1_SCIENTIFIC_STATUS` remains `STOP_AND_REVIEW`.

PRE acceptance_23d/full artifacts are profile-specific. PRE Fast cannot feed a long run. Evidence expansion starts at `PRE acceptance_23d`; middle and full require their own readiness contracts and authorization.
