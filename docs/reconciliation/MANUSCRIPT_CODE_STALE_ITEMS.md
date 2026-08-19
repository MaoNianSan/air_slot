# MANUSCRIPT_CODE_STALE_ITEMS

Classification of stale items found during `AIR_SLOT_MODEL_MANUSCRIPT_
RECONCILIATION` (2026-08-19).  Rule used: if the latest manuscript is clear
and the code is wrong, the item is `CODE_STALE` (code must change); the
manuscript is not marked stale to protect the code.

## CODE_STALE (fixed in this reconciliation)

| Item | Location | Old semantics | Resolution |
| --- | --- | --- | --- |
| M1 formal targets | `model/M1/semantics.py`, `model/M1/contracts.py` | `R_IB -> DELTA_OB -> T_TX` with raw `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` | `R_IB, D_OB, D_TX` formal; `D_TO = D_OB + D_TX` per scenario; auxiliaries marked internal |
| M1 batched warning D_TO | `model/M1/warning.py` | raw `delta + tx - taxi_ref` sum | clamped `D_OB` + `D_TX` components |
| M1 realized D_TO | `model/M1/warning_preparation.py` | raw identity | per-scenario `max(0, delta) + max(0, taxi_out - reference)` |
| M2 delay-state reconstruction | `model/M2/drivers.py` | rebuilt `takeoff` from `delta_ob + t_tx - taxi_reference` | consumes `d_ob_minutes/d_tx_minutes/d_to_minutes`; abstains otherwise |
| M2 valuation conflation | `model/M2/valuation.py`, `model/M2/freeze.py`, `model/M2/contracts.py` | one `ValuationRegistry` for CU+money | `CUNormalizationRegistry` (CU) + `MonetaryMappingRegistry` (money, M4) |
| M4 raw-CU ranking | `model/M4/post_action.py`, `model/M4/ranking.py`, `model/M4/lanes.py` | `sum CU` then rank | monetary conversion first; no raw-CU fallback |

## MANUSCRIPT_STALE (report only; not modified)

| Item | Location | Detail |
| --- | --- | --- |
| Manuscript D_TO identity | `docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md` (around lines 71-72) | Draft still defines `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` and the `R_IB -> DELTA_OB -> T_TX` chain as the formal model chain.  The manuscript is the scientific authority; the code now follows `D_TO = D_OB + D_TX`.  The draft needs a paper-team update. |
| Historical frozen docs | `docs/reconciliation/D3_SIGNED_M1_CONTRACT_ALIGNMENT.md`, `docs/reconciliation/SCIENTIFIC_CONFLICT_LEDGER.md` | Record the old `D_TO` identity as permanently frozen; they remain historical evidence and were not rewritten. |

## CONFIG_STALE

| Item | Location | Detail |
| --- | --- | --- |
| M2 registry definition text | `registries/m2_data2_formal_cu_v1.json` (`native_quantity_definitions`, `train_scale_artifact.definition`) | Text still uses `max(0, DELTA_OB + T_TX - taxi_reference)` for F_propagation/P_time.  The registry hash is train-frozen and the consumed arithmetic is in `model/M2/drivers.py`; a re-freeze of the definition text requires a human decision. |
| M1 config | `configs/scientific/foundation.yaml` | `m1_stochastic_targets` still names `DELTA_OB`/`T_TX` (training heads); resolved by adding the new frozen `m1_formal_output_contract` rather than changing the frozen training value. |

## TEST_STALE (fixed in this reconciliation)

| Item | Location | Old assertion | Resolution |
| --- | --- | --- | --- |
| D_TO identity test | `tests/contract/test_experiment_v5_contract.py` | asserted old identity behavior | per-scenario `D_OB + D_TX` identity test |
| Signed OB contract tests | `tests/m1/test_signed_ob_contract.py` | legacy `R_OB`-only semantics | formal `d_*` fields + identity assertions |
| M2 context/mapping tests | `tests/m2/test_context.py`, `tests/m2/test_mapping.py` | scenarios with legacy delay fields | formal scenario fields; no state reconstruction |
| M4 tests | `tests/m4/*` | `evaluate_decision` without monetary mapping | pass `monetary_fixture()`; typed request carries monetary triple |
| P0 estimand fixture | `tests/fixtures/p0_p1_contracts.py`, `tests/contract/test_p0_estimand.py` | `valuation_registry_id` | `cu_normalization_registry_id` |

## EXPERIMENT_STALE

| Item | Location | Detail |
| --- | --- | --- |
| Exp1 warning artifacts | `exp/exp1/development/`, stored warning-probability artifacts | computed under old D3 `D_TO` identity; historical evidence, not modified |
| Exp2 representations | `exp/exp2/representations.py` | operates on legacy `r_ob_minutes/t_tx_minutes` fields; user is rewriting Exp1-4 |
| Exp234 fast path | `exp/exp234/development_execution.py`, `exp/exp234/scenario_artifact.py` | `_fast_pre_rows` reconstructs old-identity `takeoff`; artifact rows lack formal `d_*` fields |
| Validation scripts | `validation/exp1_lead_quantiles_quick_20260818.py`, `validation/m1_horizon_accuracy_quick_20260818.py` | report text describes the old D_TO identity |

## Not stale

- `m1_stochastic_targets = [R_IB, DELTA_OB, T_TX]` remains correct for
  training heads; the new `m1_formal_output_contract` parameter records the
  formal output contract without disturbing the frozen training freeze.
