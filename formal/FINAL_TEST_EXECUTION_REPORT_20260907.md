# Air Slot Final Test Execution Report

Date: 2026-09-07.

Status: `BLOCKED_FINAL_TEST_COHORT_AUTHORITY_AND_INPUT_BINDING`.

The user's explicit Held-Out Final Test authorization is acknowledged.
This is not an authorization blocker. No held-out cohort or result was read
in this execution attempt. The Test remains unopened for this locked run.

## Verified Identity

- Start HEAD: `99114195f11d7cb3446e53729daab611c88f4d36`.
- Development scientific code lock:
  `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`.
- Scientific authority: `formal/FINAL_TEST_LOCK_20260907.md`.
- Lock file checkout SHA-256:
  `6a68b08226076cb5f8601139569077b8b37ca0483805725be0f30d24e76174a5`.
- Diff against the scientific lock for `model`, `exp`, `configs`,
  `registries`, and `docs/EXPERIMENT_DEFINITION_LEDGER_V1.md`: empty.
- H16 History checkpoint SHA-256:
  `061c3540c38ad8272982590de437d27064d50b1e023b55b672e77392d2c4ac3b`.
- H16 Current checkpoint SHA-256:
  `68a349a2d82f1d2c8c344c30e85777c55c644e63605e01a94364afdce7183ee3`.

## Blocking Evidence

1. The temporal split authority exists:
   `model/PRE/cohort.py:28` assigns canonical service dates to frozen splits;
   `model/PRE/episode/containment.py` checks both flights and the entire episode
   support. These rules must be reused, not replaced with a raw-date filter.
2. The current cohort selection configuration is Development-only.
   `configs/engineering/m1_data2_development_fast.yaml:9` specifies a seeded
   reservoir, seed `20260813`, and counts
   `{train: 128, calibration: 64, development: 128, test: 0}`.
   `artifacts/models/m1/M1_FORMAL_TRAINING_COHORT_V1.json:205` records
   `final_test_episode_count: 0`. The Final Test lock does not supply a Test
   episode list, a Test reservoir size/selection contract, or a reference to
   an active H16 Test cohort artifact.
3. Q4 path selection is supported by
   `model/PRE/streaming/data2.py:ontime_paths(..., allow_final_test=True)`,
   but this is not a cohort selector. The existing `episode_reservoirs`
   implementation enumerates input paths as months starting at January
   (`:467`, `:484`, `:490`) and explicitly rejects Test episodes (`:499`).
   Passing only Q4 paths to that Development routine would not constitute a
   valid split switch. This is an input-interface limitation, not evidence
   that the Development scientific implementation is incorrect.
4. `model/PRE/development.py:147` accepts only the three non-Test partitions.
   Exp1 additionally binds exact Development PRE/cache identities and the
   Development-specific 1769-node count
   (`exp/exp1/formal_inputs.py:82`, `:104`).
   Exp2 binds the Development reservoir
   (`exp/exp2/development_inputs.py:191`).
   Exp3/Exp4 call `validate_development`
   (`exp/exp3/run.py:18`, `exp/exp4/run.py:23`), which rejects Q4 dates.
   None of these guards was bypassed or changed.
5. `formal/RUNTIME_PATH.md:8` makes archived experiment workflows
   provenance-only, not formal execution authorities. Historical H32 results
   or cohort counts cannot silently supply the missing current Test binding.

The missing scientific input is the current lock's explicit Test cohort
selection authority. A 128-episode Test reservoir, a full Q4 population, or
an archived episode list cannot be chosen interchangeably by the executor.
Once that authority is supplied, the input/output binding can be implemented
while retaining the locked analysis functions. No new estimand is proposed.

## Verification

Ran once, without held-out inputs:

```text
python -m pytest -q tests/exp1/test_development_smoke_contract.py tests/exp2 tests/experiments/test_exp134_scientific_contracts.py
```

Result: **39 passed in 13.84 seconds**. This is contract evidence, not Final
Test result evidence. No bootstrap or model materialization was launched.

## Requested Result Status

- Final Test episode, rolling-node, target-eligible, primary-support,
  stage-specific, and canonical-event counts: `NOT_MATERIALIZED`, not zero.
- Exp1 headline results, lead slices, representation contrasts, and native
  distortion confidence intervals: `NOT_RUN`.
- Exp2, Exp3, Exp4 formal tables and bootstrap confidence intervals: `NOT_RUN`.
- Development versus Test direction, robustness, null and negative findings:
  `NOT_EVALUATED`.
- Test typed abstentions and support coverage: `NOT_EVALUATED`.
- Paper-facing figure data and figures: `NOT_GENERATED`.
- `model_retrained = false`.
- `calibration_refit = false`.
- `parameter_reselected = false`.
- `scientific_definitions_changed = false`.
- `paper_result = false`.
- `FINAL_TEST_ACCESS_COUNT = 0`.

Only this report was added. Models, scientific code, registries, data,
Development outputs, the lock file, and manuscript text were left unchanged.
No commit or push was performed.
