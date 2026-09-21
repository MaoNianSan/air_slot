# AirSlot V2 - Section 4 / Section 5 Artifact Map

Every artifact behind the two status tables, with its owning module and whether
it is committed to the repository. Links are repository-relative.

## Section 4 artifacts (Development / construction)

| Scientific object | Owning module | Source artifact | Paper-facing artifact | Committed |
|---|---|---|---|---|
| History vs Current state families | `model/M1/` | `artifacts/diagnostics/v2_phase5_development/FAMILY_A_STATE_FAMILIES.json` + `.npz` | Section 4 tables (to be authored) | yes |
| H16 primary model | `model/M1/` | `artifacts/models/m1/M1_H16_HISTORY_PRIMARY/` | - | yes |
| H8 capacity sensitivity | `model/M1/` | `artifacts/models/m1/M1_V2_PHASE5_H8_SENSITIVITY/` | - | yes |
| Representation families | `model/M1/` | `artifacts/diagnostics/v2_phase5_development/FAMILY_B_REPRESENTATION_FAMILIES.json` + metrics/variogram `.npz` | Section 4 tables (to be authored) | yes |
| Turnaround / headroom Train support | `model/M3/` | `artifacts/diagnostics/v2_phase5_development/TRAIN_TURNAROUND_HEADROOM_SUMMARY.json` | Section 4 support rows | yes |
| Reference binding audit | `model/M2/` | `artifacts/diagnostics/v2_phase5_development/REFERENCE_BINDING_AUDIT.json` | - | yes |
| CU / consequence construction | `model/M2/` | `registries/m2_data2_formal_cu_v5.json`, `registries/m2_v5_passenger_consequence_design.json` | Section 4.3 | yes |
| Phase-5 run summary | `model/` + `formal/` | `artifacts/diagnostics/v2_phase5_development/PHASE5_RUN_SUMMARY.json` | - | yes |

## Section 5 artifacts (Final Test)

| Scientific object | Owning module | Source artifact | Paper-facing artifact | Committed |
|---|---|---|---|---|
| Canonical cohort authority | `formal/v2_phase7/` | `formal/FINAL_TEST_COHORT_AUTHORITY_V1.json`, `formal/FINAL_TEST_COHORT_MANIFEST_V1.json` | Section 5 cohort row | yes |
| Stage-I / Stage-II / M4 / bootstrap payloads | `formal/v2_phase7/executor/` | `artifacts/experiment/final_test_v2/checkpoints/` (9 stages) | - | no (local, ~587 MB) |
| Checkpoint identities / hashes | `formal/v2_phase7/executor/checkpoints.py` | `artifacts/experiment/final_test_v2/CHECKPOINT_MANIFEST.json` | - | yes |
| Section 5 tables | `formal/v2_phase7/executor/paper_views.py` | same checkpoint payloads | `artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md` | yes |
| Sealed run result | `formal/v2_phase7/` | `artifacts/experiment/final_test_v2/GATE_B_RUN_RESULT.json` | - | yes |
| Access ledger | `formal/v2_phase7/access_audit.py` | `artifacts/experiment/final_test_v2/PHASE7_ACCESS_AUDIT.json` | - | yes |
| Post-run integrity audit | `validation/` + `tmp/phase7_postrun_audit.py` (local script) | `artifacts/experiment/final_test_v2/PHASE7_POSTRUN_SCIENTIFIC_AUDIT.json` | - | yes |
| Freeze ancestry evidence | `validation/v2_phase7/freeze_ancestry.py` | `artifacts/diagnostics/v2_phase7/FREEZE_ANCESTRY_VALIDATION.json` | - | yes |
| Gate B.0 executor binding | `formal/v2_phase7/gate_b0.py` | `artifacts/diagnostics/v2_phase7/GATE_B0_EXECUTOR_BINDING.json` | - | yes |
| Gate B.0a solver-authority equivalence | `formal/v2_phase7/stage2_authority.py` | `artifacts/diagnostics/v2_phase7/GATE_B0A_EQUIVALENCE_VALIDATION.json` | - | yes |
| Safe-fixture DAG dump | `formal/v2_phase7/executor/` | `artifacts/diagnostics/v2_phase7/gate_b0_dag/` | - | no (local, Development fixtures) |

## Caveats

- `PHASE5_RUN_SUMMARY.json` and `GATE_B_RUN_RESULT.json` embed absolute local
  paths (for example `D:\research\air_slot\code\explore\...` and
  `D:\Local_Projects\airslot\_v2_phase7_execution\...`). These are local-input
  lineage records, not repository links; the corresponding files are referenced
  here by relative path where they are committed.
- `GATE_B_RUN_RESULT.json` snapshots the access ledger while the epoch was still
  open (`status = PHASE7_ACCESS_EPOCH_OPEN`, `raw_read_completed = false`).
  `PHASE7_ACCESS_AUDIT.json` is the final ledger
  (`status = PHASE7_ACCESS_EPOCH_COMPLETE`, `raw_read_completed = true`).
- Historical field name `M3_FORMAL_HIGHS_OBJECTIVE_ON_FIXED_REFERENCE_COHORT`
  inside the frozen checkpoint is retained unmodified. The active execution
  authority is `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID` with Pyomo+HiGHS as a
  parity backend only (`registries/v2_stage2_solver_authority_reconciliation.json`).
