# JATM S34 Q4 extension protocol V3

Status: FROZEN BEFORE NEW Q4 OUTCOME ACCESS  
Supersedes V2 only for required Q4 adapter, runner, and provenance controls. The approved scientific scope and cohort rule are unchanged.

## Scope and cohort

- Years: 2017--2022 independently; October 1 through December 31 of each year.
- Unit: aircraft-linked episode. Retain only when all source service dates, episode interval endpoints, and rolling decision times resolve to that year's `test` partition under `split_for_date_multiyear`. Exclude cross-window chains; do not replace an episode for downstream lack of support.
- Select exactly 4,096 Q4-contained eligible episodes per year. Rank using `SHA256(("M5-COHORT-SEED-20260928" + "||" + episode_id).encode("utf-8"))`, ascending hexadecimal digest, then episode ID tie-break. Persist and hash the selected-ID list before PRE-state, prediction, scenario, support, consequence, or result generation. If eligible N is below 4,096, stop that year; do not substitute a window or reduce N.
- Use frozen annual M1 artifacts, H1-frozen M2 references, annual tails, year-local headroom, consequence scales, support thresholds, action/q grids, objectives, tie rules, and inference procedures. No Q4 fitting, calibration, threshold/parameter selection, or reporting-choice selection.
- Run the same E1, E2/E3, and E4 scientific definitions. E4 uses its frozen training-cohort grid and the same fixed Q4 cohort. No new sensitivity combinations.
- Use a new isolated output root. Keep the earlier 2019 Q4 exposure labeled as an exposed-window replication; identify the other five years separately. Report descriptive comparisons only.

## Code and adapter requirements

- Producer identity: effective commit `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`, based on snapshot `583f2c12d54297ce6522285b44ff8bf008587308` plus official patches `8cc7a1b7` and `1d3ba5d3`. Bind full source, environment, annual inputs, model/reference/tail artifacts, and resolved bootstrap settings in the run manifest before computation.
- Build the Q4 episode pass separately. Do not use the Development `episode_reservoirs` for Q4: it rejects `test` and its month counter assumes January-first paths. Derive months from path partitions; use the frozen episode builder, multiyear split resolver, and containment rules.
- Build PRE states through an isolated Q4 materializer. Retain the frozen replay lag and decision-time availability rules, and make Q4 weather observations available through the eligible Q4 node window. Hash and count every Q4 source. Keep the Development materializer's Oct 1 weather cutoff and all Development guards unchanged.
- Build a Q4 bridge/cache adapter for frozen M1 inference and S34 evaluators. Keep true `split=test` in data and manifests. Do not relax the M1 Development cache guard or persist Q4 observations under a Development label.
- Use separately namespaced E1/E2/E3/E4 Q4 runners or an explicit, hash-bound dispatch seam. Q4 receipts must identify `split=test`, report actual positive access counts, and carry Q4 status/schema labels. No Development `final_test_access_count=0` fields may be copied as if they described Q4 execution.
- E1, E2/E3, and E4 consume the same immutable, frozen 4,096-episode cohort and PRE/M1 bridge. Avoid multiple simultaneous rebuilds of one year's mutable state.

## Cloud schedule

- Target three independent years in parallel, subject to measured CPU, RAM, and disk. Use isolated per-year scratch/cache/output directories and logs; keep inputs/models read-only. Suggested waves are 2017/2018/2019, then 2020/2021/2022.
- Before Q4 content access, bind and hash all six years' code, models, references, tails, raw on-time inputs, weather inputs, output root, and environment. A bounded engineering check may verify structure/resources but must not generate outcomes or select settings.
- After cohort-only extraction, freeze and verify each year's selected-ID manifest before its E1/E2/E3/E4 result generation. A resource pilot may measure time and memory only; do not inspect its outcomes to tune settings.
- A year can resume only from hash-validated year-local checkpoints. Mark a year complete only after all stages and output hashes pass.

## Stop conditions

Stop before result generation on any source/model/hash mismatch, eligible N below 4,096, nondeterministic selection, failed containment, Q4 feature availability leakage, adapter changes to scientific definitions, incorrect access accounting, or unsafe resource use. Record the blocker; do not silently adjust scope/settings.
