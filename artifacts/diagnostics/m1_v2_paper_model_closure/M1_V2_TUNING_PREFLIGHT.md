# M1_V2_TUNING_PREFLIGHT

Status: `M1_V2_TUNING_PREFLIGHT_READY`

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
H = {16, 32}
learning rate = {0.001, 0.003, 0.01}
Adam weight decay = {0.0, 0.0001}
optimization duration epochs = {4, 8}
```

The protocol is staged and one-factor-at-a-time, not a Cartesian grid. It
allows at most six unique candidate configurations per paired seed. H is
selected first at the reference optimizer setting. If H16 and H32 are within
the existing 0.5% practical-equivalence rule, H16 is preferred; H32 requires a
meaningful paired Development improvement.

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
