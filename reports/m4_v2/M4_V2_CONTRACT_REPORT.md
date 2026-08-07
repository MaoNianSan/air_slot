# M4 V2 Contract Report

Date: 2026-08-07

## Identities

```text
M4 contract = M4_CONTEXTUAL_RESIDUAL_RISK_V2
input contract = M4_M2_V2_M3_V4_INPUT_V1
output contract = M4_RESIDUAL_RISK_OUTPUT_V1
draw pairing = M4_STABLE_SHARED_DRAW_INDEX_V1
risk = M4_WEIGHTED_MEAN_CVAR_V1
ranking = M4_RANKING_1235_V2
```

M4 reuses `SUBITEMS_M2_V2`, `COST_CHANNELS`, `OutcomeCoverage`, and
`ParameterStatus`; it does not define a competing M2/M3 schema.

## Input Gates

M2 requires contiguous sample IDs, aligned episode/snapshot identity, finite
nonnegative weights, exact nine-subitem keys, exact F/P/R keys, and exact
subitem-to-channel-to-total identities. Missing loss is rejected, never filled
with zero.

M3 requires the V4 identities, 21 ordered actions, contiguous response draw
IDs, `[R,9]` recovery, `[R,3]` costs, finite ranges, hashes, and exact A00 zero
recovery/cost. Formal mode additionally requires parameter freeze `DONE`,
formal library `READY`, non-test-only identity, and publication permission.

## Scientific Boundaries

- PRE R2 may pass structural compatibility but cannot satisfy the R3 formal gate.
- PRE R3 requires input-rule and formula-registry hashes.
- Resource, crew, gate, ground-handler, and aircraft availability cannot be
  inferred from airport or ground pressure.
- Null lead time remains unconfigured; M4 does not replace it with zero.
- Stage compatibility is impossible without an explicit versioned mapping.
- Synthetic fixtures may produce test rankings but are never publishable.
- Evaluation reads frozen output and cannot alter formal files or decisions.
