# Air Slot Output Retention Policy V2

This policy governs generated artifacts and reports.  It does not change
scientific parameters, model behavior, the baseline seal, or data boundaries.

## Classes

- **ACTIVE_AUTHORITY**: an object selected by the active model/artifact index.
- **ACTIVE_FIXTURE**: a frozen regression or golden fixture selected by the
  active index.
- **IMMUTABLE_PROVENANCE**: a source snapshot or supersession record required
  to explain the sealed V1/V1R1 implementation.
- **KEEP_PROVENANCE**: a historical input still referenced by runtime,
  configuration, tests, validation, or an explicit closure record.
- **ARCHIVE_MINIMAL**: a small registry/config/report retained only when it
  answers a provenance question that cannot be answered by the active seal.
- **REGENERABLE_OUTPUT**: generated output that can be recreated from the
  active implementation and is not a scientific authority.
- **HISTORICAL_ARCHIVE**: legacy output retained only while it has independent
  provenance value.  It is not a default retention class.
- **REVIEW**: an unresolved classification.  V2 requires this to be zero or
  at most a small, explicitly explained set.

## Rules

1. Active authorities, fixtures, immutable provenance, and referenced inputs
   are never deleted by the automated cleaner.
2. Diagnostic, smoke, cache, per-node, bootstrap, plot-source, and temporary
   outputs are not permanent by default.
3. Historical experiment and paper outputs are deleted unless a minimal
   manifest or final closure record is explicitly retained.
4. Duplicate content keeps one canonical copy; immutable paths always win.
5. Validation runs use temporary directories.  A frozen validation artifact is
   created only by an explicit materialization command.
6. Validation commands are read-only/in-memory by default; use an explicit
   `--materialize` flag when a frozen validation output is intentionally
   published.
7. Active selection uses explicit indexed paths only; timestamp or newest-file
   discovery is prohibited.
8. Final Test values are outside this cleanup audit.  Final Test paths are
   handled by filename/provenance classification only; no values are read or
   reanalyzed.

The machine-readable plan is
`reports/output_refactor/OUTPUT_DEEP_CLEAN_PLAN_V2.csv` and is checked by
`python -m validation.validate_output_retention`.
