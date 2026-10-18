# AirSlot V2 Phase 6 Scientific Freeze Report

## 1. Activation state

- active registry: `registries/v2_scientific_freeze.json`
- active registry artifact hash: `sha256:3828b17ac93cbaf81579e865faf32ed9547a1d540a65d3679ab4248a2bf17e2d`
- status: `SCIENTIFIC_FREEZE_ACTIVE`
- formal freeze: `YES`
- freeze_commit: `2d74af9ee5a1cb5db59e0e94fac83f2aa608db01`
- freeze_commit semantics: `PRE_FREEZE_SCIENTIFIC_BASELINE_NOT_ACTIVATION_COMMIT`
- pre-freeze scientific baseline commit: `2d74af9ee5a1cb5db59e0e94fac83f2aa608db01`
- pre-freeze scientific baseline tree: `4bb3257666421c46e18bd17703c11d2a78d347d2`
- complete frozen repository state: `ANNOTATED_TAG_RESOLUTION`
- activation tag: `v2-scientific-freeze`
- activation tag target: `RESOLVED_AFTER_COMMIT`

The pre-freeze baseline commit is a scientific/numerical baseline. It
does **not** contain the Phase 6 activation metadata and is not the final
repository snapshot. The complete Phase 6 frozen repository state is the
state resolved by the annotated activation tag after the activation
commit exists. The resolved target is reported in the final Phase 6
handoff and in the post-tag report update.

## 2. Independent artifact identities

### M2 typical turnaround reference

- identity: `sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57`
- scope: `M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY`
- declared artifact hash: `sha256:eff3da4508af5a597516db61e5f8ed45cb84b36c0a06698b43232c5cc76eed41`
- manifest freeze id: `sha256:bfe4f24e40d554e874faac1d987b0126b393a7dd091068b8fd203aba3e06ae7b`
- file SHA-256: `sha256:4a75c326b5ac193eb9b65eefa4741eac8a6ed36d1fde66e542d5cbd8e053803f`
- statistic: `MEDIAN`
- applicability: `AIRPORT_GROUP`, global value `57.0`, global sample count `2668529`, cells `349`
- semantic correction: `BTS_SIGNED_DELAY_SEMANTIC_CORRECTION`

### M3 Stage-II turnaround lower-bound reference

- identity: `M3_STAGE2_TURNAROUND_LOWER_BOUND_Q20`
- scope: `M3_STAGE2_FEASIBILITY_ONLY`
- definition: `T^{turn,lb} = Q20(T^{turn} | Train)`
- nominal Q20: `41.0` minutes; Q10/Q30: `34.0` / `47.0` minutes
- population rows: `2668531`

### F_continuity CU scale

- identity: `M2_V5_F_CONTINUITY_SCALE_CORRECTION_V1`
- scope: `M2_F_CONTINUITY_CU_SCALE`
- declared artifact hash: `sha256:4f6851fae1a3f24f3742b5049bdb9465932cb2fcb190cefe396ab773be6c967f`
- file SHA-256: `sha256:688560356d5c7fa292b59e5a7b45cf249619c35bf6620446b1166034a5a2e061`
- statistic: `MEDIAN_TRAIN_POSITIVE`
- median: `44.0`
- positive n: `186742`
- population rows: `2668531`
- fit partition/period: `TRAIN` / `2019-H1`

## 3. Non-merge contract

- `merge_forbidden = True`
- `41_is_not_the_m2_node_reference = True`
- `57_is_not_the_stage2_lower_bound = True`

The M2 reference is the airport-cell median node-reference bundle input
with global fallback 57. The M3 quantity is the scalar Train Q20 lower
bound 41 used only for Stage-II feasibility. They are not merged.

## 4. Provenance correction

The corrected Train-support summary changes only provenance/scope
metadata, the added Stage-II lower-bound block, the summary artifact
hash, and the dependent registry file hash. The two sample arrays,
sample membership, rotation and episode counts, quantiles, median 57,
headroom statistics, U_max and action grid are unchanged. The metadata
diff is validated by `validation/v2_phase6/lineage_hash_validation.py`.

## 5. Final-Test accounting

- historical Final-Test access total: `1`
- current freeze-run increment: `0`
- new Final-Test execution: `false`
- Phase 7 entered: `false`
- Final-Test path touched: `false`

No Final-Test artifact was read or written by Phase 6.

## 6. Validation gates

- focused pytest: reported in the Phase 6 handoff
- split isolation: reported in the Phase 6 handoff
- enumeration/HiGHS parity: reported in the Phase 6 handoff
- lineage/hash validation: `artifacts/diagnostics/v2_phase6/FREEZE_LINEAGE_HASH_VALIDATION.json`
