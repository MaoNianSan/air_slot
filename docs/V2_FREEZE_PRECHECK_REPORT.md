# AirSlot V2 Freeze Precheck Report - corrected A2 turnaround reference

Branch `v2/paper-primary`. Precheck round: 2026-09-19, run after the accepted
Phase 0-5 chain (Phase 5 checkpoint `2d28538`). Scope: audit the corrected Data
Gate A2 turnaround support against the old `sha256:7c6ac016...` reference that
appears in the M2 node-reference bundle, repair the lineage, recompute only the
dependent Development/support artifacts, and re-run the frozen verification
gates. Phase 6/7 were not entered, no Final-Test path was read or written, and
M1 was not retrained.

## 1. Audited question and answer

Question: is the old `sha256:7c6ac016...` turnaround reference only stale
metadata, or does it still drive computation?

Answer: **it was an active computation input, not stale metadata.** The old
artifact resolved the M2 node-reference bundle at decision time:

```
exp.exp2.development_inputs._reference_payloads()          # read old JSON
  -> model.M2.context.load_data2_reference_bundle()
  -> validation.v2_phase5.common.build_node_binding()      # turnaround_reference_minutes
  -> model.M2.consequence_service.M2ConsequenceService
  -> F_continuity = max(0, R_IB - turnaround_reference)
```

`P_itinerary`, `P_service`, `F_execution`, `F_propagation`, `P_time` and
`R_operating` never read that reference; `F_continuity` does, both per node
(binding) and in its positive-Train normalization scale (CU scale artifact).

## 2. Numeric and definition differences

| item | superseded reference | corrected A2 reference |
| --- | --- | --- |
| reference_id | `sha256:7c6ac01673f200260fc925eb4c0b57f143fcc34532832375124945252b69707c` | `sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57` |
| manifest_freeze_id | `sha256:89b5329d984f7070f68818832caec72aa46ac2f79d93f303661ab0f81adf1b0a` | `sha256:bfe4f24e40d554e874faac1d987b0126b393a7dd091068b8fd203aba3e06ae7b` |
| artifact_hash | `sha256:f4992f85fa65232115256a7eb9e18e9323995cd4c026463fb5a58bf4cf31cfdb` | `sha256:eff3da4508af5a597516db61e5f8ed45cb84b36c0a06698b43232c5cc76eed41` |
| file sha256 | `sha256:1b80ea32ae33bd383f68e233a4a0c49701ec426cd92fa512095a6fbdd889a440` | `sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f` |
| path | `artifacts/diagnostics/v5_development_freeze/DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json` | `artifacts/diagnostics/m1_v2_data_gate_a2/DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json` |
| global median | 51.0 minutes | 57.0 minutes |
| global sample count | 2,670,770 | 2,668,529 |
| cells | 349 | 349 |
| semantics | pre-correction BTS gate-gap handling | `BTS_SIGNED_DELAY_SEMANTIC_CORRECTION` |

Cell-level comparison: 349 shared cells, 332 cells differ, maximum absolute
difference 41.5 minutes, mean absolute difference 4.1576 minutes.

Definition check (no scientific redefinition): both files satisfy the frozen
rule `DATA2_TURNAROUND_REFERENCE@1.0.0` - statistic `MEDIAN`, applicability
`AIRPORT_GROUP`, fallback `AIRPORT_CELL -> GLOBAL`, minimum support
`MIN_CELL_SIZE_50`. The corrected payload loads through the frozen loader with
no contract change, and the reference bundle resolves every Development node.

## 3. Ruling (R7, R8) and the requested Q20 substitution

R7: the corrected A2 artifact is the active M2 node reference; the superseded
artifact is retained as provenance only.

R8: the M2 node reference stays an **airport-conditioned empirical Train median
with global fallback**, while `T^{turn,lb} = Q20(T^{turn} | Train) = 41` minutes
stays a separate Stage-II lower-tail support quantity.

The precheck request allowed two outcomes: repair provenance if the old
reference were only metadata, otherwise "unify the active reference to the
current Train-derived Q20 = 41". The first branch is excluded by section 1; the
literal Q20 unification was **not** executed, and the reason is recorded
explicitly:

- Substituting the scalar 41-minute bound into `F_continuity = max(0, R_IB -
  turnaround_reference)` would replace an airport-conditioned median reference
  with a global lower-tail bound. That changes the frozen consequence
  definition, which this round is forbidden to modify.
- The corrected Train-derived support *does* drive the chain: the node
  reference now comes from the corrected A2 artifact (global median 57.0), and
  the Stage-II bound is computed from the same corrected Train population
  (`Q20 = 41.0`, `Q10 = 34.0`, `Q30 = 47.0`). Both objects are now
  same-generation; they are simply not the same quantity.

Because the request's conditional branch could not be applied literally without
violating the same request's "do not modify frozen scientific definitions"
constraint, the ruling is registered in the freeze draft as R7/R8 with the
authority chain, and remains open to human revision if the owner reads the two
quantities differently.

## 4. Dependency DAG and recompute scope

Recomputed (M2-dependent only):

- M2 node bindings for all 1,769 Development nodes
  (`REFERENCE_BINDING_AUDIT.json`), because `turnaround_reference_minutes`
  changed per airport.
- `F_continuity` positive-Train median CU scale, from the corrected reference
  (`validation/v2_phase5/scale_correction.py`):
  median `43.0 -> 44.0` minutes, positive n `206,787 -> 186,742`, population
  rows `2,668,531 -> 2,668,531` (unchanged, as required - the continuity
  population never reads the reference).
- Development Family A/B consequence transmission and their artifacts, through
  `python -m validation.v2_phase5.run_phase5 --skip-train-support`.
- Draft freeze and summary, so the lineage and the corrected scale appear in
  the draft.

Not recomputed and verified unchanged:

- M1 was not retrained. The matched H8 sensitivity was reused; the run's
  `h8_sensitivity` marker advances by 0.018 s after the authority load.
- `TRAIN_TURNAROUND_HEADROOM_SUMMARY.json` (0 changed leaves) and
  `TRAIN_TURNAROUND_HEADROOM_SAMPLES.npz` (both arrays identical): Train
  support already used the corrected A2 reference.
- `FAMILY_B_VARIogram_ROWS.npz`: all six arrays identical.
- The other four principal CU scales (`F_execution 17.0`, `F_propagation 10.0`,
  `P_time 990.3555555555556`, `R_operating 5.0`) and the two event
  normalizations (`P_itinerary`, `P_service`, scale 1.0) still inherit their
  V4/assumption sources; only `F_continuity` reads the turnaround reference.
- `model/M1/development_training.py` still reads the old reference root as
  M1-training-time provenance. It is not on the V2 decision path, and changing
  it would invalidate frozen M1 artifacts; the legacy path is therefore
  retained and recorded, not rewritten.
- `registries/ACTIVE_MODEL_ARTIFACTS_V1.json` and
  `registries/MODEL_PARAMETER_REGISTRY.json` are V1R1 legacy registries whose
  digests appear inside the frozen Final-Test-era manifests; they stay
  byte-identical and the supersession is recorded in
  `registries/passenger_reference_supersession_v3.json` instead.

## 5. Output diff evidence (HEAD -> recomputed)

- `FAMILY_A_STATE_METRICS.npz`: 67 of 70 keys identical; only
  `expected_cu__h16__F_continuity` (max abs delta 0.0450),
  `expected_cu__current__F_continuity` (0.00239) and
  `expected_cu__h8__F_continuity` (0.00165) changed. Every MAE, CRPS, coverage,
  interval-width, support-mass and observed-quantity key is identical.
- `FAMILY_B_REPRESENTATION_METRICS.npz`: 80 of 82 keys identical; only
  `expected_cu__joint__F_continuity` and
  `expected_cu__marginal__F_continuity` changed (max abs delta 0.0450).
  POINT `F_continuity` stays identically zero; the POINT representation maps
  that component to zero under both reference generations.
- `FAMILY_A_STATE_FAMILIES.json` / `FAMILY_B_REPRESENTATION_FAMILIES.json`:
  only the `F_continuity` consequence-transmission and paired-distance entries
  plus artifact/registry hashes changed. No ranking or directional claim was
  added (`directional_claims = NONE`, `ranking_performed = false`).
- `REFERENCE_BINDING_AUDIT.json`: per-node `turnaround_reference_minutes`
  updated to the corrected cells; a sample of the first 39 nodes moves e.g.
  `57 -> 63`, `45 -> 47`, `30 -> 34`.
- `PHASE5_RUN_SUMMARY.json`: registry hash, lineage, family hashes, freeze
  hashes and timings only.

## 6. Verification results

- Focused pytest:
  `tests/phase5 tests/decision/test_decision_contracts_v2.py
  tests/m1/test_state_representation_v2.py
  tests/m2/test_comparison_support_v2.py tests/m3/test_stage2_v2.py
  tests/m4/test_evaluation_v2.py tests/m2/test_cu_registry_v5.py -q`
  -> `97 passed`.
  New regression coverage: `tests/phase5/test_turnaround_reference_lineage.py`.
- `python validation/split_isolation.py` -> `status PASS`,
  `final_test_access_count = 0`.
- `python validation/m3_enumeration_highs_parity.py` -> `status PASS`,
  `all_enumeration_highs_parity_passed = true`, Pyomo 6.10.1 / HiGHS 1.15.1,
  TAXI/COMP `NOT_ACTIONABLE` check passed,
  `final_test_access_count = 0`.
  The synthetic parity objectives shift slightly (`j_star` PRE parity node
  `11.8727 -> 11.8365`) because the parity builder consumes the active CU scale
  (`F_continuity 43.0 -> 44.0`); enumeration and HiGHS stay identical and the
  refreshed artifact is recorded in
  `artifacts/diagnostics/v2_phase3/M3_ENUMERATION_HIGHS_PARITY.json`.
- `python -m validation.v2_phase5.run_phase5 --skip-train-support` ->
  `status PASS` in 284.5 s.
- Registry self-check: `registry_hash == registry.digest()` and
  `passenger_reference_supersession_v3.registry_payload_hash` matches it.

## 7. Freeze draft state after the precheck

- `registries/v2_scientific_freeze_draft.json`:
  `status = DRAFT_NOT_ACTIVATED`, `freeze_commit = PENDING`,
  `final_test_access_count = 1` (historical, unchanged),
  `new_final_test_execution = false`,
  artifact hash `sha256:286c27fc858ec06721e84e13f311ce4c4e3b0e38b93d351807276b32c45b94d3`.
- `docs/V2_SCIENTIFIC_FREEZE_SUMMARY.md` section 18 records the precheck;
  summary hash `sha256:b324f85fbd82278db50702ce9caa9d22471a76d048366b55e8a55b78a852455f`.
- New draft block `turnaround_reference_precheck` records the active and
  superseded references, the call path, the cell-level delta, the
  median-versus-Q20 separation, the rejected scalar substitution, and the
  corrected `F_continuity` scale.
- No formal freeze is claimed and no Final-Test artifact was read, written or
  reinterpreted.

## 8. Key artifact and file hashes

- corrected A2 reference: `sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f`
- corrected `F_continuity` scale artifact:
  `artifacts/diagnostics/v2_freeze_precheck/M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json`
  (`artifact_hash sha256:4f6851fae1a3f24f3742b5049bdb9465932cb2fcb190cefe396ab773be6c967f`)
- CU registry V5: `registries/m2_data2_formal_cu_v5.json`,
  `registry_hash sha256:fd3ccfa0c56ba64d840ab163b5a133a5b0d6a662249d89af38c7377f6f24b030`
- Family A: `sha256:92dd3769c4e7516a8203f2a174868a61ad2d1a33d2e16fcea1e0816de56c1e52`
- Family B: `sha256:e7706447a308d3c7b3c3338f23e752a85b31fb907a879e206f052c395e654467`
- Reference binding audit:
  `sha256:9332c92a924abf9bc71e43be78fda1a38fdd3aea070ec6e4681f54793ee9ae53`

## 9. Open items

- R7/R8 remain open to human revision: if the owner intends the M2 node
  reference itself to become the scalar Q20 bound, that is a consequence
  redefinition and needs its own decision plus a manuscript correction.
- The manuscript appendix CU section is still not synchronised with the five
  principal medians plus two event normalizations (Phase 5 open item O1).
- `F_continuity` scale provenance now differs from the V4 legacy scale artifact
  on purpose; the V4 file and the V1R1 parameter registry stay untouched for
  their frozen pipelines.
- Formal freeze activation and any new Final-Test access remain Phase 6 human
  gates.
