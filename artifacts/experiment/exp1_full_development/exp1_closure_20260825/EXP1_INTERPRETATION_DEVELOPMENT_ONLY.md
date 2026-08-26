# Exp1 Development Evidence Closure — Interpretation (DEVELOPMENT_ONLY)

Generated from the 2026-08-25 supplement; DEVELOPMENT_ONLY scope.

## Claim scope

- Exp1A records + frozen sorting: `DEVELOPMENT_CONDITIONAL_DIAGNOSTIC` (non-causal, non-optimal, non-authoritative ranking).
- Exp1B HISTORY/CURRENT records: `DEVELOPMENT_COMPARATOR_ONLY`; `PAPER_FULL_RUN = FALSE`.
- Comparison/top-1/ranking remain NOT_RUN at the shared M4 mapping/replay gate (G2).
- `FINAL_TEST_ACCESS_COUNT = 0`; no calibration data read; no model training in this module.

## Exp1A

- Per-node records: 1769 nodes x 2 variants.
- Sorting diagnostic: 1769 nodes; 1420 in main (support_fraction >= 0.90); 1765 in sensitivity (>= 0.50).
- Excluded by reason: {"EXCLUDED_M2_NOT_AVAILABLE": 4, "EXCLUDED_SUPPORT_BELOW_THRESHOLD": 345}.
- Main Spearman rho = 0.5142848509421646, Kendall tau = 0.3698756315199158, top-10% overlap = 0.11267605633802817, decile-divergence rate = 0.37464788732394366.

## Exp1B

- Prediction records: HISTORY:MATERIALIZED/CURRENT:MATERIALIZED.
- Current-only comparator: MATERIALIZED (budget_identical_to_reference=True, calibration_path_identical_to_reference=True).

## Remaining gates

- G2: M3 non-A00 / M4 production mapping freeze before comparison/ranking upgrade.
- G3: freeze `PAPER_OUTPUT_SPEC_V1.json` before Test.

