# C07 independent implementation and acceptance proposal

**DESIGN_ONLY / IMPLEMENTATION_NOT_AUTHORIZED**, 2026-10-12.
Scientific baseline: `e278ac55871dd3208bbd9a55e24b0d7a94314c96`.
**P0_INDEPENDENT_REVIEW_PASSED / SIX_YEAR_EXECUTION_BLOCKED**.
This document defines a future bounded reliability task. It changes no Python,
receipt, cache, scientific output or statistical estimand. See
[current authority and limits](CLEANUP_DOC_ONLY_STATUS.md).

## 1. Problem and scope

At the baseline, `shared_run.evaluation_is_current` checks a single
`EVALUATION_COMPLETE.json` with one evaluation identity and exactly three summary
hashes: E1, E1_FIXED_COMMON and E2_E3. `_run` recomputes all three evaluations when
that combined check fails. SharedStore already validates atomic chunk/node data
commits; progress counts alone are not a resume mechanism.

Proposed improvement: retain independent, content-validated completion receipts
for these **three evaluation stages**, so an interruption after valid E1 does not
force another 2,000-replicate bootstrap. Keep E2 and E3 together in this first change;
they share action results, support and statistical outputs. No new scientific
pipeline, solver, bootstrap approximation or cache-hash override is proposed.

The target is avoided recomputation after interruption, not a claim of measured
speedup. Stage-specific algorithm invalidation must be conservative: saving time
never permits accepting a dependency whose current identity cannot be verified.

## 2. Protected contracts and future edit scope

Preserve PRE/M1/M2/M3/M4, exact weighted Marginal, complete action enumeration,
four mechanism structures and their own Joint evaluators, canonical C1, independent
contrast-keyed C2, rolling C3, both CU tracks and primary ratio-of-sums L_rec.
Bootstrap remains 2,000 paired episode draws under the approved seed/definition.
Valid undefined zero-denominator statistics remain undefined, not fabricated zero.

Potential future changes are limited to shared_run receipt orchestration,
shared_store-compatible receipt I/O, e4_shared_aggregate receipt consumption and
targeted contract/recovery tests. Scheduler adaptation is allowed only if needed
to read the same fail-closed outcome contract; no weaker success condition.
Do not fold C01/C02/C03/C05/C06 extraction into this change.

No alteration of model weights, annual tail, CU references, canonical identity,
candidate/support populations, q, action grid, nominal headroom, objective or
statistical algorithm is part of receipt implementation. New helper files, if
necessary, must be included in the relevant code identity; helper extraction is
not implicitly authorized by this design.

## 3. Proposed three-stage dependency map

| Stage ID | Required inputs and independent validation | Required scientific outputs |
| --- | --- | --- |
| E1_YEAR_LOCAL | Current annual cache identity, complete shared score manifest and exact node-table hash; legal year/split/cutoff, annual tail/model/CU bindings, canonical/support contract, q/views/tie-break, bootstrap/seed | E1/E1_PAIRED_SUMMARY.json; E1_POINT_EQUIVALENCE.json as computation/legacy-comparison evidence with its actual status |
| E1_FIXED_COMMON | Same valid scientific source; fixed_common shared manifest/table and approved 2017-H1 CU reference; same E1 statistical contract | E1_FIXED_COMMON/E1_PAIRED_SUMMARY.json and corresponding point-evidence file |
| E2_E3 | Shared score identity, legally supported restorable states and M2 bindings; nominal headroom/effort policy; both CU references; all representation/population/operator identities; action-store commits and native-response ledgers | E2_E3/E2_E3_SUMMARY.json plus the referenced scientific action/ledger closure required for reproducibility |

This is a proposed minimum output contract to finalize against actual writers
before implementation. Mutable PROGRESS files, elapsed time and log offsets are
observability, not completion proofs. A point-evidence file without a paired summary
does not complete E1. `POINT_ESTIMATES_COMPUTED_NO_LEGACY_COMPARISON` does not claim
legacy parity. E2/E3 summaries must retain seven-component responses, population
support, per-node results, paired statistics, objectives and mechanism records;
receipt splitting cannot discard them to reduce file count.

E1_FIXED_COMMON and E2_E3 consume shared science, not the E1 summary. Their receipts
do not require valid E1 merely to exist; the annual completion record requires
**all three**. The initial implementation should preserve sequential execution
order and resource use; introducing concurrent evaluations is a separate change.

## 4. Proposed schema (not a created runtime file)

Suggested new namespace: `<annual-output>/receipts_v2/`, with immutable attempt
receipts and an atomically published selection/completion index. None is created
in this phase. The shape below is illustrative; angle-bracket values are schema
placeholders, not real hashes or generated results.

```json
{
  "schema_version": "JATM_STAGE_RECEIPT_V2",
  "stage": "E1_YEAR_LOCAL",
  "attempt_id": "<unique-local-attempt>",
  "year": 2017,
  "split": "development",
  "scope": "FULL_DEVELOPMENT",
  "cu_tracks": ["YEAR_LOCAL"],
  "status": "COMPLETE",
  "identity": {
    "source_identity_hash": "<current-verified-shared-identity>",
    "inputs": [{"path": "<relative-path>", "sha256": "<raw-bytes-hash>"}],
    "scientific_contract_hash": "<population-score-objective-statistics-contract>",
    "algorithm_sources": {"<repo-relative-python-path>": "<LF-normalized-source-hash>"},
    "algorithm_hash": "<canonical-source-map-digest>",
    "evaluation_parameters": {"replicates": 2000, "seed": 20261011},
    "execution_contract_hash": "<year-split-cutoff-model-tail-CU-backend-contract>"
  },
  "identity_hash": "<canonical-identity-digest>",
  "outputs": [{"path": "<relative-path>", "size_bytes": 0, "sha256": "<raw-bytes-hash>", "schema": "<output-schema>"}],
  "validation": {"status": "PASS", "contract_version": "<validator-version>"},
  "provenance": {"git_head": "<producer-commit>", "final_test_access_count": 0},
  "receipt_hash": "<canonical-receipt-without-this-field-digest>"
}
```

`size_bytes: 0` above is a type example only; real nonempty outputs require their
actual lengths. Missing, malformed or invented hashes cannot validate. Suggested
required field rules:

- `stage`, `year`, split, scope and CU track tuple are exact enums/identities.
  E2_E3 includes YEAR_LOCAL and FIXED_COMMON, not an ambiguous single-scale label.
- Required fields cannot be dropped by defaulting. Old schema is accepted only
  through its explicit legacy validator, never by treating missing V2 fields as valid.
- The validator independently computes expected identity from current authorized
  inputs/source and approved parameters; it never compares saved identity only to
  itself. Record cohort/canonical/support hashes, N4096 annual model/tail identities,
  Train/Calibration/Development cutoffs and both scale provenance where applicable.
- Raw artifact byte hashes, LF-normalized source hashes and canonical JSON digests
  retain their separate existing meanings. Do not unify their encodings as cleanup.
- Bootstrap version, B, seed, q grid/views, estimand, population key and mechanism
  operator version must be explicit in contract identity, as applicable to stage.
- Required output paths form a stage-specific allowlist, not a caller-supplied
  arbitrary subset. Reject path traversal, wrong roots, duplicate paths and outputs
  bound to another year/attempt/track. Generated timestamps must not be part of the
  scientific identity solely to force new computation.
- `git_head` is producer provenance. A new docs-only HEAD alone is not a scientific
  equivalence proof and must not be substituted into an old receipt. Reuse still
  requires all expected input/algorithm/output identities to match.

The first implementation should err on broad source dependency coverage. Narrowing
an algorithm hash to make more cache hits requires a reviewed dependency argument;
it is not permission to ignore scientific code changes. If stage-specific hashing
cannot be established safely, shared invalidation is preferable to stale reuse.

## 5. State machine and atomicity

```text
MISSING -> RUNNING -> OUTPUTS_WRITTEN -> VALIDATING -> COMPLETE
             |               |              |
             +-------------> FAILED / PAUSED / INVALID
COMPLETE -- current revalidation succeeds --> REUSABLE (skip this stage)
COMPLETE -- input/algorithm mismatch ------> STALE (not reusable)
COMPLETE -- missing/corrupt output --------> INVALID (not reusable)
```

Only a validated COMPLETE receipt permits a skip. RUNNING, completed_chunks,
completed_replicates, an output filename or process exit 0 alone never does.

1. Acquire the existing single-writer protection; check stop/ownership before a
   new attempt. Do not break live or remote locks automatically.
2. Read any existing stage receipt and verify schema, identity and complete
   required output closure. If valid, reuse exactly those outputs without calling
   E1 bootstrap or E2/E3 computation. Log the verified reuse, not a new experiment.
3. If missing/invalid/stale, preserve existing receipts and evidence. Recompute only
   under execution authorization into a new versioned attempt/output location.
   Do not overwrite valid or corrupted old scientific evidence in place.
4. Flush and atomically publish each output, then validate scientific output
   structure and expected hashes. Publish immutable stage completion last.
   A crash after output writing but before receipt commit remains incomplete;
   file existence must not reconstruct success by guesswork.
5. After all three stages are valid, atomically publish a new annual evaluation
   index binding their exact receipt hashes and shared identity. Failure or safe
   stop before this leaves the year incomplete; previously valid stage receipts
   survive for resume. An old index referring to another attempt is not current.

Versioned attempt directories and selected paths must be consumed consistently by
the annual reader and E4. The implementation must choose a reviewable path contract;
it must not copy new hashes into old files just to preserve hard-coded paths.
This is a small receipt/index extension, not a new scheduler or database.

## 6. Legacy reader and receipt compatibility

Keep `EVALUATION_COMPLETE.json`, existing stage summaries, SharedStore commits and
all historical receipts immutable. Keep the baseline legacy reading rules available.

| Existing evidence | Proposed behavior |
| --- | --- |
| Only valid legacy receipt, all three outputs and expected input/algorithm identities valid | Legacy complete read remains supported; it proves the original combined completion, not newly computed V2 stages |
| Legacy receipt missing/invalid or one required output corrupt | Do not salvage stage success from that receipt by discarding its failed checks; preserve evidence and require approved stage computation/validation |
| Legacy algorithm hash differs after future implementation | No automatic equivalence alias. Use a new output version, or seek separately reviewed equivalence migration; current approval authorizes neither |
| Valid V2 receipt for one/two stages, no valid combined completion | Reuse individually only after full current validation; annual/E4 status remains incomplete until all stages are valid |
| Both schemas exist | Selected namespace/attempt must be explicit and verified. A corrupt current V2 index cannot silently fall back to an older legacy success |
| Old reader opens old artifacts | Continue baseline behavior without file rewrites; it must not falsely accept V2 partial outputs as legacy complete |

No synthetic backfilling of per-stage claims into an invalid combined receipt.
Any future metadata-only compatibility index must preserve original receipt hash,
producer version and exact output paths, and explicitly record that no computation
occurred. It is not necessary for the first implementation and not authorized now.

## 7. P0 completion gate must remain fail-closed

An annual evaluation may report COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE only with
the correct full Development scope, valid current annual scientific identity,
all three stage completions, both CU tracks, required statistical/output schemas
and no protected-access provenance. Stage-I-only, pilot, missing tail/model,
failed stage and missing ledger remain incomplete or blocked.

E4 must inspect all six distinct years 2017–2022 with existing P0 population and
ratio-of-sums contracts, 2,000 bootstrap configuration and full-run outputs.
Scheduler exit status, queue exhaustion, the number of receipt files or a
valid E1 summary cannot replace this inspection. Missing/failed years retain
SIX_YEAR_EXECUTION_BLOCKED or PARTIAL_DEVELOPMENT; valid years are not relabeled
as scientific failures merely because another year is blocked.

Even six computed years remain pending scientific review. Receipt verification
does not close P1, confer DEVELOPMENT_COMPLETE, authorize cloud execution or
grant Test/Final-Test access.

## 8. Targeted future acceptance matrix (planned, not run)

Use small fixtures for crash/mismatch states and the existing authorized small
Development evidence for the one necessary end-to-end resume comparison. No
new training, M5-b, full annual run, broad suite or Test access is required.

| Case | Expected result / measurable check |
| --- | --- |
| T01 All three stage receipts valid | Three validated skips; zero evaluator, bootstrap and M1 calls; same scientific result payloads |
| T02 E1 complete, E2/E3 raises | E1 remains reusable; only missing/invalid stages run on resume; annual status incomplete until completion |
| T03 FIXED_COMMON E1 fails | YEAR_LOCAL E1 preserved; retry fixed-common evaluation without redoing its valid sibling; E4 blocked meanwhile |
| T04 One summary missing/truncated/byte-mutated | Corresponding receipt INVALID; no skip; other stages reusable only if their own dependencies remain valid |
| T05 Referenced action commit/native ledger corrupt | E2/E3 rejected even if top-level summary hash matches; preserve corrupted evidence for diagnosis |
| T06 Output written, process stops before receipt publication | No COMPLETE; no completed-count/file-existence inference; recovery follows approved attempt protocol |
| T07 Receipt claims completion with empty output set, altered hash, unknown schema or wrong required set | Rejected; never treat vacuous hash checks as success |
| T08 year/model/tail/cohort or cutoff mismatch | Reject affected stage; no cross-year fallback, Train/Test substitution or caller-supplied identity acceptance |
| T09 YEAR_LOCAL/FIXED_COMMON or source-year mismatch | Reject; a valid 2017 fixed-common reference cannot masquerade as another year's Year-local scale |
| T10 q/support/canonical/seed/B/estimand/operator mismatch | Reject affected identity; no changed population, bootstrap reduction or mechanism alias |
| T11 Valid legacy combined receipt | Accepted through legacy validator only when current expected dependencies match; preserve old bytes |
| T12 Invalid legacy receipt / new algorithm hash / corrupt V2 with old success present | Fail closed; no opportunistic downgrade or forced hash rewrite |
| T13 Partial-file stop, second writer, stale/remote lock | Atomicity/single-writer behavior preserved; no live-lock deletion; valid sibling outputs survive |
| T14 2017 succeeds, 2018 lacks tail, remaining years lack models | Independent outcomes retained; SIX_YEAR_EXECUTION_BLOCKED, no complete E4 signal |
| T15 Six files but duplicate year, pilot scope, wrong contract or nonzero protected-access field | Complete path rejected |
| T16 Six distinct valid full-year mocked records | E4 completion path eligible, still COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE / human review; no claim of real six-year execution |
| T17 Existing small Development cache, uninterrupted versus interrupted/resumed evaluation | Identical selected IDs, four-view point estimates/paired CIs, C1/keyed C2/C3, ratio-of-sums, objective/action/mechanism outputs and valid replicate counts; compare scientific fields excluding timing/provenance timestamps |
| T18 Docs-only commit versus genuine scientific-source change | No forced HEAD-based cache relabel; current scientific hashes decide reuse; scientific change is not ignored |
| T19 Negative/nonsignificant outcomes, zero reference denominator and legal exclusions | Preserve results and undefined values; never turn statistical non-gain into cache rejection or force zero regret |
| T20 Receipt/output path escapes annual root or refers to another attempt | Reject before data access outside declared legal roots |

T17 should use the established 2-episode/5-canonical-node evidence with its actual
tail/CU provenance clearly recorded. Legacy-tail cache and current-tail golden are
distinct sources and must not be conflated. Preserve B=2,000 for statistical parity;
lightweight receipt unit cases do not need to recompute bootstrap repeatedly.
Record exact input hashes, code version, evaluator call counts, recomputed stages,
reused stages and checks. Any approximation or scientific-contract change requires
a separate decision, not a modified tolerance to pass acceptance.

## 9. Separate future implementation/review gates

1. Obtain explicit C07 implementation authorization for the final schema, output
   allowlists, dependency identity and legacy strategy. This document is the
   approval candidate, not that authorization.
2. Implement in an isolated, narrowly scoped commit while preserving baseline
   source/receipts and active-job safety. Do not run authorized old jobs with
   hot-replaced modules. Update source-identity coverage for any new helper.
3. Run only affected contract/recovery cases plus one representative real-data
   comparison; capture logs, scientific-field comparisons, immutable source and
   input hashes, and evidence of zero repeated completed-stage evaluator calls.
4. Submit code, exact commit/diff, outputs and limitations for independent review.
   Rollback selects the retained baseline code/output namespace; do not rewrite
   old caches. No files are deleted or moved to implement rollback.
5. Linux behavior/performance, annual input completion, P1 science and formal
   Development execution remain separately authorized stages. The present
   documentation phase stops at CLEANUP_DOC_ONLY_COMPLETE_REVIEW_PENDING.
