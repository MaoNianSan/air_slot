# D3 Warning Probability And Artifact Freeze

Status: IMPLEMENTED_MODEL_FROZEN_INFERENCE_NOT_RUN

## Probability Contract

The principal warning event is the strict event `D_TO_POST_GT_30`. For each
decision node, signed M1 produces aligned joint scenarios and derives:

`D_TO = max(0, DELTA_OB + T_TX - train-frozen taxi reference)`

The warning probability is the normalized weighted scenario frequency for
`D_TO > 30`. It uses the existing explicit target-bin representative values,
records whether a tail representative participated, and never drops scenarios
with missing support. If the train-frozen Data2 taxi reference or any scenario
`D_TO` is unavailable, the whole decision node abstains.

## Frozen Model

The final model is a byte-identical copy of signed W30, H32, seed `20260813`.
The seed is the first pre-registered W seed, not the seed with the best observed
Development NLL. The manifest validates signed H/W evidence, cache identity,
checkpoint hash, target order, signed support, and zero Final Test access.

## Execution Boundary

- H/W retraining: `FALSE`
- full Development warning inference: `NOT_RUN`
- warning operating point: `NOT_FROZEN`
- Final Test access count: `0`
- `paper_full`: `FALSE`

Full Development warning inference requires a separate operating-point freeze
covering the FPR statistical unit, probability-threshold tie rule, abstention
denominator, and principal Development scenario budget. Those choices are not
silently inferred from `target_fpr: 0.10`.
