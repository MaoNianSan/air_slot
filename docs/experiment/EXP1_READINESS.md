# Exp1 Readiness

Scientific contract: test why the information pathway and state dependence are necessary.

## Exp1A: `FULL` versus `NO_DIRECT_REUSE`

| Requirement | Current capability | Status |
| --- | --- | --- |
| decision input adapter | `M1Service` consumes typed PRE state; `BaseRunner` does not | `PARTIAL` |
| full frozen pathway | PRE -> M1 typed boundary exists | `PARTIAL` |
| remove only direct-reuse pathway | no named transform or exclusion contract exists | `BLOCKED` |
| prohibit raw-information bypass | model tests and PRE/M1 boundaries prohibit arbitrary observed-state injection and raw-reader access | `ALIGNED` |
| state-only execution | M1 `STATE_AWARE` path exists, but it is not the same thing as a scientifically defined `NO_DIRECT_REUSE` variant | `PARTIAL` |
| paired execution on identical cohort/seeds | common pairing/RNG helpers exist; Exp1 runner does not enforce them | `STALE` |

`NO_DIRECT_REUSE` is absent from `configs/evaluation/exp1.yaml`, `exp/exp1/variants.py`, and `exp/exp1/runner.py`. The existing `CURRENT` history variant must not be relabelled as `NO_DIRECT_REUSE`: current-node history length and cross-stage direct information reuse are different interventions.

Implementation readiness requires an experiment-owned adapter that explicitly lists which already-admissible typed inputs are removed while preserving all other model, cutoff, calibration, scenario, and seed identities. It must never read raw data or create replacement proxy values.

## Exp1B: `CURRENT`, `FIXED_HISTORY`, `ADAPTIVE_HISTORY`

| Requirement | Current capability | Status |
| --- | --- | --- |
| `CURRENT` | `model/M1/history.py::current_history` returns only the current legal node | `ALIGNED` |
| `FIXED_HISTORY` | closed `[t-W,t]` selector on the five-minute grid | `ALIGNED` |
| `ADAPTIVE_HISTORY` | full causal prefix inside one episode | `ALIGNED` |
| history-window control | positive five-minute-aligned window required; future/cross-episode history rejected | `ALIGNED` |
| M1 input contract | typed `PREState` sequence and M1 validation exist | `ALIGNED` |
| current V2 artifact support | historical Exp1 artifacts are V1/HISTORICAL_ONLY | `BLOCKED` |
| new paired evaluator | old warning evaluator targets historical D_TO warning semantics and old scientific question | `REWRITE` |

The reusable component is the history selector, not the historical H/W selection or warning freeze. The old H/W evidence, signed checkpoint, scenario artifact, warning probabilities, and lead-time results remain provenance only and must not be treated as a V2 baseline.

## Required new experiment boundary

The new Exp1 runner should:

1. load one declared cohort and frozen chain identity;
2. build `FULL` and `NO_DIRECT_REUSE` through an explicit input-transform contract;
3. build the three history views through `model.M1.history.represent_history`;
4. preserve split, model family/version, calibration, scenario count, scenario seed, downstream interfaces, and metric definitions across paired comparisons;
5. emit predictive and decision/risk metrics with support-aware denominators;
6. reject legacy V1 scenario artifacts and retrospective leakage inputs.

## Tests required before implementation can be called ready

- transform changes only the declared direct-reuse fields;
- transform never increases support or substitutes missing values;
- raw readers/adapters are not imported by Exp1;
- CURRENT/FIXED/ADAPTIVE use identical episode/node cutoffs and never cross episode boundaries;
- repeated runs preserve variant and source hashes;
- historical V1 artifacts are rejected as principal inputs;
- unsupported M3/M4 paths remain `BLOCKED`, not zero-filled.

`EXP1_STATUS = BLOCKED_PENDING_REWRITE`

