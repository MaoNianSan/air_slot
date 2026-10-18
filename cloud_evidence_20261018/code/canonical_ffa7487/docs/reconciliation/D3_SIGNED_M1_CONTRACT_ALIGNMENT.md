# D3 Signed M1 Contract Alignment

Status: PERMANENTLY_FROZEN

## Formal M1 Contract

The Development refreeze uses the ordered stochastic chain:

`R_IB -> DELTA_OB -> T_TX`

`DELTA_OB` is the signed number of minutes from the successor CRS scheduled
departure to the realized off-block departure. It is a post-hoc
`TRAIN_LABEL` / `EVAL_OUTCOME`, never decision-time inference evidence.

`R_OB = max(0, DELTA_OB)` is a scenario compatibility value, not an
independent M1 head. `T_OB`, `T_TO`, and `D_TO` are derived from the same joint
draw. In particular, `D_TO = max(0, DELTA_OB + T_TX - taxi_reference)` where
the taxi reference is the existing train-frozen Data2 reference. A missing
reference yields unavailable `D_TO`, never zero.

## Ownership And Data Boundary

PRE remains responsible for canonical CRS departure, realized departure,
TaxiOut, episode/node/split/support/evidence material, and V5 containment.
M1 converts those typed outcomes to labels, owns the signed bins and joint
scenario logic, and does not read BTS data. `exp/exp1/development/signed_refreeze.py`
owns only Development H then W orchestration.

The Data2 schedule reference remains CRS based. The signed realized departure
is not exposed in PRE inference features before `POST_OB_PRE_TO`.

## Permanent Development Freeze

The new cache is `M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1`; it is separate from
the historical cache and is guarded against Final Test access and cross-split
episodes. Its signed finite support is -180 through +180 minutes at 5-minute
starts, with explicit underflow and overflow classes.

Historical `m1_hstar_evidence.json` and `m1_wstar_evidence.json` remain
unchanged. Human decision `D3_SIGNED_M1_H_W_REFREEZE` permanently freezes the
signed-target evidence result at `H=32` and `W=30`. The scientific foundation
now points to `m1_signed_hstar_evidence.json` and
`m1_signed_wstar_evidence.json`; it no longer exposes `R_OB` as a stochastic
support parameter.

The final warning-model artifact is a byte-identical freeze of the first
pre-registered W seed (`20260813`). This rule does not select the best observed
Development seed. Its manifest records the signed evidence, cache, source
checkpoint, target chain, and zero Final Test access. Warning probability is
the weighted aligned-scenario frequency of the strict event `D_TO > 30`, with
missing train-frozen taxi reference causing node-level abstention.

Full Development warning inference and warning operating-point selection have
not run.
