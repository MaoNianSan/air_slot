# AirSlot V2 Freeze R2 Correction Report

## Status

- Phase: `PHASE_6_R2_FREEZE_AUTHORITY_RECONCILIATION`.
- Status: `SCIENTIFIC_FREEZE_R2_ACTIVE`.
- Scope: `STAGE2_SOLVER_AUTHORITY_ONLY`.
- Parent freeze: `v2-scientific-freeze` (`35d5fe1896dd9e17be92bec601f87ec33adb4d56` -> `d29fc769e74d6b46f86d3fdf7db18b3f9936f8b1`).
- Parent registry remains byte-identical: `sha256:2b89976da5158f0fee87222daef33a8b3b617d61ece94ade00a001869134afdd`.
- R2 activation tag: `v2-scientific-freeze-r2`.
- Activation tag target: `RESOLVED_AFTER_COMMIT`; the complete R2 frozen repository state is defined by annotated tag resolution.
- R2 registry artifact hash: `sha256:4e7d3bb454e83779e6cbb592d4cf9d6ffddc0edf3435a7bc3d2822e4523417f2`.
- R2 registry file SHA-256: `sha256:15c1e8bf5ec5fbb5ee783595a124b1255b550d7d7bc96e34b2cd3df0a4e88e6f`.
- Reconciliation artifact hash: `sha256:f1e5a3ac42650c48e4f94c2f45de69b9f4ca6302f8de3ab3806788a4c29434ee`.

## Authority Reconciliation

- Formal solver: `PYOMO_HIGHS`.
- Parity oracle: `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`.
- Objective perturbation: `NONE`.
- Long-term deviation: `false`.
- Tie rule: `u*=min{u in U_i(theta): J_i(u)=min J_i}`.
- Tie implementation: two-stage lexicographic HiGHS solve; first minimize `J`, then minimize `u` subject to `J <= J* + tau`.
- `M3_NUMERICAL_COMPARISON_TOLERANCE = 1e-06`; it is `NOT_A_SCIENTIFIC_PARAMETER`.
- Diagnostics `tie_break_applied` and `near_tie_candidate_count` are computational audit fields only.

## Decision Equivalence

- Corpus: all available non-Test Stage-II validation fixtures, closed over their admissible specification grid.
- Actionable cases: `720`.
- Typed non-actionable cases: `2`.
- Action disagreements: `0`.
- Tie-break cases: `2`.
- Maximum near-tie candidate count: `2`.
- Maximum objective absolute error: `0.0` (tolerance `1e-06`).
- Maximum recoverable-value absolute error: `0.0` (tolerance `1e-06`).
- Action equality is exact; objective and `V` parity use only the declared numerical comparison tolerance.
- TAXI/COMP remain `NOT_ACTIONABLE`, singleton action set `{0}`, solver `NOT_RUN`, and undefined recoverable value.

## Boundary

- No scientific parameter, estimand, feasible set, state transition, consequence definition, objective, or evaluation population changed.
- M1 was not retrained and no scientific output was recomputed.
- No Final-Test path was read or written; historical access total remains `1`, current R2 increment is `0`.
- Phase 7 Gate B was not entered; human release is still required.
- The original Phase 6 registry and `v2-scientific-freeze` tag remain immutable.
