# Data Model

## RuntimeConfig

Scientific, reproducibility, and engineering mappings plus a stable `config_hash`, Python version, platform, device, and package versions. No virtual-environment identity.

## RunManifest

`run_id`, `run_kind`, `config_hash`, input/artifact hashes, ordered stage records, status, fixture/smoke flags, `paper_result=false`, creation time, runtime environment, and unresolved issues.

## StageRecord

Stage name, status (`PENDING|RUNNING|PASS|FAIL|ABSTAIN|SKIPPED`), input/output hashes, artifact paths, and typed reason code.

## ProgressEvent

Sequence, UTC time, run id, stage, status, completed/total units, and message.

## ArtifactValidationReport

Validation status, checked paths, errors, warnings, and paper-eligibility status.

