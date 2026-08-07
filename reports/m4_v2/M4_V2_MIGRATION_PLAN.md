# M4 V2 Migration Plan

Date: 2026-08-07

Status: completed locally; formal execution remains blocked by upstream gates.

## Verified Baseline

```text
git branch = main, ahead of origin/main by 1
existing staged M3 V4 replay = preserved
compileall overall_run/src overall_run/tests = PASS
M1 tests = 61 passed
M2 tests = 58 passed, 1 stale-gate failure
M3 + Ranking + legacy M4 contract tests = 39 passed, 7 skipped
```

The M2 failure expects the retired M3 contract mismatch. Current orchestration
already loads M3 V4 and stops at `M3_PARAMETER_NOT_FROZEN`.

## Migration Order

1. Add `overall_run/src/m4/` contracts, compatibility, evidence, stage,
   opportunity, stable draw pairing, post-loss, risk, ranking, rolling, output,
   pipeline, and evaluation modules.
2. Accept only `M2InputBundle`, `tuple[M2SampleLoss, ...]`, and `M3Artifact`.
3. Preserve PRE R2/R3 distinction; R2 is compatibility-only and cannot satisfy
   an R3 formal evidence gate.
4. Keep non-A00 formal execution blocked by current M2 valuation, M3 parameter
   freeze, formal library, stage, opportunity, and evidence status.
5. Add an explicit test-only synthetic integration path that never writes the
   formal output directory and never allows publication.
6. Reuse shared Ranking@1/@2/@3/@5 fixed-width prefix materialization from one
   authoritative formal sort.
7. After new tests pass, isolate old screening/evaluation under `src/legacy/`
   and retire old public APIs with `M4_LEGACY_CONTRACT_RETIRED`.
8. Update strict config, implementation manifest, pipeline gate tests, README,
   and local reports. Do not run Fast, Middle, Full, overall_adv, or part_adv.

## Non-Negotiable Gates

```text
M2 nine-subitem completeness
M2 channel and total loss identities
M2 valuation/test-only identity
M3 V4 shapes, ranges, hashes, and A00 identity
PRE R2/R3 evidence distinction
no pressure-to-resource inference
no future observed chain inference
no missing-to-zero conversion
no guessed stage or opportunity contract
evaluation cannot change formal output hash
Ranking K views are prefixes of one sort
```
