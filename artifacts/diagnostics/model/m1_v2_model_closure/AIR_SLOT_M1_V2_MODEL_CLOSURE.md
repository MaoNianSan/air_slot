# AIR_SLOT_M1_V2_MODEL_CLOSURE

```text
HEAD = 7127859c9be574d0209cd59ada757d46d7c7d897
```

## Source quality

```text
SOURCE_CLOCK_AUDIT = CLOSED
DST explained = 27
date-offset ambiguous = 1
isolated raw contradiction = 1
canonical timestamp changes = 0
cohort affected = 0
265 min JAX->EWR case = SOURCE_QUALITY_DIAGNOSTIC
```

## Final support

```text
support provenance = V2_SUPPORT_REFROZEN_AFTER_A2_B2
selection unit = TRAIN_EPISODE_BALANCED
T_IB_REMAINING_HAZARD = 360
D_OB = 210
D_TX = 60
bin width = 5
D_OB conditioning classes = 42 finite + tail
```

The principal V2 pipeline reads only:

- `m1_v2_t_ib_remaining_max_finite_minutes`
- `m1_v2_d_ob_max_finite_minutes`
- `m1_v2_d_tx_max_finite_minutes`

The V1 support names remain `LEGACY_V1_PROVENANCE_ONLY` and do not control the
principal V2 pipeline.

## Training objective

```text
old = active-row-count normalized
new = target-specific episode balanced

T_IB episode denominator = episodes with active T_IB_REMAINING_HAZARD
D_OB zero denominator = episodes with active D_OB
D_OB positive denominator = episodes with active positive D_OB
D_TX zero denominator = episodes with active D_TX
D_TX positive denominator = episodes with active positive D_TX
```

For each eligible component, active row weight is
`1 / active_node_count(episode, component)`. The five primitive terms are
T_IB hazard NLL, D_OB zero BCE, D_OB positive pinball, D_TX zero BCE, and D_TX
positive pinball.

## Episode balance tests

```text
single-node vs ten-identical-node episode = PASS for all five components
full-batch vs microbatch total loss = PASS
full-batch vs microbatch gradients = PASS within numerical tolerance
Development joint/primitive diagnostics = microbatch invariant
```

## B2

```text
feature schema unchanged = true
cache unchanged = true
labels unchanged = true
active masks unchanged = true
feature contract = 39 dynamic + 4 static = 43
feature schema hash = sha256:1f4b886a9bddc67f3fe72b977ea957cf5828b6cdd20dcc69655dcf3f2ec2972a
cache hash = sha256:157c0d555c40efd9d7dc5ecebc5dda60a902b855d42bdab9a3657aa601e6f919
```

## Hyperparameter status

```text
H32 = DEVELOPMENT_CANDIDATE
H candidates = {8, 16, 32}
H candidate update = AIR_SLOT_M1_V2_TUNING_PREFLIGHT_H_CANDIDATES_UPDATE
implicit H32 selection = forbidden
quantile levels = DEVELOPMENT_CANDIDATE_UNCHANGED
tuning authorized = false
```

## Validation

```text
focused/config/ownership/data-usage tests = 187 passed
Data Usage = PASS
PRE ownership = PASS
compileall = PASS
git diff --check = PASS
```

## Next

```text
M1_V2_TUNING_PREFLIGHT_H_READY = true
```

## Safety

```text
M1_TRAINING_RUNS = 0
TUNING_RUNS = 0
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = false
```
