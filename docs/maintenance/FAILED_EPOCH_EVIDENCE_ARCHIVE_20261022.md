# Failed-epoch evidence archive (2026-10-22)

Context: the project has moved from the testing stage to the delivery stage. The
two failed Final-Test epochs stay on record, but their multi-hundred-megabyte
checkpoint payloads no longer need to sit in the working tree.

## What stays (unchanged on disk)

- `artifacts/experiment/final_test_v2_stage_matched_canonical_v1/` — 15 files,
  tree hash `sha256:5bff383e2ccbd5254aaa5bda17c27bd3c5b5b581da32630580568ee55afa33b9`, still matches
  `formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V2.json` byte for byte.
- `artifacts/experiment/final_test_v2_stage_matched/` — the seal and audit files
  (`EPOCH_SEAL.json`, `FINAL_TEST_EXECUTION_RESULT.json`,
  `GATE_B_HUMAN_RELEASE.json`, `PHASE7_ACCESS_AUDIT.json`,
  `POST_EXECUTION_AUDIT.{json,md}`, `LARGE_ARTIFACT_MANIFEST.json`) and the
  smaller checkpoints.
- `formal/JATM_STAGE_MATCHED_FINAL_TEST_FREEZE_V1/V2.{json,md}` — the frozen
  records still state the original tree hashes, including for the archived
  payloads.

## What was archived

Two gitignored payloads of the non-canonical epoch were moved out of the
working tree (kept in a local quarantine directory, not deleted):

- `checkpoints/CONSEQUENCE_VARIANTS.json` (300.9 MB)
- `checkpoints/STATE_VARIANTS.json` (177.5 MB)

Consequence for verification: the live tree of the non-canonical epoch is now
14 files instead of the 15 recorded at freeze time (the frozen record was made
when exactly one of the two payloads was present; this checkout carried both,
so it already differed by one file before this archive). The recorded hash
`sha256:6c7bcc3ebb6a5565e24009b29ab4604078f94342d8d018d214a859d45823b2d3` in FREEZE_V2.json is the
authoritative statement of what that epoch contained; it cannot be recomputed
from local bytes any more.

## Effect on the gates

`tests/phase7/test_execution_freeze.py` still passes unchanged: it asserts the
epoch is present, that the committed files are there, and that the count is
`committed + payloads actually present on disk`. No assertion was weakened and
no test was skipped.

## Restoration

Move the two files back under
`artifacts/experiment/final_test_v2_stage_matched/checkpoints/`. Nothing else
needs to change.
