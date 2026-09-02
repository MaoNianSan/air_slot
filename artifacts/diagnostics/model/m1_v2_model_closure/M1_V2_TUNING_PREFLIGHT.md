# M1_V2_TUNING_PREFLIGHT

Status: `M1_V2_TUNING_PREFLIGHT_H_READY`

Authorization: `false`

## Fixed model contract

- Features: `39 dynamic + 4 static = 43`.
- Supports: `T_IB_REMAINING_HAZARD=360`, `D_OB=210`, `D_TX=60`.
- Bin width: `5 minutes`.
- History: `FULL_ADAPTIVE_CAUSAL_PREFIX`.
- Objective: target-specific episode-balanced five-component joint loss.

## Principal Development metric

`EPISODE_BALANCED_JOINT_VALIDATION_LOSS`

This is the sum of the same five episode-balanced primitive terms used for
training:

- `T_IB_HAZARD_NLL`
- `D_OB_ZERO_BCE`
- `D_OB_POSITIVE_PINBALL`
- `D_TX_ZERO_BCE`
- `D_TX_POSITIVE_PINBALL`

Calibration is not applied during model selection. Calibration remains
post-selection probability calibration and diagnostic only.

## Narrow candidates

```text
H = {8, 16, 32}
learning rate = {0.001, 0.003, 0.01}
Adam weight decay = {0.0, 0.0001}
optimization duration epochs = {4, 8}
```

The protocol is staged and one-factor-at-a-time, not a Cartesian grid. It
allows at most seven unique candidate configurations per paired seed. H is
selected first at the reference optimizer setting. The smallest H within 0.5%
of the best paired mean Development loss is preferred; a larger H requires a
meaningful paired Development improvement.

Candidate update provenance:
`AIR_SLOT_M1_V2_TUNING_PREFLIGHT_H_CANDIDATES_UPDATE` (`2026-08-22`), scoped
to adding `H=8` only.

## Seed policy

```text
paired seeds = {20260813, 20260814, 20260815, 20260816, 20260817}
same seeds for every candidate = true
aggregate = mean across paired seeds
choose best observed seed = false
```

## Split roles

```text
Train = fit
Development = model/hyperparameter selection
Calibration = post-selection calibration/diagnostic only
Final Test = locked
```

## Not tuned

Feature set, support, bin width, history window, roll interval, and quantile
levels are not tuning variables in this protocol. The positive-quantile upper
tail remains a later closure item required before full-chain M4 CVaR work.

## Safety

```text
M1_TRAINING_RUNS = 0
TUNING_RUNS = 0
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = false
```

Stop and wait for human approval before any candidate run.

## Stage 1 preparation

`M1_V2_TUNING_STAGE1_MANIFEST.json` records the executable preparation for
`NO_HISTORY`, `H8`, `H16`, and `H32`. The no-history baseline disables the
history encoder and consumes only the current admissible observation/state
input. The manifest also records the read-only downstream artifact interface, including joint
scenario identity, scenario-derived marginal summaries, history lineage, and
the evaluation horizon grid `0,30,60,120,180,240,300,360,420,480` minutes.
