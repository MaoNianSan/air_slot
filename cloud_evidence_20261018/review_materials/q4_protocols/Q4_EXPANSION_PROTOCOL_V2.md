# JATM S34 Q4 extension protocol V2

Status: FROZEN BEFORE NEW Q4 OUTCOME ACCESS  
Supersedes: `Q4_EXPANSION_PROTOCOL_V1.md` for code identity and cohort-rank serialization only.  
Approved scope: six annual Q4 extensions of saved JATM S34 E1--E4 definitions.

## Scope

- Years: 2017--2022 independently; service dates October 1 through December 31 in each year.
- Unit: aircraft-linked episode. Retain an episode only when all source service dates, episode interval endpoints, and rolling decision times resolve to that year's `test` partition under `split_for_date_multiyear`. Exclude cross-window chains; never replace an episode for downstream lack of support.
- Select exactly 4,096 episodes per year from the Q4-contained eligible pool. Rank with the frozen cohort rule `SHA256(("M5-COHORT-SEED-20260928" + "||" + episode_id).encode("utf-8"))`, ascending hexadecimal digest, then episode ID as deterministic tie-break. Persist and hash the selected ID list before constructing PRE states, predictions, scenarios, support, consequences, or result tables. If a year has fewer than 4,096 eligible episodes, stop that year and record the shortfall; do not substitute a window or reduce N.
- Use the already fitted annual M1 artifacts, H1-frozen M2 references, annual tails, year-local headroom parameters, consequence scales, support thresholds, action grid, q grid, objectives, tie rules, and inference procedures from the S34 producer. No fitting, calibration, threshold/parameter selection, or reporting-choice selection on Q4 outcomes.
- Run the same S34 E1, E2/E3, and E4 definitions. E4 varies only its already frozen training-cohort grid and evaluates each fit on the same fixed Q4 cohort. No extra sensitivity combinations.
- Write to a new isolated root. Never overwrite Development outputs, source data, model artifacts, or prior Final Test outputs.
- 2019 Q4 was accessed in an earlier, different experiment. Label its new S34 outputs an exposed-window replication. The other five years have no prior Q4 access found in this audit; retain year-specific provenance and do not pool away the 2019 distinction.
- Report descriptive comparisons under the S34 reference criterion. Make no causal COVID claim and no claim of realized operational savings or independent external validity.

## Executable identity

- The six-year cloud producer is effective commit `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`, based on snapshot commit `583f2c12d54297ce6522285b44ff8bf008587308` plus patches `8cc7a1b7` and `1d3ba5d3`. V1's snapshot-only pin was incomplete.
- Before execution, record the full source-tree hash, dependency lock/environment, input manifest hashes, model/reference/tail hashes, and resolved bootstrap settings from this effective producer. Confirm the official Development precheck inputs still match; earlier official precheck passed, but the local partial-binding hash attempts are not evidence of mismatch.
- Existing Development entry points are not Q4-capable: `episode_reservoirs` rejects `test`, `materialize_preselected_cohorts` requires only train/calibration/development, and `iter_annual_bridges` materializes Development episodes only. Add a separate Q4 adapter/worker in the extension layer; preserve scientific evaluation functions and Development code unchanged. The adapter must use the frozen temporal resolver and episode containment, then feed the same typed states and annual bridge contracts to unchanged E1--E4 evaluators. If this cannot be done without changing scientific definitions, stop and revise this protocol before result access.
- First run code/environment/input binding checks that do not read Q4 file contents. Then run a bounded, outcome-blind cohort selection/materialization check; commit the selected-ID manifest before evaluation. Do not use pilot outcomes to tune any setting.

## Parallel execution and output isolation

- Target three independent annual workers at a time, subject to cloud CPU, RAM, and storage checks. Each worker owns one year, its own temporary state/cache, logs, and output directory. No shared mutable caches. Use a coordinator that starts at most three years, monitors heartbeat/RSS/disk, and resumes only from a validated year-local checkpoint.
- Suggested waves: 2017/2018/2019, then 2020/2021/2022, unless resources or input readiness require another order. The scientific settings and cohort rule remain identical across waves.
- Do not start the first wave until all six years' bindings and the isolated output root pass preflight. Run per-year E1/E2/E3/E4 only after that year's frozen cohort manifest is written and verified.

## Stop conditions

Stop a year before its result generation if code/artifacts mismatch, an input/model/reference/tail hash fails, eligible N is below 4,096, selected IDs are not deterministic, temporal containment fails, a Q4 adapter changes a scientific function, or resource limits cannot safely support chunked execution. Record the exact blocker; do not silently adjust scope or settings.
