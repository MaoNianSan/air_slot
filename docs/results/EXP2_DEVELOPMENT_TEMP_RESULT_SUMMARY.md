# Exp2 Development Temporary Result Summary

## Status

- `DEVELOPMENT_ONLY = TRUE`
- `TEMPORARY_REPORT = TRUE`
- `NOT_FINAL_PAPER_RESULT = TRUE`
- `FINAL_TEST_ACCESS_COUNT = 0`
- `PAPER_FULL_RUN = FALSE`
- `M1_PURE_INFERENCE = REUSED`; `M1_PURE_INFERENCE_REUSED = TRUE`

## Scientific Question

When does preserving joint operational uncertainty materially affect consequence assessment and recovery comparison?

## Frozen Inputs

- PRE: reused (no rebuild)
- M1: frozen signed model (H=32, W=30, seed 20260813; `R_IB -> DELTA_OB -> T_TX` chain)
- M1 scenario artifact: `sha256:ca3370a3…1dfec` (`M1_SIGNED_DEVELOPMENT_SCENARIOS_V1`, `--verify-only=PASS`)
- M2: `M2_DATA2_FORMAL_CU_V1` (registry hash `sha256:c257debc…b029`)
- M3: `M3_RESPONSE_SCENARIO_V1` (registry hash `sha256:ff8adb30…5ce0`; response seed 20260813 recorded)
- M4: support-aware implementation; material coverage contract not frozen

## Cohort

| Level | N | Role |
|---|---|---|
| Episode | 128 | independent empirical unit |
| Decision node | 1824 | repeated observation |
| Scenario per node | 250 | numerical representation |
| Total numerical scenarios | 456000 | numerical representation (NOT independent observations) |

The 456,000 numerical scenarios are not treated as independent observations; all empirical summaries are episode-balanced or node-level with episode counts reported.

## Principal Point-vs-Distribution Result

Contrast: DISTRIBUTIONAL (frozen aligned M1 scenarios through frozen M2, reference q=0) vs POINT COLLAPSE (frozen weighted joint medoid through the same M2).

| Metric | Point collapse, node mean | Point collapse, episode-balanced mean |
|---|---|---|
| ConsequenceDistortion | 1.7272 | 1.7624 |
| Tail consequence difference (p90 of per-action abs diff) | 1.7202 | 1.7640 |
| Tail consequence difference (max of per-action abs diff) | 1.9164 | 1.9862 |
| ActionGapDistortion | 0.2310 | 0.2526 |
| Top1Disagreement | 0.4890 | 0.4912 |

Distinction: ConsequenceDistortion measures the summed absolute difference of the five-component formal consequence representation; ActionGapDistortion measures pairwise action-value gap distortion; Top1Disagreement measures whether the lowest-consequence action changes. The distributional reference is exactly self-consistent (q=0, all metrics 0.0).

## Stratified Results

Stratum definitions (derived from the frozen scenario artifact; stored labels shown exactly):

- `operational_stage` (frozen labels): `PRE_IB`, `POST_IB_PRE_OB`, `POST_OB_PRE_TO`
- `high_uncertainty` (`True`/`False`): node-level std across 250 scenarios of derived `R_OB` minutes ≥ Q3 (True)
- `tight_turnaround` (`True`/`False`): node-level minutes from decision time to episode end ≤ Q1 (True)

ConsequenceDistortion (point collapse):

| Stratum | Label | N | Node mean | Episode-balanced mean |
|---|---|---|---|---|
| operational_stage | POST_IB_PRE_OB | 1502 | 1.5017 | 1.5159 |
| operational_stage | POST_OB_PRE_TO | 53 | 0.7351 | 0.7351 |
| operational_stage | PRE_IB | 269 | 3.1817 | 3.2916 |
| high_uncertainty | False | 1362 | 1.6836 | 1.7216 |
| high_uncertainty | True | 462 | 1.8559 | 1.9100 |
| tight_turnaround | False | 1344 | 1.7960 | 1.8764 |
| tight_turnaround | True | 480 | 1.5347 | 1.5460 |

## Lineage Corruption

Frozen corruption grid `q = [0.0, 0.25, 0.50, 0.75, 1.0]` (marginal-preserving within-scenario shuffle).

| q | ConsequenceDistortion (node) | ConsequenceDistortion (episode) | Tail p90 (node) | ActionGapDistortion (node) | Top1Disagreement (node) |
|---|---|---|---|---|---|
| 0.25 | 0.0420 | 0.0438 | 0.0443 | 0.0053 | 0.0208 |
| 0.50 | 0.0688 | 0.0712 | 0.0718 | 0.0079 | 0.0340 |
| 0.75 | 0.0898 | 0.0910 | 0.0933 | 0.0101 | 0.0417 |
| 1.00 | 0.1138 | 0.1145 | 0.1177 | 0.0121 | 0.0493 |

The magnitude of distortion from lineage corruption increased with corruption severity, but remained substantially smaller than the distortion associated with collapsing the predictive distribution to a point representation in this Development cohort. This does not imply lineage is unimportant, nor that point collapse always dominates lineage corruption; this is Development evidence only.

## Scenario-Conditioned Action Comparison

Status: `EXP2_FORMAL_RANKING_RESULTS = BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`. The following are **SCENARIO_CONDITIONED · NON_AUTHORITATIVE · TEMPORARY_DEVELOPMENT_ONLY** and are not authoritative, formal, optimal-action, or causal-action claims.

| Metric | Point collapse, node mean |
|---|---|
| ActionGapDistortion | 0.2310 |
| PairwiseRankingReversalRate | 0.1214 |
| RankingAt3Overlap | 0.7014 |
| Top1Disagreement | 0.4890 |
| ReferenceObjectiveSelectionPenalty (normalized) | 0.0536 |
| ReferenceObjectiveSelectionPenalty (raw) | 0.0972 |

`ReferenceObjectiveSelectionPenalty` is not called regret. Per-node values: `artifacts/_archive/2026-08-25/exp2_development_temp/exp2_temp_scenario_action_results.parquet` (local, not pushed).

## Interpretation

- **A (consequence level):** Point collapse materially alters the reconstructed consequence representation relative to the frozen distributional scenario representation in this Development cohort.
- **B (mechanism level):** Distortion is larger in some early/high-uncertainty operating states (`PRE_IB` node mean 3.182; `high_uncertainty=True` 1.856 vs False 1.684), which is consistent with the idea that preserving uncertainty matters most before the operational state has contracted.
- **C (action level):** Scenario-conditioned action comparisons show non-trivial sensitivity to uncertainty representation (Top1Disagreement 0.489), but authoritative formal ranking remains pending the frozen M4 material-coverage contract.

C is not upgraded into a final paper claim.

## Provenance

- M1 scenario artifact: `sha256:ca3370a3…1dfec`
- Exp2 temporary manifest: `sha256:ceeabb16…6920` (`artifacts/_archive/2026-08-25/exp2_development_temp/EXP2_TEMPORARY_MANIFEST.json`, local)
- Exp2 development V1 checkpoint: `sha256:1cf8a7ac…666d` (`EXP2_DEVELOPMENT_V1.json`, local)
- M2 registry: `sha256:c257debc…b029`; M3 response registry: `sha256:ff8adb30…5ce0`
- Global development closure: `sha256:d43ae36f…1b1ad`
- Temporary aggregate checkpoint vs frozen `EXP2_DEVELOPMENT_V1.json`: 20/20 items matched within 1e-9 (`frozen_aggregate_checkpoint_pass=True`)
- Source: `artifacts/_archive/2026-08-25/exp2_development_temp/` (local, gitignored); detailed report `docs/TEMPORARY_DEVELOPMENT_REPORT_20260818.md`

