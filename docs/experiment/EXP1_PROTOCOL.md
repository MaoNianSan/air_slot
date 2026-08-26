# Exp1 Protocol

## Question

Why are direct cross-stage information reuse and admissible history needed in
the rolling recovery state?

## Active Variants

| Subexperiment | Variants | Only Changed Factor |
| --- | --- | --- |
| Exp1A | EXP1A_NO_DIRECT_REUSE, EXP1A_FULL | Whether current information remains directly reusable after state/consequence formation |
| Exp1B principal | EXP1B_CURRENT, EXP1B_ADAPTIVE_HISTORY | Legal history available to the same train-frozen state-aware architecture |
| Exp1B sensitivity | EXP1B_FIXED_HISTORY_30 | Fixed 30-minute history; never included in the principal result table without the explicit sensitivity switch |

Both Exp1A variants preserve PRE, M1, M2, M3, M4, the action library, and
support/provenance rules. NO_DIRECT_REUSE keeps minimal actionability,
execution-window, and qualification facts, while blocking hidden-history and
raw-weather rereads.

## Metrics And Claims

Primary outputs are state/representation differences, primitive-target CRPS,
and principal-event Brier/calibration when the train-frozen M1 V2 artifact is
available. Top-1 disagreement and ex-post model-implied residual risk are
secondary downstream diagnostics. The residual-risk unit is
`CONSTRUCTED_LOSS_UNIT` until a complete authoritative mapping freezes; replay
is not an observed causal treatment effect.

Warning/FPR/recall/DecisionWindowGain, context neutralization, and
shared-state efficiency are legacy or appendix-only and are not headline Exp1
evidence.

## Gates

`CONTRACT_FAST` validates the information mask, history isolation,
split/lineage, and result schema without raw data. `REAL_DATA_FAST` binds the
shared Data2 Development cohort but currently leaves M1-state and M4-decision
metrics `NOT_RUN` rather than substituting legacy V1 outputs. FINAL_TEST_ACCESS_COUNT
= 0 and PAPER_FULL_RUN = FALSE.

## 2026-08-25 Development Evidence Closure (supplement execution)

Executed under `codex_framework/AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT_20260825.md`
(DEVELOPMENT_ONLY). The baseline
`docs/experiment/DEVELOPMENT_CLOSURE_EXECUTION_20260825.md` is untouched.

- Exp1A: `EXP1A_M2_INTERFACE_CHANGES = NONE`. Per-node paper-facing records
  (EXP1A_FULL / EXP1A_REDUCED) built from frozen M2 consequences and read-only M3
  instantiation; comparison/top-1/ranking stay NOT_RUN at the shared M4 mapping/replay gate.
  Frozen-sorting diagnostic: `q_state(i)` (scenario-weighted mean `D_TO`) vs `q_ctx(i)`
  (scenario-weighted mean formal five-component consequence) on `S_i = {D_TO finite AND
  five_component_status = FORMAL_AVAILABLE}`, `support_fraction_i = |S_i| / 250`, main
  threshold `>= 0.90`, sensitivity `>= 0.50`, typed exclusions
  (`EXCLUDED_M1_NONFINITE` / `EXCLUDED_M2_NOT_AVAILABLE` / `EXCLUDED_SUPPORT_BELOW_THRESHOLD`);
  Spearman rho, Kendall tau, top-10%/20% overlap, decile-divergence rate
  (`|decile gap| >= 3`), episode-cluster bootstrap (2000, seed `20260825`, percentile 95% CI).
  Claim scope: `DEVELOPMENT_CONDITIONAL_DIAGNOSTIC`.
- Exp1B: H32 CURRENT-only comparator `M1_V2_GRU_H32_CURRENT_ONLY` trained with the exact H32
  History budget (Adam lr=0.001, weight_decay=0.0, epochs=2, batch=64, seed=20260821,
  128/128 FAST_TRAIN_MODE; same B2 cache/feature/support; input
  `cache.partition(split, representation="CURRENT")`).
  `budget_identical_to_reference = true`, `calibration_path_identical_to_reference = true`.
  Per-node prediction records (HISTORY + CURRENT), paired delta-MAE table over lead-time bins,
  NA without interpolation. Claim scope: `DEVELOPMENT_COMPARATOR_ONLY`.
- Outputs: `artifacts/experiment/exp1_full_development/exp1_closure_20260825/`
  (`*_DEVELOPMENT_ONLY` filenames; CSV + parquet + manifests + summary + interpretation).
- Safety: `FINAL_TEST_ACCESS_COUNT = 0`, `PAPER_FULL_RUN = FALSE`.
- Remaining human gates: G2 (M3 non-A00 / M4 production mapping freeze) before
  comparison/ranking upgrade; G3 (freeze `PAPER_OUTPUT_SPEC_V1.json`) before Test.
