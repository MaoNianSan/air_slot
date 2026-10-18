# MODEL_MANUSCRIPT_RECONCILIATION_AFTER

Status of `AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION` after the code,
contract, config, and test migration (2026-08-19).

## What changed per module

### PRE (unchanged contract)
- `PREState` remains the decision-time admissible information contract only.
- `information_cutoff <= decision_time` continues to be enforced on
  `DecisionNodeRecord`; future realized outcomes never enter `E_{<=t}`.

### M1 (formal successor contract)
- `model/M1/semantics.py` is now the single source of truth:
  - `M1_FORMAL_TARGETS = ("R_IB", "D_OB", "D_TX")`
  - `D_OB = max(0, DELTA_OB)`, `D_TX = max(0, T_TX - taxi_reference)`
  - `D_TO = D_OB + D_TX` per scenario; never a separately trained head
  - `DELTA_OB` / `T_TX` remain internal predictive auxiliaries
  - `R_OB` is a compatibility alias of `D_OB`
- `AlignedScenario` gained computed `d_ob_minutes`, `d_tx_minutes`,
  `d_to_minutes`, `d_ob_support`, `d_tx_support`, `d_to_support` and a hard
  validator: `D_TO == D_OB + D_TX` per scenario (tolerance 1e-6).
- `model/M1/warning.py` batched path now derives `D_TO` from clamped
  `D_OB`/`D_TX` components instead of the raw `DELTA_OB + T_TX - taxi_ref`
  sum; the object path (`warning_probability`) consumes the formal
  `AlignedScenario.d_to_minutes`.
- `model/M1/warning_preparation.py` realized `D_TO` uses the per-scenario
  identity `max(0, delta) + max(0, taxi_out - reference)`.
- FAST path closed with a coded ARX-LightGBM distributional predictor
  (`model/M1/fast_path.py`) that shares the STATE_AWARE distribution and
  scenario schema; status `DEVELOPMENT_ONLY` until a train-frozen artifact
  exists.

### M2 (formal input + CU separation)
- `model/M2/drivers.py` consumes `d_ob_minutes` / `d_tx_minutes` /
  `d_to_minutes` directly and never reconstructs M1 delay state; a
  legacy-only scenario (only `delta_ob_minutes`/`t_tx_minutes`/taxi ref)
  abstains instead of fabricating values.
- Dependency per manuscript: `F_execution <- D_OB`, `F_propagation/P_time/
  P_service <- D_TO`, `R_operating <- D_TX`, `F_continuity <- R_IB`.
- CU normalization (`q_k -> C_k^CU`) is a separate train-frozen
  `CUNormalizationRegistry` in `model/common/cu_normalization.py`.
- `ValuationRegistry` is now a deprecated alias of
  `M2CUNormalizationAdapter`; `ValuationRegistry.smoke()` is DEV-only and
  returns `CU_NOT_FROZEN` rows, never formal CU.

### M3 (structured response provenance)
- `model/M3/contracts.py` adds `EvidenceBasis`, `ActionResponseSupportState`,
  and `ActionResponseSupport` (hybrid-capable `Pi_a`): evidence_bases,
  source_refs, support_state, freeze_id, parameter_version,
  interpretation_scope, hybrid flag.
- `ActionTemplate`/`CandidateAction` carry optional `response_support`;
  `from_legacy_provenance` maps old `ResponseProvenance` enums to structured
  support; instantiated candidates surface it.

### M4 (monetary ranking)
- `M4DecisionRequest` requires `monetary_system`,
  `monetary_mapping_registry_id`, `monetary_mapping_registry_hash`.
- `evaluate_candidate` converts per scenario: `L_a^m = sum_k omega_k^m *
  C_a,k^CU`; `MONETARY_MAPPING_NOT_FROZEN` when unfrozen; no raw-CU fallback.
- `assign_lane` never grants FORMAL without a frozen monetary mapping; a
  structured `response_support` with non-SUPPORTED state blocks FORMAL.
- Ranking identity now includes CU + monetary registry lineage + hash chain.
- `evaluate_decision` defaults to `MonetaryMappingRegistry.not_frozen()`, so
  authoritative ranking is unavailable unless a frozen RMB registry is passed.

### model/common (new shared contracts)
- `cu_normalization.py`: `CUNormalizationRule`, `CUNormalizationRegistry`.
- `monetary_system.py`: `MonetarySystem.RMB`, `MonetaryMappingRegistry`,
  `MonetaryMappingStatus`, `not_frozen()` default.
- `scenario_lineage.py`: `scenario_lineage_key`, `validate_same_lineage`,
  `aligned_scenario_ids`.
- `estimand.py`: `FormalEstimandStatus.MONETARY_MAPPING_NOT_FROZEN`;
  `ConsequenceScope.cu_normalization_registry_id` replaces
  `valuation_registry_id` (scope hash payload changed).

### Config
- `configs/scientific/foundation.yaml` adds a frozen
  `m1_formal_output_contract = [R_IB, D_OB, D_TX, D_TO]` with provenance
  `AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION_2026-08-19` and
  `final_test_access_count: 0`.  `m1_stochastic_targets` (training heads) is
  unchanged.

## New contracts / tests

- `tests/reconciliation/` covers spec Tests A-J plus an M2 smoke contract:
  - Test A: `D_TO == D_OB + D_TX` per scenario (parameterized)
  - Test B: nonnegativity of `D_OB/D_TX/D_TO`
  - Test C: scenario lineage identity/weights across M1/M2/M4
  - Test D: M2 consumes formal fields and abstains on legacy-only scenarios
  - Test E: CU normalization is not money
  - Test F: RMB-weighted ranking differs from raw CU and is selected by M4
  - Test G: NOT_FROZEN monetary mapping blocks authoritative ranking
  - Test H: PRE information_cutoff <= decision_time
  - Test I: ADAPTIVE_HISTORY causal prefix
  - Test J: FAST/STATE_AWARE share the M1Forecast schema
  - M2 smoke: `ValuationRegistry.smoke()` rows are `CU_NOT_FROZEN`
- FAST path tests fit tiny LightGBM models and assert schema/scenario
  equivalence and ABSTAIN-without-models behavior.

## Compatibility breaks

- `ConsequenceScope` scope-hash payload key renamed
  `valuation_registry_id` -> `cu_normalization_registry_id`; scope hashes
  computed after this change differ from before.
- `M4DecisionRequest` now requires the monetary triple; old requests without
  it fail validation.
- M2 drivers no longer accept legacy-only delay scenarios as supported
  (they abstain on delay components).
- `ValuationStatus` enum values are deprecated aliases of
  `CUNormalizationStatus`.

## Remaining boundaries

- No commit/push/PR; worktree stays local.
- No final-test parameter selection; `FINAL_TEST_ACCESS_COUNT = 0` in every
  touched registry/config.
- No formal Exp1-4 runs; the user confirmed Exp1-4 are being rewritten, so
  no exp/ migration was performed beyond read-only audit.
- FAST path is DEVELOPMENT_ONLY until a train-frozen artifact is registered.
- The manuscript draft still contains the old `D_TO` identity
  (`MANUSCRIPT_STALE`); the M2 registry definition text still carries the old
  identity (`CONFIG_STALE`) and was not silently rewritten because the
  registry hash is train-frozen.
