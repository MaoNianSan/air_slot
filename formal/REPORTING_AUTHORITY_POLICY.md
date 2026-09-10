# Air Slot Reporting Authority Policy

Status: `PAPER_FREEZE_DOCUMENTATION_POLICY`

This policy prevents a derived report, a hardcoded narrative sentence, or a
typeset value from being treated as an independent scientific numerical source.
It is additive to `formal/FINAL_TEST_PROVENANCE_RECONCILIATION_V1.json` and
does not alter the manuscript, Final Test artifacts, report generator, or
historical authority records.

## Numerical Authority Order

1. The immutable pre-access cohort authority and the post-access audit establish
   Final Test lifecycle provenance. They do not replace executed result values.
2. For Exp1--Exp4, the executed artifacts in
   `artifacts/experiment/final_test/exp1` through `exp4`, together with their
   designated manifests, hashes, and authoritative files recorded by the B1
   reconciliation, are the paper numerical authority.
3. For aggregation robustness, the sole paper numerical authority is
   `artifacts/paper_results_v2_final_test/aggregation_robustness/` as recorded
   by the B1 reconciliation.
4. Tables, figures, PDFs, and Markdown reports are representations of the
   authoritative artifacts. A representation is evidence only to the scope
   and hash recorded in the applicable artifact manifest; it is never a basis
   for recomputing or superseding the underlying result.
5. Manuscript values are the approved communication layer for the frozen paper.
   This policy does not authorize their editing and does not make prose a
   replacement for the corresponding artifact-level numerical authority.

## Generated Reporting Boundary

`formal/final_test_run.py` generates reporting material from executed results.
Its report template includes a small number of literal scientific values and
counts in narrative prose. Those literals are derived presentation text only:

- they are not an additional Exp1 authority;
- they do not supersede a manifest, CSV, parquet file, or frozen figure listed
  as authoritative for an experiment;
- a later report-template edit, if ever authorized, requires an explicit
  artifact-to-prose reconciliation rather than copying a number by inspection.

The same rule applies to static reporting files under `formal/`: they document
or display results but do not alter producer provenance, frozen payloads, or
the B1 authority hierarchy.

## Reconciliation Procedure For A Future Discrepancy

If a table, figure, report sentence, or manuscript value appears inconsistent:

1. Identify the exact metric, result artifact, manifest, SHA-256, producer
   commit, and scientific scope.
2. Compare the representation with that designated authoritative artifact.
3. Record the discrepancy as `REPORT_ARTIFACT_DIVERGENCE`; do not infer a new
   number from prose and do not overwrite historical material.
4. Preserve the paper-freeze boundary. Any proposed correction, regenerated
   derivative, or manuscript change requires separate human authorization.

No discrepancy may be resolved by rerunning Final Test, retraining or
recalibrating M1, reselection, bootstrap regeneration, mutation of artifact
payloads, or mutation of the pre-access authority.

## Maintenance Rules

- Producer commits remain provenance. Different artifacts may validly have
  different producer commits; do not rewrite history to make them match a
  later audit head.
- Diagnostic, smoke, timing, Numba, and reduced-replicate outputs remain
  retained but non-authoritative where the B1 reconciliation classifies them
  as such.
- This policy classifies authority and reporting roles only. It does not
  change scientific formulas, statistical estimands, target aliases, support
  semantics, or manuscript claims.
