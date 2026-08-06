# M1-M2 V2 Semantic Fix Report

Date: 2026-08-06

```text
M1_CORE_MODEL_CHANGED = NO
M1_CONTRACT_STATUS = PASS
M1_SAMPLING_STATUS = PASS
M2_MISSING_VALUE_SEMANTICS = PASS
M2_CONTEXT_DIRECTION_STATUS = PASS
M2_SUBITEM_DEPENDENCY_STATUS = PASS
PRE_TO_M2_CONTEXT_WIRING = PARTIAL
M2_TAIL_GATE_STATUS = PASS
M2_CU_RMB_STATUS = PASS
M2_PARAMETER_FREEZE_STATUS = NOT_YET_DONE
M2_FORMAL_RECONSTRUCTION_STATUS = NOT_YET_RUN
M3_CONTRACT_STATUS = MISMATCH
M4_CONTRACT_STATUS = NOT_YET_MIGRATED
GLOBAL_RERUN_ALLOWED = NO
```

## Scope Boundary

- No file under `overall_run/src/m1/model`, M1 training, or M1 calibration was changed.
- The single one-layer GRU, hidden sizes, IB/OB/TX heads, five-minute distributions, fixed episode random numbers, per-target temperature scaling, and training-only empirical tail design remain unchanged.
- No independent takeoff head, copula, flow, neural loss model, online update, cross-module training, or M3/M4 compatibility layer was added.
- No PRE rebuild, M1 training/calibration/resampling, M2 formal reconstruction, middle/full run, `overall_adv`, or `part_adv` was executed.

## Missing-Value Semantics

Removed the numeric fallbacks in the M2 formal path that previously used `value or 0.0`, `max(context, 1.0)`, and equivalent behavior. `RuntimeEvents` now carries four explicit maps:

```text
event_value
event_status
event_semantics
event_source
```

Event statuses are `AVAILABLE`, `PROXY_AVAILABLE`, `MISSING`, `UNSUPPORTED`, and `TAIL_UNRESOLVED`. Observed zero and predicted zero remain real zero values. `None`, NaN, unsupported inputs, and unresolved tail values do not produce zero quantity or zero CU. An active subitem receiving an unavailable or non-finite primitive raises `M2_SUBITEM_INPUT_CONTRACT_ERROR`.

## Context Direction

`CONTEXT_FIELD_REGISTRY` is the single direction contract. Unit-interval lower-risk fields are converted before quantity reconstruction:

```text
execution_window_pressure = 1 - execution_window_margin
resource_scarcity = 1 - resource_availability
infrastructure_constraint = 1 - infrastructure_flexibility
connection_pressure = 1 - connection_slack  # only when pressure is absent
```

The conversion rejects values outside `[0, 1]`; it does not apply `1-x` to unnormalized data. `R_SCARCITY` consumes `resource_scarcity`, never positive `resource_availability`. Context multipliers require explicit `gamma`, lower bound, and upper bound, and use `clip(1 + gamma*x, lower, upper)`. No formal numeric default was introduced.

## Central Dependency And Activation Gate

`overall_run/src/m2/dependencies.py` is the single dependency registry for all nine subitems. It covers required/all-or-any events, context, references, rule parameters, value parameters, proxy permission, resolved-tail requirements, and core-subitem status. `R_SCARCITY` implements an explicit OR across configured wait/taxi triggers.

Activation results are `ACTIVE`, `PROXY_ACTIVE`, `UNSUPPORTED`, `DISABLED_BY_CONFIG`, or `NOT_CONFIGURED`. Missing rule type, rule parameter, multiplier parameter, or `v_gj` is `NOT_CONFIGURED`, not a zero-valued loss.

The episode-level status is computed as follows:

- `VALID`: core and conditional candidates are configured and available, with no proxy or unresolved tail.
- `PARTIAL`: core reconstruction is supported, while a conditional subitem is unavailable or not configured.
- `PROXY_SUPPORTED`: at least one active subitem uses supported proxy evidence.
- `ABSTAIN`: core dependency failure, core parameter not frozen, PRE/M1 mismatch, sample alignment failure, or unresolved tail.

## PRE To M2 Wiring

`build_m2_context()` reads a validated `PublishedPreBundle`, preserves PRE identity/provenance, applies only registered normalization, and builds `M2ContextBundle`. `build_m2_input_from_pre()` is the formal construction path:

```text
PublishedPreBundle + M1ScenarioBundle
    -> M2ContextBundle
    -> M2InputBundle + separate ValuationContext
```

Valuation is not read from PRE. The wiring status is `PARTIAL`, not `PASS`, because the current PRE Core V2 required schema does not contain every M2 risk field and the current status file reports `formal_fast_bundle_available=false`.

## Tail Gate

M1 horizon output now reports conditional resolved probability, unresolved probability mass, lower bound, upper bound, and formal availability. Unresolved samples are not counted as false events.

M2 separates formal and resolved-only summaries. If any loss-relevant sample is unresolved:

```text
formal_q95_available = false
formal_cvar90_available = false
m4_gate_status = M2_TAIL_NOT_READY_FOR_M4
```

Only fields named `resolved_only_*` retain descriptive resolved-sample values. No complete Mean-CVaR object is exposed as M4-ready.

## Summary, Currency, Correction, And Joint Evaluation

- Mean losses are named `channel_mean_losses` and `subitem_mean_losses`.
- Contribution ratios are named `channel_loss_shares` and `subitem_loss_shares`; zero total loss returns `ZERO_TOTAL_LOSS` rather than NaN or arbitrary equal shares.
- RMB mapping requires explicit F/P/R rates. Missing any rate raises `M2_CURRENCY_MAPPING_INCOMPLETE`.
- The current identity mapping remains explicitly configured as `1 CU = 1 RMB` for every channel.
- The disabled learned-correction interface now enforces `abs(delta) <= rho_g * max(structural, epsilon)` when enabled in a future labeled setting. This task did not train or enable a correction model.
- Joint evaluation reports the three requested joint-tail frequencies, residual correlations, and calibration availability without changing `CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING`.

## Downstream Gate

`overall_run/src/pipeline.py` still raises the real `M3_CONTRACT_MISMATCH`. The retired scalar M2-to-M4 test remains module-skipped, and M2 summaries expose `M2_TAIL_NOT_READY_FOR_M4` when CVaR is not formal. M3 and M4 are not migrated by this change.
