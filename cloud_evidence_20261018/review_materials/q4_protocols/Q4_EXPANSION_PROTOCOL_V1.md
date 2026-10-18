# JATM S34 Q4 extension protocol V1

Status: FROZEN BEFORE NEW Q4 SOURCE READ  
Approved scope: six annual Q4 extensions of saved JATM S34 E1--E4 definitions.  
Source code: snapshot bundle commit `583f2c12d54297ce6522285b44ff8bf008587308` (six-year run producer).

## Scope

- Years: 2017--2022 independently; service dates October 1 through December 31 in each year.
- Unit: aircraft-linked episode. Keep an episode only when the frozen multiyear temporal split and episode-containment authority assign every required flight, interval, and decision time to that year's Q4 test window. Exclude cross-window chains; do not replace an episode for downstream lack of support.
- Select 4,096 episodes per year from the Q4-contained eligible pool using the same outcome-blind SHA256 ranking rule used for the annual Development cohort (`SHA256(M5-COHORT-SEED-20260928 || episode_id)`), ascending rank, deterministic tie break by episode ID. Freeze selected IDs before deriving predictions, scenarios, support, consequences, or results. If any year has fewer than 4,096 eligible episodes, stop for that year and record the shortfall; do not substitute another window or reduce N.
- Use the already fitted annual M1 artifacts, H1-frozen M2 references, annual tails, year-local headroom parameters, consequence scales, support thresholds, action grid, q grid, objectives, tie rules, and inference procedures from the S34 producer. No fitting, calibration, threshold/parameter selection, or reporting-choice selection on Q4 outcomes.
- Run the same S34 E1, E2/E3, and E4 evaluation modules. E4 varies only the already frozen training-cohort grid and evaluates each fit on the fixed Q4 cohort. Do not run extra sensitivity combinations.
- Persist outputs in a new, isolated root. Never overwrite the Development outputs, source data, model artifacts, or prior Final Test outputs.
- 2019 Q4 was accessed in an earlier, different experiment. Its new S34 outputs are an exposed-window replication and are not described as an untouched confirmatory test. The other five years have no prior Q4 access found in this audit; retain their own year-specific provenance and do not pool away the 2019 distinction.
- All yearly results are descriptive comparisons under the S34 reference criterion. No causal COVID claim; no claim of realized operational savings or independent external validity.

## Statistical and code identity

- Reuse the exact executable bootstrap settings, resampling unit, estimator, and support handling from the pinned S34 producer; record the resolved values and source hashes in the run manifest before result generation.
- Permitted implementation changes are limited to an isolated Q4 cohort/input adapter and test-scoped output/access accounting. Scientific functions and definitions are reused unchanged. Any necessary scientific-function change blocks execution and requires a revised protocol before result access.
- The historical 2019 access total is recorded separately. This extension gets its own access epoch and manifest; it does not rewrite or reset prior access records.
- First run a bounded engineering preflight that materializes no Q4 outcomes and writes no paper results. It may verify source paths, code bindings, environment, and output isolation. A bounded execution pilot may assess resource use only; its outputs cannot be used to choose scientific settings.

## Stop conditions

Stop before producing year results if code and saved Development artifacts do not share the pinned producer contract, a model/reference/tail hash does not match, Q4 cohort selection is not deterministic, temporal containment fails, the Q4 adapter needs a scientific change, or memory/storage cannot safely support chunked execution. Record the exact blocking item without modifying the frozen scope.
