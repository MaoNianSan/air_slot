# A00 Baseline Gate V2 — modification instruction and minimal rerun

## Status and scope

- decision id: `A00_BASELINE_GATE_V2_20260826`
- status: `IMPLEMENTATION_AUTHORIZED`
- source question: prevent a cost-free, universally available A00 baseline from being reported as an operational recovery recommendation when all non-A00 actions remain factual-eligibility `UNKNOWN` and response `SCENARIO_ASSUMPTION`.
- non-goals: no retraining; no modification of frozen response parameters, registries, V1 artifacts, TeX, Final Test split, or paper-full run.

## Binding instruction

1. `A00` is a counterfactual baseline, never an operational recommendation.
2. An operational recommendation may contain only a non-A00 action satisfying all three conditions at the decision node: `eligibility_state=TRUE`, `response_support=SUPPORTED`, and finite conditional objective.
3. `UNKNOWN`, `SCENARIO_ASSUMPTION`, unsupported, or non-finite non-A00 actions remain visible in conditional diagnostic records but are excluded from operational selection. They must never be silently promoted to A00.
4. If no qualifying non-A00 action exists, emit one typed abstention: `ABSTAIN_NO_FACTUALLY_ELIGIBLE_NON_A00`, `ABSTAIN_NO_FACTUALLY_SUPPORTED_NON_A00`, or `ABSTAIN_NO_FINITE_SUPPORTED_NON_A00`.
5. Conditional ranks retain the label `conditional`; they are not action recommendations. The conditional summary must count all finite actions, not only the already filtered Top-1 row.

## Minimal rerun contract

- Read the existing calibrated Development-cohort action-risk parquet only.
- Materialize a new V2 conditional-rank audit and a V2 A00-gated recommendation artifact under new output roots.
- Expected current result: all node-band records abstain because the current 22 non-A00 actions are `UNKNOWN` / `SCENARIO_ASSUMPTION`; this is a correctness outcome, not a failure to be repaired by changing A00 or response parameters.
- Required checks: focused unit tests; V2 output schema; 1,769 decision nodes x three valuation bands; zero A00 recommendations; frozen V1 file hashes unchanged; no Final Test split access.

## Evidence required before a future non-A00 recommendation

For each action, provide decision-time legal factual eligibility, action-specific authority/resource evidence, and response support upgraded beyond scenario-only parameters. A future study must use a new versioned contract and an independent evaluation; no post-hoc reduction of A00's objective is permitted.
