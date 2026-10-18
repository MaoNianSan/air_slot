# EXPERIMENT_IMPACT_MEMO

Compatibility audit of experiment code against the reconciled scientific
contract (`AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION`, 2026-08-19).

**User decision (2026-08-19): Exp1-4 are being rewritten.**  No experiment
code was migrated and no formal rerun was executed.  This memo records the
obsolete dependencies found by the read-only audit so the rewrite can avoid
them; the rewrite supersedes any code-level migration of the current
`exp/` implementations.

## Exp1 (warning model / operating point)

| Item | Value |
| --- | --- |
| Obsolete dependency | `exp/exp1/development/warning_evaluation.py`, `warning_operating_point.py`, `warning_freeze.py` consume `model.M1.warning` warning probabilities for the strict `D_TO > 30` event. |
| Contract change | `D_TO` is now `D_OB + D_TX` per scenario (was `max(0, DELTA_OB + T_TX - taxi_ref)`); the batched warning path in `model/M1/warning.py` was updated accordingly. |
| Old outputs stale? | Stored warning-probability artifacts were computed under the old D3 identity; they are historical evidence and were not modified. |
| Rerun required? | Yes, under the rewrite, using the reconciled warning path and the frozen signed M1 artifact (if the warning event semantics are retained). |

## Exp2 (scenario corruption / point collapse)

| Item | Value |
| --- | --- |
| Obsolete dependency | `exp/exp2/representations.py` `point_collapse`/`corrupt_scenario_lineage` operate on legacy fields `r_ib_minutes`, `r_ob_minutes`, `t_tx_minutes`. |
| Contract change | Formal scenario fields are now `d_ob_minutes/d_tx_minutes/d_to_minutes`; `r_ob_minutes` remains a compatibility alias of `D_OB`. |
| Old outputs stale? | Historical exp2 artifacts unchanged; their D_TO values predate the reconciled identity. |
| Rerun required? | Under the rewrite, regenerate from reconciled scenario artifacts and lineage helper (`model/common/scenario_lineage.py`). |

## Exp3 (ablations)

| Item | Value |
| --- | --- |
| Obsolete dependency | `exp/exp3/ablations.py` operates on formal consequence rows; `model/M2` output rows now carry `cu_normalization_registry_id` (renamed from `valuation_registry_id`). |
| Contract change | Row field rename only; value semantics unchanged for supported rows. |
| Old outputs stale? | Historical artifacts remain as-is. |
| Rerun required? | Under the rewrite, consume the renamed row field. |

## Exp4 (portability / strata)

| Item | Value |
| --- | --- |
| Obsolete dependency | `exp/exp4/` consumes M1/M2 outputs; M4 evaluation now requires a frozen monetary mapping for authoritative ranking. |
| Contract change | `evaluate_decision`/`evaluate_candidate` require a `MonetaryMappingRegistry`; no raw-CU fallback. |
| Old outputs stale? | Historical artifacts remain as-is. |
| Rerun required? | Under the rewrite, pass a frozen RMB mapping or accept `AUTHORITATIVE_DECISION_UNAVAILABLE`. |

## Exp234 development execution (not in the user's Exp1-4 rewrite scope)

| Item | Value |
| --- | --- |
| Obsolete dependency | `exp/exp234/development_execution.py` `_fast_pre_rows` still reconstructs `takeoff = max(0, delta_ob + t_tx - taxi_ref)` and `exp/exp234/scenario_artifact.py` writes legacy-identity `d_to_minutes`. |
| Contract change | Formal M2 mapper consumes `d_ob_minutes/d_tx_minutes/d_to_minutes`; the fast projection must mirror that (or be removed). |
| Old outputs stale? | Stored scenario artifacts lack formal `d_*` fields and use the legacy D_TO identity. |
| Rerun required? | Requires regeneration of the scenario artifact with formal fields plus a fast-path update; equivalence gate would fail otherwise. |

## Validation scripts

| Item | Value |
| --- | --- |
| Obsolete dependency | `validation/exp1_lead_quantiles_quick_20260818.py` and `validation/m1_horizon_accuracy_quick_20260818.py` describe `D_TO` with the old frozen identity in report text. |
| Contract change | None executed; report text is stale relative to the reconciled identity. |
| Old outputs stale? | Diagnostic artifacts remain as historical evidence. |
| Rerun required? | Only if the rewritten pipeline needs refreshed diagnostics. |

## Summary

- No formal rerun was executed; no stored experiment result was modified.
- Exp1-4 obsolete dependencies are listed for the rewrite.
- Exp234 and validation scripts carry legacy identity text; they are outside
  the rewrite scope and were not modified.
