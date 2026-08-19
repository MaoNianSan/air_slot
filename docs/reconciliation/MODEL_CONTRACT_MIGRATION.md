# MODEL_CONTRACT_MIGRATION

Migration map for `AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION` (2026-08-19).

## M1 targets

| Old scientific role | Old field/name | New formal role | New canonical field | Status |
| --- | --- | --- | --- | --- |
| successor off-block offset (formal) | `DELTA_OB` | internal auxiliary (signed) | `delta_ob_minutes` | DEPRECATED for downstream; training head unchanged |
| taxi-out duration (formal) | `T_TX` | internal auxiliary | `t_tx_minutes` | DEPRECATED for downstream; training head unchanged |
| nonnegative off-block delay (derived) | `R_OB` / `r_ob_minutes` | formal successor delay | `D_OB` / `d_ob_minutes` | ALIAS (`r_ob_minutes` property kept) |
| excess taxi delay (not previously formal) | - | formal successor delay | `D_TX` / `d_tx_minutes` | NEW |
| total takeoff delay (old identity) | `D_TO = max(0, DELTA_OB + T_TX - taxi_ref)` | derived per-scenario identity | `D_TO = D_OB + D_TX` | REPLACED in `model/M1/semantics.py` |
| predecessor in-block representation | `R_IB` / `r_ib_minutes` | predecessor A00 in-block | `R_IB` / `T_IB_A00` | unchanged formal target |

`M1_FORMAL_TARGETS = ("R_IB", "D_OB", "D_TX")`; `M1_DERIVED_TARGETS =
("D_TO",)`; `M1_INTERNAL_AUXILIARY_TARGETS = ("DELTA_OB", "T_TX")`.

## M2 registry and CU separation

| Old | New | Notes |
| --- | --- | --- |
| `ValuationRegistry` (one registry, two semantics) | `M2CUNormalizationAdapter` + `CUNormalizationRegistry` | `ValuationRegistry` kept as deprecated alias |
| `ValuationStatus` enum | `CUNormalizationStatus` | old enum values are deprecation aliases |
| `valuation_registry_id` (scope/rows) | `cu_normalization_registry_id` | `ConsequenceScope` hash payload key renamed; scope hash changes |
| `constructed_value_cu` from valuation | CU from `CUNormalizationRegistry.to_cu` | train-frozen scales; DEV smoke returns `CU_NOT_FROZEN` |
| M2 drivers reconstructing `takeoff` from `delta_ob + t_tx - taxi_reference` | M2 consumes `d_ob_minutes/d_tx_minutes/d_to_minutes` | legacy-only scenarios abstain |

## M3 response provenance

| Old | New | Notes |
| --- | --- | --- |
| `ResponseProvenance` single enum | `ActionResponseSupport` structured support | `from_legacy_provenance` mapping added |
| - | `EvidenceBasis` / `ActionResponseSupportState` | hybrid-capable `Pi_a` |
| - | `ActionTemplate.response_support`, `CandidateAction.response_support` | optional; `None` falls back to legacy enum checks |

## M4 monetary contract

| Old | New | Notes |
| --- | --- | --- |
| ranking on `sum CU` | ranking on `sum_k omega_k^m * C_a,k^CU` | per-scenario monetary conversion first |
| raw-CU fallback when valuation missing | `MONETARY_MAPPING_NOT_FROZEN`, no authoritative ranking | `lanes.py` never grants FORMAL without frozen mapping |
| `M4DecisionRequest` without monetary fields | requires `monetary_system`, `monetary_mapping_registry_id`, `monetary_mapping_registry_hash` | hard identity/hash checks in `evaluate_request` |
| `ActionEvaluation` without monetary lineage | carries `monetary_system`, `monetary_mapping_registry_id`, `monetary_mapping_registry_hash` | included in ranking identity |

## Config

| Old | New | Notes |
| --- | --- | --- |
| `m1_stochastic_targets = [R_IB, DELTA_OB, T_TX]` (unchanged) | added `m1_formal_output_contract = [R_IB, D_OB, D_TX, D_TO]` | training heads untouched; provenance `AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION_2026-08-19` |

## Hash / contract breaks

- `ConsequenceScope.scope_hash` changes for any scope created after the
  rename of `valuation_registry_id` -> `cu_normalization_registry_id` in the
  hash payload (`model/common/estimand.py`).
- M2 registry JSON on disk is unchanged (hash preserved); its
  native-quantity definition *text* still uses the old identity and is
  tracked as `CONFIG_STALE` (re-freeze requires a human decision).
- `M4DecisionRequest` validation now rejects requests missing the monetary
  triple; callers must supply a frozen `MonetaryMappingRegistry`.
- M1 `AlignedScenario` validation now rejects any scenario where
  `D_TO != D_OB + D_TX` (within tolerance); legacy raw `r_ob_minutes` input
  is rejected (`Extra inputs`).
