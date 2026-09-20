# Air Slot — Current Paper Authority

Status:

- FINAL_TEST_COMPLETE = YES
- PAPER_RESULTS_FROZEN = YES
- READY_FOR_FREEZE = YES
- scientific definition changed = NO

This file is the first repository-level authority pointer for the current JATM
paper state. Read it before using any experiment result, Final-Test artifact,
or manuscript value. Automated readers (Codex / web GPT sessions): treat this
file as the entry point; do not infer Final-Test status from anything on
`main` or from Development-branch reports.

Canonical sealed-epoch state (`v2/phase7-gate-a`):

- FINAL_TEST_EPOCH_SEAL_STATUS = SEALED_AUDIT_PASS
- execution_status = PASS
- post_execution_audit = PASS
- blocking_failure_codes = []

## Scientific authority hierarchy

### 1. Final held-out results / Final-Test authority

- branch: `v2/phase7-gate-a`
- scientific commit: `8360dd7d88958ae139322d0ea5c66f1c5fe6455c`
- valid epoch: `artifacts/experiment/final_test_v2_stage_matched_canonical_v2`

Authoritative evidence (repository-relative, on `v2/phase7-gate-a`):

- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/EPOCH_SEAL.json`
- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/FINAL_TEST_EXECUTION_RESULT.json`
- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/POST_EXECUTION_AUDIT.json`
- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/POST_EXECUTION_AUDIT.md`
- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/PHASE7_ACCESS_AUDIT.json`
- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/GATE_B_HUMAN_RELEASE.json`
- `formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json`
- `formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.md`

Exact final PAPER_VIEWS / checkpoint path (Section-5 paper-facing source):

- `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/checkpoints/PAPER_VIEWS.json`

  This checkpoint is part of the sealed epoch and is **not committed** to any
  branch: the `checkpoints/` tree is local to the sealed Phase-7 execution
  worktree (`D:\Local_Projects\airslot\_v2_phase7_execution\...`). Its identity
  is recorded in the committed `FINAL_TEST_EXECUTION_RESULT.json`
  (`file_sha256 = sha256:cfedca4f...`, `payload_hash = sha256:88b470ad...`;
  schema `AIR_SLOT_V2_PHASE7_PAPER_VIEWS_V1`). The same 10-stage atomic
  checkpoint set feeds `POST_EXECUTION_AUDIT.json` (all file/payload hashes
  PASS).

Verified identities (see `CURRENT_PAPER_AUTHORITY.json` for hash semantics):

- freeze content identity (`artifact_hash` of the freeze): `sha256:05b6327a...`
- `FINAL_TEST_EXECUTION_RESULT.json`: `sha256:0687b21a...`
- `EPOCH_SEAL.json`: `sha256:eb4a22a2...`
- `POST_EXECUTION_AUDIT.json`: `sha256:efb3c26a...`
- `POST_EXECUTION_AUDIT.md`: `sha256:60db1d5c...`

Locating tags: `jatm-final-test-freeze-20260920` → `8360dd7d...`.

### 2. Paper-primary / Section 4–5 implementation authority

- branch: `v2/paper-primary`
- scientific commit: `b753db8251812faec2eb2dbdabf34c325eb76f9b`

Important: Development reports on this branch are Development authority only.
Their `FINAL_TEST_COMPLETE=NO` fields describe the state at the time
Development was frozen and MUST NOT be interpreted as the current
repository-wide Final-Test status. Example, as of this commit:

- `artifacts/experiment/jatm_section5/development/report/JATM_SECTION5_DEVELOPMENT_REPORT.md`
  ("Final-Test complete: NO"; "Development ready for freeze: YES")
- `artifacts/experiment/jatm_section5/development/report/JATM_SECTION5_MANIFEST.json`
  (`final_test_complete = "NO"`, `development_ready_for_freeze = "YES"`)

Locating tag: `jatm-paper-primary-freeze-20260920` → `b753db82...`.

### 3. Default main

`main` is NOT the current scientific implementation branch.

`main` exists as repository/default navigation plus this authority pointer.
Current JATM scientific code/results live on the two V2 branches above
(`v2/paper-primary`, `v2/phase7-gate-a`). The final held-out results are not
on `main`, and the legacy `final_test_v2` outputs that exist on the V2 branches
are not the current paper authority.

## Do not use for current paper results

- `artifacts/experiment/final_test_v2/`
  = OLD PRE-STAGE-MATCHED FINAL TEST
  = NOT CURRENT PAPER AUTHORITY
  (committed evidence on `v2/phase7-gate-a`; its
  `PAPER_FACING_SECTION5_VIEWS.md` predates the stage-matched rerun and must
  not be used for current Section-5 values)

- `artifacts/experiment/final_test_v2_stage_matched/`
  = FAILED NONCANONICAL EPOCH
  = SEALED / INVALID FOR PAPER RESULTS
  (seal status `SEALED_AUDIT_FAILED`; blocking code
  `CANONICALIZATION_BEFORE_SUPPORT`; sealed local epoch, not committed)

- `artifacts/experiment/final_test_v2_stage_matched_canonical_v1/`
  = CANONICAL BUT SCIENTIFIC-OUTPUT-INCOMPLETE EPOCH
  = SEALED / INVALID FOR PAPER RESULTS
  (seal status `SEALED_AUDIT_FAILED_SCIENTIFIC_OUTPUT_INCOMPLETE`; blocking
  codes `PAIRED_MARGINAL_INCREMENT_NOT_EXECUTED`,
  `SECTION5_ROBUSTNESS_RESULTS_NOT_EXECUTED`; sealed local epoch, not
  committed)

- paper-primary Development result artifacts
  = VALID DEVELOPMENT EVIDENCE
  = NOT FINAL HELD-OUT PAPER RESULT AUTHORITY

- `artifacts/diagnostics/v2_phase7/gate_b0_dag/`
  = PRE-OPEN SAFE-FIXTURE DAG DUMP (development fixtures, access epoch not
  opened) = NOT FINAL-TEST PAPER RESULTS (its `PAPER_VIEWS.json` is
  fixture-based and must not be quoted as a paper view)

Only:

    artifacts/experiment/final_test_v2_stage_matched_canonical_v2

may be used for current held-out Section-5 results.

## Section 4 model-capacity interpretation

- H8 / H16 / H32 is a Section-4 M1 capacity diagnostic only.
- The diagnostic does NOT select or mutate the Section-5 downstream model.
- Section-5 primary model is: `H16_FROZEN_PRIMARY`.
- active model mutation = NONE.
- H-capacity downstream execution = NONE.
- Section 4 was not rerun during Final-Test execution
  (`SECTION4_H_CAPACITY_STATUS = REUSED_NOT_RERUN`, canonical-v2
  `POST_EXECUTION_AUDIT`).

Authoritative paper-primary H-capacity diagnostic files (branch
`v2/paper-primary`):

- `artifacts/diagnostics/jatm_section4/h_capacity/H_CAPACITY_SELECTION.md`
- `artifacts/diagnostics/jatm_section4/h_capacity/H_CAPACITY_SELECTION.json`
- `artifacts/diagnostics/jatm_section4/h_capacity/H_CAPACITY_MODEL_PERFORMANCE.csv`
- `artifacts/diagnostics/jatm_section4/h_capacity/H_CAPACITY_TARGET_PERFORMANCE.csv`

These are Section-4 capacity evidence only. Do not copy their numbers into
Section 5 claims.

## Section 5 manuscript source precedence

For manuscript filling:

1. canonical-v2 sealed Final-Test paper views / atomic checkpoints
   (`artifacts/experiment/final_test_v2_stage_matched_canonical_v2/checkpoints/`;
   identity committed in `FINAL_TEST_EXECUTION_RESULT.json`)
2. canonical-v2 POST_EXECUTION_AUDIT for validation / provenance
   (`POST_EXECUTION_AUDIT.json` / `.md`)
3. paper-primary implementation docs for definitions
   (`v2/paper-primary`)
4. Development outputs only for Development diagnostics, never final claims

Do not copy values from the old
`artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md`.

Publication note: this pointer is a documentation-only patch (2026-09-20). It
changes no scientific definition, no result artifact, and no sealed epoch.
