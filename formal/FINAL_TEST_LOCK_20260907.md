# Air Slot Exp1-Exp4 Final Test Pre-Lock

Date: 2026-09-07. Scope: scientific freeze and lightweight consistency checks
only; not authorization to access Final Test or to make paper-result claims.

Status: `FINAL_TEST_LOCKED_READY_FOR_EXPLICIT_AUTHORIZATION`.

## Code Identity

- Actual HEAD inspected before this documentation-only commit:
  `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`.
- `DEVELOPMENT_ANALYSIS_CODE_LOCK`:
  `c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6`.
- Scientific-code diff since that snapshot: **none**. The starting worktree
  was clean; `git diff c70c306dfb8bcc40ccb2c1329594fe6b1a54acb6 -- model exp
  docs/EXPERIMENT_DEFINITION_LEDGER_V1.md` was empty.
- This commit adds only this lock document. It does not modify `model/`,
  `exp/shared/`, `exp/exp1/` through `exp/exp4/`, Data1, Data2, registries,
  the frozen experiment definition ledger, or existing experiment artifacts.
- Producer HEAD values already recorded in Development manifests remain
  historical provenance; they are not rewritten to the documentation commit.

## Frozen Common Definitions

- Primary model: frozen **H16 History**. **Current is a comparator only in
  Exp1**. No retraining, recalibration, parameter reselection, threshold
  reselection, or metric reselection.
- No Development-driven manuscript claim selection before Final Test.
- Exp2-Exp4 retain the Development definitions of `D`, `S_F`, `S_P`, `S_R`,
  `S_C`, `NO_F_EXECUTION`, and support, using the same shared authorities.
  There must be no experiment-local redefinition at Final Test.
- `NO_F_EXECUTION` remains
  `F_no_exec = mean(F_continuity, F_propagation)` and
  `C_no_exec = mean(F_no_exec, P, R)`, using the frozen normalized fields and
  `exp.shared.recovery_priority.compute_no_f_execution_priority`.
- Exp2-Exp4 primary support: `COMMON_SUPPORT_CONDITIONAL_090`.
  Sensitivity thresholds remain `0.50` and full support `1.00`.
  Primary aggregate eligibility also requires
  `conditional_aggregate_complete == True`; Exp2B retains its independently
  defined component/domain finite, support-applicable, primary-support
  population, not the Exp2A seven-component complete-case sample.
- Exp1 History/Current retains exact matched node identity and matched
  target-specific support. Unsupported or inactive targets are not zeros.
- Formal inference: cluster = `original_episode_id`, `B = 2000`,
  seed = `20260906`, percentile 95% CI. Duplicate episode occurrences retain
  bootstrap multiplicity and distinct technical instance identities.
  Original-episode self-pairs remain prohibited.
- Rebuild the required ranks, Top-K, matching, and canonical/support cohorts
  within each replicate. Exp3 preserves episode-pair balancing and derives
  stage contrasts from replicate-specific stage metrics. Exp4 rebuilds
  canonical events before support, K, rankings, and selection statistics.
  Computational cost does not authorize changing B or the estimand.

## Exp1 Reporting Lock

### Exp1A

Report `R_IB`, `D_OB`, and `D_TX` separately; never pool them into a headline
MAE. MAE and P90 absolute error remain in minutes. The Development denominator
audit is:

| Target | raw_record_count | matched_eligible_count | n_nodes | n_episodes |
| --- | ---: | ---: | ---: | ---: |
| R_IB | 1769 | 217 | 217 | 48 |
| D_OB | 1769 | 1671 | 1671 | 128 |
| D_TX | 1769 | 1765 | 1765 | 127 |

`5307 = 1769 * 3` is only the node-target audit record count, not a pooled
metric or bootstrap denominator. Inactive, unavailable, and unsupported
target rows remain excluded from each target's eligible denominator.

Finite-support CRPS belongs only to the `R_IB` / `T_IB` distributional
evaluation (`R_IB_T_IB_FINITE_SUPPORT_CONDITIONAL_ONLY`). Do not introduce
unfrozen CRPS for `D_OB` or `D_TX`. Preserve paired History/Current contrasts
and the evaluation-lead grid `[0, 30, 60, 120, 180, 240, 300, 360, 420, 480]`
minutes.

### Exp1B

The audited Development direction is `Point_minus_Joint_VS > 0`, while
`Marginal_minus_Joint_VS` is approximately `-0.06`. This is recorded as a
pre-test constraint, not selected as a manuscript conclusion.

Do not change representation, Variogram Score, `p = 0.5`, support, or
aggregation to make Joint outperform Marginal. Final Test must use exactly
the Development definitions.

The downstream paper-summary rule is now frozen: for **each M2 consequence
component separately**, report Point-vs-Joint native W1 and Marginal-vs-Joint
native W1 as **mean native W1 over eligible nodes + episode-cluster bootstrap
95% CI**. Do not average across components with different native units.
Cross-component summaries, if used, may use only the already frozen
normalized/CU representation, with no new normalization. This Pre-Lock
records the reporting rule; it does not recompute Development summaries.

## Exp2-Exp4 Interpretation Lock

- **Exp2:** Delay may be an informative priority proxy; the experiment tests
  whether it sufficiently represents multidimensional consequences.
- **Exp3:** Discuss operating-stage variation and association, not causality.
  Same-delay primary heterogeneity remains the within-stage consequence
  percentile-rank gap, with all three pairwise stage contrasts and
  common-episode robustness.
- **Exp4:** Fixed-capacity recovery triage/screening, not action optimization,
  realized cost saving, welfare improvement, or an OCC staffing simulation.
  Capture is consequence burden represented in a screening shortlist,
  not consequence reduction.
- Exp4 selects the first chronological canonical node before support;
  unsupported canonical events retain typed exclusions and are never
  replaced by later supported nodes. Preserve stage-specific budget cohorts,
  `q = 5/10/20/30%` (primary 10%), `K = ceil(q*N)`, deterministic technical-node
  boundary tie handling/audit, F/P/R and seven native-component capture,
  and explicit Delta Capture.
- Robust high-consequence sets use eight non-base views, each view's Top-10%
  **within the stage-specific budget cohort**, with `m = 4` primary and
  `m = 3,5` sensitivities. Preserve robust miss-rate contrasts and Pareto
  screening definitions. Report zero Pareto results honestly; do not change
  definitions to find positive results.

## Development Result Identity

All four existing manifests retain `final_test_access_count = 0`,
`paper_result = false`, `model_retrained = false`, `calibration_refit = false`,
and `parameter_reselected = false`. Counts below are confirmed from existing
manifests; no bootstrap was rerun.

| Experiment | Existing status | Completed / required | Seed |
| --- | --- | --- | ---: |
| Exp1 | PASS | 2000 / 2000 | 20260906 |
| Exp2 | DEVELOPMENT_COMPLETE | 2000 / 2000 | 20260906 |
| Exp3 | DEVELOPMENT_COMPLETE | 2000 / 2000 | 20260906 |
| Exp4 | DEVELOPMENT_COMPLETE | 2000 / 2000 | 20260906 |

All paths in the following two tables are relative to `artifacts/experiment/`.
Hashes are SHA-256 of the **actual checkout bytes on 2026-09-07**.

| Manifest | SHA-256 |
| --- | --- |
| `exp1/development/EXP1_OUTPUT_MANIFEST.json` | `c4cd4046f1bb090ddbfc023d4ebb0b31c1d1c1da998ff6f2ed84cbcd7c31da54` |
| `exp2/development/EXP2_MANIFEST.json` | `89bb36af15e815186ca16cc9a15936b80b9f9b946184c1e5204a7710df0ceca7` |
| `exp3/development/EXP3_OUTPUT_MANIFEST.json` | `985f3f85ce94c6890c18c19af099afa50517e215d95d3ca674a08b11fd51e761` |
| `exp4/development/EXP4_OUTPUT_MANIFEST.json` | `b5b02032b3cc4ae57fb78de4911f49b11fe85ebf5ec2f17d2e66791319e3ee8d` |

| Main result | SHA-256 |
| --- | --- |
| `exp1/development/EXP1_HISTORY_CURRENT_TARGET_SUMMARY.csv` | `c934740233ca7916c5b2ce9f5cf6b60e3ee68b699d31beaee00c6b063e76c408` |
| `exp1/development/EXP1_HISTORY_CURRENT_MATCHED_RECORDS.csv` | `11e10ac8a1903fe244ebd8a98efdb131b909f8ab0ad8abb00483e82dc40641ed` |
| `exp1/development/EXP1_HISTORY_CURRENT_BOOTSTRAP.csv` | `2cbb9e88b469b47d02f353ebe495552917afbe8706373a57fa37f2e7eabb5b8a` |
| `exp1/development/EXP1_EVALUATION_LEAD_TIME.csv` | `11edf706a803e6b9db81375b99877375c7b0bdb5d3778fb0b0a0e5e597fe3d91` |
| `exp1/development/EXP1_REPRESENTATION_CONTRASTS.csv` | `a88d90e7a4b594f968bff349bf83ca1bb10582cd99f994fffb0fa17ffb7a9db5` |
| `exp1/development/EXP1_REPRESENTATION_SUMMARY.csv` | `5ac1385e4ce7b0001a194cbb0064efc8fc818564dea00185953cefcff4c6202e` |
| `exp1/development/EXP1B_REPRESENTATION_SUMMARY.csv` | `2a5139c502bc1458a0ac02d0f81b6766279f55063db8f23f23fa97bc9f99c182` |
| `exp1/development/EXP1B_DOWNSTREAM_NATIVE_DISTORTION.csv` | `a757d0d58e716602a45ca723387d2d6b1025578b385c1a1c218dcd87c2480cfb` |
| `exp2/development/results/EXP2A_SUMMARY.csv` | `e2e6796801ba8f3fed47e42824d835275cc7bf9003fdee409343b6104144adb3` |
| `exp2/development/results/EXP2B_COMPONENT_DOMAIN_SUMMARY.csv` | `5c7e71348690eb46ea0dc47a0b12243ab93bda31fb262d418c75841b55ad5ee5` |
| `exp2/development/results/EXP2C_PAIR_BALANCED_SUMMARY.csv` | `64b1d4ccdb4beca660c04624edcec7d8d3f86b44834f1fbea4039989844e1109` |
| `exp2/development/results/EXP2A_BOOTSTRAP.csv` | `68fc16f6897d953f526e72649ce9d1327596021f5926441289f3a6891f426499` |
| `exp2/development/results/EXP2B_BOOTSTRAP.csv` | `d0abc7e043011123fa025922ad50657c94cb3f4e128d26af11e0ff6c5c8cbfe9` |
| `exp2/development/results/EXP2C_BOOTSTRAP.csv` | `6e74c1e7651fac2d70e0b6ed5762753fc9ce8fd51617b478f58b55df158116dd` |
| `exp2/development/results/EXP2_ROBUSTNESS_SUMMARY.csv` | `3474e2e34a3940a522ecdf4d2df4753d0c8fef5735a382edfb7f60ecb5320ede` |
| `exp3/development/EXP3_STAGE_AGREEMENT.csv` | `0c9075bce2dba61682a949e1e093a409f69d73537cd29602ebc3f0abd8d7fe17` |
| `exp3/development/EXP3_STAGE_HETEROGENEITY.csv` | `8a2fcadece99cb433738aff7b7af4b3b828c599030915c67e6b8414a65f8f0a1` |
| `exp3/development/EXP3_STAGE_CONTRASTS.csv` | `f5708823aba522dcffec11f6a3f4a2b038591ad7bd175a1f8cc6c40f0e48df8d` |
| `exp3/development/EXP3_STAGE_CONTRAST_BOOTSTRAP.csv` | `22e1adf2b8a2218859ac1144bb0b91ff17f4341d29a96d11cbdf680cd39653cb` |
| `exp3/development/EXP3_BOOTSTRAP.csv` | `6d4d972c597bad58631a61c60f88256d9368393ab3829aa9bb7453a78511d0f7` |
| `exp3/development/EXP3_COMMON_EPISODE_ROBUSTNESS.csv` | `35539dd71114ea46b1835a0b7a1e140aac2159028c989da46380a7e89021f08b` |
| `exp3/development/EXP3_COMMON_EPISODE_BOOTSTRAP.csv` | `520f07a66374ae5f77404cedce5dcf21939231066382d02a44363ab7ce9744b2` |
| `exp4/development/EXP4_SCREENING_RESULTS.csv` | `a04aaa10487b9b39ca4c79bd45a40af140d563af1f197580b97e3afe87864098` |
| `exp4/development/EXP4_CAPTURE.csv` | `bbf43b4287c4867237b9f7b38f236904e16e37656d95f323df2756c760ac40be` |
| `exp4/development/EXP4_DELTA_CAPTURE.csv` | `6985440a53fdc4a63de68e53f6b01e70726bde5565c9c58f5dbda0d43e59c24c` |
| `exp4/development/EXP4_DOMAIN_CAPTURE.csv` | `0cfb0b7d6196e606d4226a2f3829d9c68d501c4b4feed9ff506de958fb806b92` |
| `exp4/development/EXP4_NATIVE_COMPONENT_CAPTURE.csv` | `83a325222be33f091e47c82c7f92825de9395983632f66b10efc98ef7d4c8c4f` |
| `exp4/development/EXP4_ROBUSTNESS_SUMMARY.csv` | `0bf6a75ad8ee379b1c014f684b36ca09ff277e138f5e0cc23102d0bfbe869944` |
| `exp4/development/EXP4_PARETO_SUMMARY.csv` | `8404d290d7198ee560350b0b8c34db2ff93ca20cceb7ee21e278b90ae1dece47` |
| `exp4/development/EXP4_PARETO_EVIDENCE.csv` | `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b` |
| `exp4/development/EXP4_BOOTSTRAP.csv` | `7a18f4f878d676856335f8b073754120526052b6931da3f56c3aa8daab7180b4` |

Output-hash reconciliation: all 43 entries in the Exp2/Exp3/Exp4 manifests
were checked. Five binary outputs match their manifest hashes byte-for-byte.
The other 38 entries are LF checkout text whose CRLF form exactly matches
the stored run-time hash. This is fully explained by the tracked
`.gitattributes` rule `*.json` / `*.csv text eol=lf`; it is not a scientific
content mismatch. Conversion was in memory only. No artifact or manifest
hash was rewritten. Exp1 has no embedded output-hash map; its existing
tracked results were hashed directly, with main hashes recorded above.

The locally available Exp3 and Exp4 `*_BOOTSTRAP_DRAWS.npy` files each match
the existing manifest SHA-256
`9a3bb194d0423e6e896aac7412a795f25613d53e5a2b76ca85e7804b6886e302`.
They remain untracked derived files. Frozen seed and code can regenerate
draws for verification; this task neither regenerates nor commits them.

## M2 Passenger Reference

The tracked `registries/m2_data2_formal_cu_v4.json` and
`registries/MODEL_BASELINE_SEAL_V1.json` retain the frozen
`M2_DATA2_FORMAL_CU_V4` passenger reference. The baseline seal reports
`MODEL_BASELINE_SEALED`. DB1B connection-share frozen reference ID:

`sha256:0b58f3bbbbbde7de38d6a71de903f05141c165b4e86bd4409609286798898e35`

This reference ID is not the file-byte hash of the registry. Checkout file
SHA-256 values are:

| Repository-relative path | SHA-256 |
| --- | --- |
| `registries/m2_data2_formal_cu_v4.json` | `e28ba89ef73fd5ba13ee67bd3aa16de8e097a64c133812c7ded341a9294c6e95` |
| `registries/MODEL_BASELINE_SEAL_V1.json` | `abae3b1639645c9c588a2d8734f2f61bc8b585bcc90679c5d03e11442ee0fb77` |
| `docs/EXPERIMENT_DEFINITION_LEDGER_V1.md` | `6e99636a517dff566ccaa5213a127b1fb0ad6305b27590dcffe9d24593f45561` |

## Minimal Verification And Stop

Existing scientific contract command:

```text
python -m pytest -q tests/exp1/test_development_smoke_contract.py tests/exp2 tests/experiments/test_exp134_scientific_contracts.py
```

Result: **39 passed in 11.67s**. Tests used existing contracts and small
deterministic/fixture checks; no formal 2000-replicate bootstrap or M1/M2
materialization was run. The legacy smoke missing-PRE test remains a
fail-closed diagnostic test, not the status authority for completed formal
Exp1. Source diff and existing Development status/flag checks passed.

`FINAL_TEST_ACCESS_COUNT = 0`.

No Final Test input/result was accessed, no Test materialization was run,
and no manuscript conclusion was written. Commit and push this lock document,
then stop. Final Test requires a subsequent explicit authorization.
