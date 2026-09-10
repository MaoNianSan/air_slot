# Final Test Provenance Reconciliation V1

Status: `FINAL_TEST_PROVENANCE_RECONCILED`

## Lifecycle

- `formal/FINAL_TEST_COHORT_AUTHORITY_V1.json` is the immutable pre-access authority. Its `final_test_access_count=0` records the state in which the Final Test cohort and evaluation boundary were frozen.
- The authorized one-time held-out access is recorded by `artifacts/experiment/final_test/FINAL_TEST_ACCESS_AUDIT.json` with `final_test_access_count=1`.
- The executed Final Test cohort contains 128 episodes and has cohort hash `sha256:1208ea465a123a7a6333dc2fd95b182492d5636fb1d8add50845d2f716313d4f`.
- The executed Final Test results under `artifacts/experiment/final_test/exp1` through `exp4` are the current paper numerical authorities. Each is marked `FINAL_TEST_COMPLETE`, `FINAL_TEST_ONLY`, access count 1, and `paper_result=true`.

## Aggregation Authority

The sole paper-authoritative aggregation robustness root is:

`artifacts/paper_results_v2_final_test/aggregation_robustness/`

Its recorded formal computation is:

- 2,000 / 2,000 episode bootstrap replicates;
- 128 Final Test episodes;
- 1,656 active priority nodes;
- 726,455 eligible similar-delay node pairs;
- 7,045 unique episode pairs;
- BASE reproduction `PASS`;
- tolerance bound `atol <= 1e-12`;
- Final Test access count 1;
- model retrained `false`;
- parameter reselected `false`;
- 238 / 238 canonical events supported;
- six-view output has no `BLOCKED` or `ABSTAIN` rows.

The smoke, timing, numba, and reduced-replicate aggregation roots remain diagnostic or validation artifacts. They are explicitly non-authoritative and are not deleted.

## Commit Provenance

Producer commits are retained as artifact provenance:

- pre-access authority: `99114195f11d7cb3446e53729daab611c88f4d36`;
- scientific code lock: `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`;
- cohort freeze: `1c336fb42b0fa7df716f8bf3bc7a67ca0153c06b`;
- Final Test execution: `c7bf2695335013994e09657e07bb023087a4039f`;
- aggregation artifact publication: `860befd20e968ba702b1aad99e618830a3a6acfe`;
- current audit commit: `753705f4fa62452bee86312bfed2eb59b5bade4e`.

The `access=0` and `access=1` values belong to different lifecycle stages. They are not reconciled by changing the historical pre-access authority. This Phase B1 record is additive; no existing scientific payload, aggregation payload, authority file, artifact name, manuscript scientific value, or formula was modified.
