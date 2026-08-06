# M1-M2 V2 Implementation Report

Date: 2026-08-06

## Before

The previous implementation exposed incomplete M1 sample variables, sampled
finite bins at their lower bounds, silently mapped overflow to the overflow
lower bound, accepted loose operational parameters, and used a monolithic
legacy M2 that mixed normalization, channel quantities, coupling, and RMB
conversion. The formal pipeline stopped at M2_CONTRACT_MISMATCH.

## After

### M1

- Added frozen feature schema, five-minute snapshots, episode sequences,
  single-node updates, revision replay, artifact-bound states, training/
  checkpoint modules, and calibration artifacts.
- Kept the single lightweight GRU architecture and three heads.
- Added M1ScenarioBundle, stable serialization, r_ib_minutes, r_ob_minutes,
  and earliest_offblock_time.
- Added stable within-bin sampling and training-only empirical tail artifacts.
- Bound empirical tails to checkpoint manifests.
- Retired cumulative feature_builder.py semantics.

### M1 to M2

- Added adapter validation for IDs, cutoff, sample count, provenance, and M1
  structural time identities.
- Equal sample weights are derived as 1/S.
- The dependence mode is explicitly structural coupling, not a fitted full
  joint distribution.

### M2

- Replaced the formal monolith with contracts, adapter, activation, events,
  compact rules, quantities, modifiers, subitem values, constructed units,
  corrections, currency, reconstruction, summaries, and evaluation audit.
- Preserved the previous implementation only as explicit legacy code.
- Implemented evidence-driven activation for nine candidate subitems.
- Implemented subitem CU conversion before channel aggregation.
- Kept the currency layer separate with 1 CU = 1 RMB.
- Blocks formal q95/CVaR when unresolved overflow is present.

## Configuration

scientific.yaml now freezes M1 sampling semantics, M2 identity, compact
complexity limits, direct-only cross-channel mode, disabled learned
correction, subitem CU conversion, and RMB identity mapping. Business values
and rule thresholds remain NOT_CONFIGURED and
REQUIRES_DEVELOPMENT_FREEZE.

## M1 Model Change Assessment

The predictive architecture did not change. Interface, input schema, snapshot
semantics, state/replay logic, output contracts, and sampling changed.
Existing checkpoints must pass identity checks. Formal retraining is required
for the new feature schema.

## Design Conflicts Resolved

1. One design note assigns snapshots to PRE, while the correction instruction
   requires an M1 adapter builder. The implementation rebuilds only from the
   published PRE bundle and frozen registry; it does not read raw data or
   replace PRE evidence authority.
2. The legacy M2 conflicts with subitem-level CU V2. It is retained under an
   explicit legacy name and is not presented as V2 compatible.
3. Formal tail data and subitem values are unavailable in this code phase.
   The implementation reports unresolved/not configured rather than inventing
   values.

## Downstream Status

M1-to-M2 targeted synthetic integration passes. The global pipeline now stops
at M3_CONTRACT_MISMATCH. No adapter converts V2 sample losses back to the old
scalar M3/M4 input.

## Not Run

- PRE build or validation;
- M1 formal training, calibration, or evaluation;
- M2 formal production reconstruction;
- overall_run fast, middle, full, or precision;
- overall_adv or part_adv;
- M3 or M4 migration runs.

## Final Code Status

    M1_CODE_STATUS=CODE_READY_TARGETED_TESTS_PASS
    M2_V2_CODE_STATUS=CODE_READY_TARGETED_TESTS_PASS
    M1_TRAINING_STATUS=NOT_RUN
    M1_CALIBRATION_STATUS=NOT_RUN
    M1_EVALUATION_STATUS=NOT_RUN
    M3_STATUS=M3_CONTRACT_MISMATCH
    M4_STATUS=MIGRATION_REQUIRED
    GLOBAL_RERUN_STATUS=NOT_RUN
    COMMIT_CREATED=YES
    PUSH_PERFORMED=YES
