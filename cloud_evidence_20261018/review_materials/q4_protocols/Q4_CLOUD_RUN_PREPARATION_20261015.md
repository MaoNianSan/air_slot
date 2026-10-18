# Q4 cloud run preparation (2026-10-15)

## Current finding

There is no saved six-year S34 Q4 run. The saved S34 E1--E4 run is Development-only. The authorized extension remains six years, 4,096 Q4-contained episodes per year, frozen annual artifacts/settings, and unchanged E1--E4 scientific definitions. 2019 is an exposed-window replication.

## What the source supports

- Source tree to deploy: `review_v64_20261014/snapshot_code` at effective commit `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef` (snapshot `583f2c12` plus the two official patches recorded in the audit).
- Reusable code: annual reference/model/tail loaders, M1 bridge/evaluation modules, Q4 path enumeration when explicitly enabled, BTS canonicalization, episode construction and temporal containment, and S34 E1/E2/E3/E4 evaluation logic.
- Missing capability: the ordinary cohort/reservoir and PRE materialization path intentionally rejects `test`; the S34 annual bridge reads the preselected Development cohort. A separate Q4 adapter must create a fixed Q4-contained cohort and typed PRE/M1 inputs that satisfy the existing bridge contract. Keep this adapter outside the frozen Development code path.
- Exact cohort rank delimiter is literal `||`: `SHA256((M5-COHORT-SEED-20260928 + "||" + episode_id).encode("utf-8"))`. The selected IDs must be frozen before any predictions/consequences/results are derived.

## Deep audit result

The detailed blockers and code locations are recorded in `Q4_CODE_AUDIT_FINDINGS_20261015.md`. The run contract is now `Q4_EXPANSION_PROTOCOL_V3.md`, which supersedes V2 only for adapter, runner, and provenance controls. No frozen producer files were changed during this audit.

## Cloud binding checklist (before content reads)

1. Record server CPU count, RAM, free disk, OS, Python/CUDA versions, and available worker capacity.
2. Bind the effective source tree and required annual inputs for all six years. Validate manifest hashes for M1 checkpoints, M2 references, tails, PRE/headroom/consequence artifacts, raw input file sizes and hashes, and code/environment identity.
3. Verify the output root is new, isolated, and has enough capacity. Assign per-year scratch/output paths and logs; keep source/model inputs read-only.
4. Confirm the adapter's cohort-only path has no route into E1--E4 outputs. Persist access accounting and selected-ID hashes.
5. Resource target: three concurrent years if measured RAM/disk permit. Start one resource-only bounded materialization on an approved year, measure peak RSS and throughput, then launch a three-year wave. Do not inspect outcomes during this capacity pilot.
6. Run year-local completion checks before the next wave. Preserve resumable state and never mark partial years complete.

## Work to finish as soon as server details arrive

- Deploy the exact effective producer and isolated adapter.
- Execute the no-Q4-content binding preflight across all six years.
- Complete adapter engineering validation on synthetic/Development-derived inputs only.
- Freeze and write cohort IDs for the first three years, then launch three annual workers if resource checks pass. Repeat for the remaining years.
- Keep all new artifacts in the separately named Q4 extension root; produce a final manifest with per-year status, cohort hash, access counts, producer identity, frozen artifact hashes, and E1--E4 completion state.

No Q4 raw CSV contents have been read for this extension, and no Q4 outcomes have been generated as of this preparation note.
