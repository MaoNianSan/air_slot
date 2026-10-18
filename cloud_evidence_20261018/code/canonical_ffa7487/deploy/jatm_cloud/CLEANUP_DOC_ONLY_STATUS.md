# Documentation-only cleanup status, 2026-10-12

Scientific baseline: `e278ac55871dd3208bbd9a55e24b0d7a94314c96`, branch
`v2/paper-primary`. User-confirmed scientific status:
**P0_INDEPENDENT_REVIEW_PASSED**. Six-year status:
**SIX_YEAR_EXECUTION_BLOCKED**.

Approval source: `D:/Download_all/AirSlot_Cleanup_Independent_Approval_20261012.md`.
The latest user request authorizes all three documentation/design deliverables
below in this phase, each in a separate commit. Completion of DOC-1 is a batch
checkpoint, not authorization to implement C07/C08 or run experiments.

| Batch | Authorized change | Explicitly deferred |
| --- | --- | --- |
| DOC-1 (C04 + C09) | Current/historical entry documentation and this new status note | Python drivers, report-generator logic, old review packages |
| DEPENDENCY-DESIGN (C08) | Static core/parity/test/report classification and Linux lock design | requirements edits, package installation/removal, image or provenance-code edits |
| RECEIPT-DESIGN (C07) | Proposed schema, state machine, compatibility and acceptance plan | Receipt implementation, cache migration, existing hash/receipt rewrites |

C01/C02/C03/C05/C06, A01–A11 and D01–D04 remain deferred. There is no
deletion, archive/move, cleanup of untracked research objects, scientific model
rewrite, cloud connection, training, full Development run or Test permission.
Once the authorized documents and static checks are complete, the phase must stop
at **CLEANUP_DOC_ONLY_COMPLETE_REVIEW_PENDING** for independent review.

## Retained annual input gaps

The existing 21-path list was checked by filesystem existence only in this phase;
all 21 remain missing. Source list:
`artifacts/experiment/jatm_s34/independent_review_p0_20261012/ANNUAL_GAPS_CURRENT.json`.

| Year | Missing required paths under artifacts/models/m1/YEAR_year | Count |
| --- | --- | --- |
| 2017 | None of the previously listed gaps; this is not new full-run readiness acceptance | 0 |
| 2018 | TAIL_REFERENCE_V1/MANIFEST.json | 1 |
| 2019 | M1_HISTORY_PRIMARY.pt, M1_HISTORY_PRIMARY_MANIFEST.json, M1_CURRENT_COMPARATOR.pt, M1_CURRENT_COMPARATOR_MANIFEST.json, TAIL_REFERENCE_V1/MANIFEST.json | 5 |
| 2020 | Same five annual filenames, bound to YEAR_2020 | 5 |
| 2021 | Same five annual filenames, bound to YEAR_2021 | 5 |
| 2022 | Same five annual filenames, bound to YEAR_2022 | 5 |

No automatic retraining, tail rebuilding or cross-year substitution is authorized
here. Existing models, tails/chunks, Year-local and FIXED_COMMON references, state
caches, checkpoints, scientific outcomes and review evidence remain protected.

## P0 acceptance and open P1 are separate

- Retain canonical C1, contrast-keyed C2 and separate rolling C3; C0 sealed
  evidence is not accessed. Unsupported earliest canonical cases are not replaced.
- Retain primary L_rec as ratio of sums, paired episode bootstrap with multiplicity,
  and the P0 fail-closed annual/E4/scheduler completion gates.
- F_continuity time-coordinate science reconciliation remains open.
- E1 exposure-specific recovery Coverage@K, the required E2 contrast/grid coverage,
  E3 signed-difference export and sensitivity/mechanism reporting, and E4 rolling
  uncertainty/environment heterogeneity remain incomplete or require explicit limits.
- Fixed nominal Stage-II 41/45/0.25 is a retrospective common policy, separate from
  annual Train headroom sensitivity. Metadata must not imply annual fitting of
  those constants. Approved annual tails and V5 CU contracts remain unchanged.
- Exact product Marginal is not asserted physically feasible; mechanism nulls or
  regrets must not be forced to zero. Negative results remain valid evidence.
- Stage-level receipt reuse is a proposed reliability change, not yet implemented.
- Linux, CUDA, Docker/systemd and container/throughput benchmarks remain NOT_RUN.

## Source identity impact and evidence

Only Markdown deployment/design files are authorized to change. The current
execution_identity, action_algorithm_hash and evaluation_identity hash scientific
Python/config/input sources; these documentation paths are outside those source
lists. The intended impact is therefore **no scientific algorithm/input hash
change**. Git HEAD and any newly generated whole-source/transfer package hash may
change, so later packaging must truthfully record its own version; no old manifest,
CODE_SNAPSHOT or receipt is rewritten to the new documentation commit.

The original P0_REVIEW_NOTES.md and all previous handoff/audit originals remain
unchanged. The baseline remains an ancestor in Git; separate documentation commits
can be reverted individually after authorization. No history rewrite is needed.

Per-batch changed paths, full Git patches, static checks and final commit IDs are
recorded separately under
`artifacts/experiment/jatm_s34/cleanup_doc_only_20261012/`. Checks cover document
links, source/CLI argument declarations, exact staged paths, diff whitespace and
unchanged source/deployment implementation. They are not scientific tests or
Linux/CUDA acceptance. Prior scientific tests are not rerun for Markdown changes.
