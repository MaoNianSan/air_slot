# MODEL_MANUSCRIPT_RECONCILIATION_BEFORE

Phase 0 read-only audit - manuscript/code semantic conflicts for
`AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION` (2026-08-19).

Authority: latest manuscript definition > this reconciliation spec > scientific
config/registries > current code > historical docs/outputs.

Audited modules: `model/PRE`, `model/M1`, `model/M2`, `model/M3`, `model/M4`,
`model/common`, `tests`, scientific config, registries, `formal/`, `exp/`,
`validation/`, `docs/`.

## Conflict table

| Conflict ID | Module | Current code | Latest manuscript definition | Scientific severity | Required change | Affected files | Affected tests | Needs human decision? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BEFORE-001 | M1 | Formal stochastic targets `R_IB -> DELTA_OB -> T_TX`; `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` derived from the raw sum | Formal successor contract `D_OB >= 0`, `D_TX >= 0`, `D_TO = D_OB + D_TX` per scenario; `DELTA_OB`/`T_TX` are internal auxiliaries only | BLOCKING | Replace formal target semantics with `R_IB, D_OB, D_TX` (D_TO derived); mark `DELTA_OB`/`T_TX` as `INTERNAL_AUXILIARY` | `model/M1/semantics.py`, `model/M1/contracts.py`, `model/M1/summaries.py` | `tests/m1/test_signed_ob_contract.py`, `tests/contract/test_experiment_v5_contract.py` | No |
| BEFORE-002 | M1 | `AlignedScenario` exposed only `r_ib_minutes/delta_ob_minutes/t_tx_minutes` with no formal `D_OB/D_TX/D_TO` fields or identity validator | Joint scenario object with `d_ob_minutes`, `d_tx_minutes`, `d_to_minutes`, supports, and hard validator `D_TO == D_OB + D_TX` | BLOCKING | Add computed formal fields and per-scenario identity validator to `AlignedScenario` | `model/M1/contracts.py` | `tests/m1/test_signed_ob_contract.py` | No |
| BEFORE-003 | M1 | Batched warning path (`warning.py`) computes `d_to = DELTA_OB + T_TX - taxi_ref` (raw old identity) | `D_TO = D_OB + D_TX` per scenario; D_TO identity has a single authoritative definition in M1 semantics | MAJOR | Derive batched `D_TO` from clamped `D_OB`/`D_TX` component values | `model/M1/warning.py` | `tests/m1/test_batched_warning_probability.py`, `tests/reconciliation/test_m1_joint_identity.py` | No |
| BEFORE-004 | M1 | Realized `D_TO` in `warning_preparation.py` used raw `DELTA_OB + T_TX - taxi_ref` | Per-scenario identity `D_OB + D_TX` | MAJOR | Update realized value to `max(0, delta) + max(0, taxi_out - reference)` | `model/M1/warning_preparation.py` | `tests/m1/test_batched_warning_probability.py` | No |
| BEFORE-005 | M2 | Drivers rebuilt takeoff delay from `DELTA_OB + T_TX - taxi_reference` (duplicated M1 state) | M2 consumes the formal aligned scenario `D_OB/D_TX/D_TO` and never reconstructs M1 delay state | BLOCKING | Rewrite `native_quantities` to consume `d_ob_minutes/d_tx_minutes/d_to_minutes`; abstain when formal fields are absent | `model/M2/drivers.py`, `model/M2/mapper.py`, `model/M2/context.py` | `tests/m2/test_mapping.py`, `tests/m2/test_context.py`, `tests/reconciliation/test_lineage_and_m2.py` | No |
| BEFORE-006 | M2 | `ValuationRegistry` conflated CU normalization and monetary semantics; `constructed_value_cu` treated as valuation | Strict separation: native `q_k` -> CU `C_k^CU` (train-frozen) -> money `L_k^m` (M4); two registries | BLOCKING | Introduce `CUNormalizationRegistry` in `model/common`; make `ValuationRegistry` a deprecated alias of `M2CUNormalizationAdapter` | `model/common/cu_normalization.py`, `model/M2/valuation.py`, `model/M2/freeze.py`, `model/M2/contracts.py` | `tests/m2/test_freeze_registry.py`, `tests/m2/test_mapping.py` | No |
| BEFORE-007 | M4 | Ranking summed raw CU then ranked (`C_a^CU -> sum -> J -> rank`) | Ranking occurs in a selected monetary system: `C_a,k^CU -> L_a,k^m -> sum_k -> mean/VaR/CVaR -> J^(lambda,alpha),m -> ranking` | BLOCKING | Apply `MonetaryMappingRegistry.to_money` per scenario before aggregation; no raw-CU fallback | `model/M4/post_action.py`, `model/M4/ranking.py`, `model/M4/lanes.py` | `tests/m4/*`, `tests/reconciliation/test_cu_money_ranking.py` | No |
| BEFORE-008 | M4 | `M4DecisionRequest` carried no monetary contract; missing valuation could fall back to raw CU ranking | Request carries `monetary_system`, `monetary_mapping_registry_id`, `monetary_mapping_registry_hash`; unfrozen mapping => authoritative ranking unavailable | BLOCKING | Add monetary fields to the typed request and hard-check registry identity/hash | `model/M4/contracts.py`, `model/M4/decision.py`, `model/M4/results.py` | `tests/m4/test_decision.py`, `tests/m4/test_typed_response_closure.py` | No |
| BEFORE-009 | M3 | Single `ResponseProvenance` enum could not express hybrid evidence or structured support provenance | `Pi_a` carries structured `ActionResponseSupport`: evidence_bases, source_refs, support_state, freeze_id, parameter_version, interpretation_scope, hybrid flag | MAJOR | Add structured support contract and legacy mapping; surface on instantiated candidates | `model/M3/contracts.py`, `model/M3/instantiate.py` | `tests/m3/*`, `tests/reconciliation/test_cu_money_ranking.py` | No |
| BEFORE-010 | M4 | No monetary lineage on `ActionEvaluation`; CU scope id used `valuation_registry_id` | Monetary lineage preserved: `monetary_system`, `monetary_mapping_registry_id`, `monetary_mapping_registry_hash`; scope renamed `cu_normalization_registry_id` | MAJOR | Rename scope field, carry monetary lineage on evaluations, include in ranking identity | `model/common/estimand.py`, `model/M4/results.py`, `model/M4/ranking.py` | `tests/contract/test_p0_estimand.py`, `tests/fixtures/p0_p1_contracts.py` | No |
| BEFORE-011 | M1 | `m1_stochastic_targets` frozen as `[R_IB, DELTA_OB, T_TX]` (training heads) with no formal output contract in config | Formal output contract is `R_IB, D_OB, D_TX` plus derived `D_TO` | MINOR | Add a new frozen `m1_formal_output_contract` parameter; leave training targets untouched | `configs/scientific/foundation.yaml` | `tests/contract/test_configuration_layers.py` | Yes (new frozen config value, provenance-only, no final-test use) |
| BEFORE-012 | M1 | FAST path was only a callback; no ARX/LightGBM distributional implementation | FAST and STATE_AWARE share feature/target/output/support/scenario schema, differ only in history representation and model class | MAJOR | Add coded ARX-LightGBM distributional predictor sharing the distribution schema; keep DEVELOPMENT_ONLY | `model/M1/fast_path.py`, `model/M1/service.py` | `tests/reconciliation/test_fast_path.py` | No (implementation status DEVELOPMENT_ONLY; formal freeze deferred) |
| BEFORE-013 | docs/manuscript | `docs/manuscript/EXPERIMENTAL_EVALUATION_V5_DRAFT_20260818.md` still defines `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` and the `R_IB -> DELTA_OB -> T_TX` chain | Manuscript is authority; code follows the new identity | DOCUMENTATION | Do not edit manuscript here; record as `MANUSCRIPT_STALE` | `docs/reconciliation/MANUSCRIPT_CODE_STALE_ITEMS.md` | none | Yes (paper team decision) |
| BEFORE-014 | docs/reconciliation | `D3_SIGNED_M1_CONTRACT_ALIGNMENT.md` and `SCIENTIFIC_CONFLICT_LEDGER.md` preserve the old `D_TO = max(0, ...)` identity as PERMANENTLY_FROZEN | Historical frozen docs conflict with the new manuscript identity | DOCUMENTATION | Keep as historical evidence; mark stale in reconciliation reports | `docs/reconciliation/*` | none | No |
| BEFORE-015 | registries | `registries/m2_data2_formal_cu_v1.json` native-quantity definition text still uses `max(0, DELTA_OB + T_TX - taxi_reference)` | Formal native quantities consume `D_OB/D_TX/D_TO`; registry hash is train-frozen | MINOR | Do not silently rewrite a frozen registry; record definition-text drift as CONFIG_STALE | `docs/reconciliation/MANUSCRIPT_CODE_STALE_ITEMS.md` | `tests/experiments/test_development_readiness.py` | Yes (re-freeze registry text + hash) |
| BEFORE-016 | M2 | `M2ScientificContext.taxi_reference` remained a context field although M2 no longer reconstructs D_TO from it | M2 consumes formal `D_TX`; taxi reference is not a delay-state input | MINOR | Keep the context field (R_operating no longer depends on it); verify no component uses it as a delay-state input | `model/M2/drivers.py`, `model/M2/context.py` | `tests/m2/test_context.py`, `tests/m2/test_mapping.py` | No |

## Severity summary

- BLOCKING: 6 (BEFORE-001, 002, 005, 006, 007, 008)
- MAJOR: 5 (BEFORE-003, 004, 009, 010, 012)
- MINOR: 3 (BEFORE-011, 015, 016)
- DOCUMENTATION: 2 (BEFORE-013, 014)

## Phase 0 conclusion

All BLOCKING and MAJOR conflicts were resolvable without additional human
scientific decisions.  The three flagged `HUMAN_DECISION_REQUIRED` items are:
(1) adding the frozen `m1_formal_output_contract` config value,
(2) manuscript draft wording (`MANUSCRIPT_STALE`), and
(3) re-freezing the M2 registry definition text/hash.  See the AFTER report
and `MANUSCRIPT_CODE_STALE_ITEMS.md` for resolution status.
