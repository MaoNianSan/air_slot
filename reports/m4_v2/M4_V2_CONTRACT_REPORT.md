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
publication gate = M4_PUBLICATION_GATE_V1
```

## Repository contract

- `scientific.yaml` selects atomic actions, M2 V2, M3 V4, PRE Core V2 R2/R3
  support, stable shared draw indices, weighted Mean-CVaR, and Ranking@1/2/3/5.
- `config.py` rejects retired decision-value fields and strictly validates draw
  pairing, risk weights, ranking depths, evaluation booleans, and evaluation
  output isolation from `output/m4`.
- `AUTHORITATIVE_CODE` contains every active `src/m4/*.py` formal file and
  excludes M4 V1 legacy audit files.
- The main pipeline retains M3 contract, parameter-freeze, and formal-library
  gates before constructing any formal M4 input.

## Ranking and publication

The only M4 score order is:

```text
risk_score
expected_total_post_loss_rmb
cvar90_post_loss_rmb
expected_implementation_cost_rmb
action_id
```

The shared authoritative-order prefix builder validates contiguous supplied
ranks, then performs prefix selection and explicit null padding without a
second score sort.

`PublicationGateResult` records both `allowed` and `reason_codes`. Formal mode
alone is insufficient: PRE formal evidence, M2 formal/frozen valuation, M3
freeze/library/publication identity, M4 contract, stage/evidence safety, result
status, and test-only isolation are checked independently.

## Evaluation and output

Formal files are fully written and hashed in a staging bundle before the bundle
is published. Test-only artifacts cannot enter formal output. Evaluation reads
the frozen artifact only after publication, uses the sole `evaluation.m4`
configuration path, writes outside the formal bundle, and cannot change the
formal hashes or formal status.
