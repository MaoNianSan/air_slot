# Draft result entry points

Use the `*_summary.json` file first, then inspect the matching metrics and
execution manifest. These are Development artifacts. Every current protocol
manifest records `paper_result: false`; they are draft-supporting evidence, not
Final Test or paper-full results.

| Experiment | First file | Metrics / detail | Current interpretation |
| --- | --- | --- | --- |
| Exp1 | `artifacts/experiment/exp1_full_development/exp1_summary.json` | `EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json`, `EXP1_FULL_DEVELOPMENT_STATE_METRICS.json` | Full Development state/history comparison; decision relevance is not run |
| Exp2 | `artifacts/experiments/exp2/full_development_v1/exp2_summary.json` | `EXP2_FULL_DEVELOPMENT_METRICS.json` | Development evaluation with explicit gated/not-run results |
| Exp3 | `artifacts/experiments/exp3/full_development_v1/exp3_summary.json` | `EXP3_FULL_DEVELOPMENT_METRICS.json` | Conditional five-anchor diagnostic; formal multi-action ranking not run |
| Exp4 | `artifacts/experiments/exp4/full_development_v1/exp4_summary.json` | `EXP4_FULL_DEVELOPMENT_METRICS.json`, `EXP4_DATA1_BOUNDED_ACCEPTANCE.json` | Data2 baselines complete; Data1 is bounded adapter/applicability only |

## What not to use as a paper headline

- `outputs/real_smoke/`: bounded smoke and contract-chain evidence.
- `outputs/runtime/`: runtime, foundation, or M1 fast-path evidence.
- `artifacts/diagnostics/`: gate packets, audits, and versioned diagnostics;
  use only when the adjacent manifest identifies the intended status.
- `artifacts/_archive/`: historical or temporary material, including the
  archived Exp2 temporary package.

## Draft workflow

1. Start with the experiment summary and execution manifest.
2. Copy only metrics whose status and support scope are `SUPPORTED` or an
   explicitly stated Development/conditional scope.
3. Preserve `ABSTAIN`, `NOT_RUN`, `BLOCKED`, and `paper_result: false` in the
   draft; do not turn a Development number into a paper claim.
4. Use `reports/` and `docs/reconciliation/` for interpretation and claim
   boundaries; use the JSON/CSV/Parquet files above for exact values.
