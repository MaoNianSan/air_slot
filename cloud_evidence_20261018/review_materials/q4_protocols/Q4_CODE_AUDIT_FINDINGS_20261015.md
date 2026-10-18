# Q4 extension code audit findings (2026-10-15)

Scope: static inspection of the effective six-year producer at commit `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`. No Q4 source contents were read and no outcomes were generated.

## Deployment identity warning

The existing `q4_extension/code` checkout is still at `583f2c12d54297ce6522285b44ff8bf008587308`, not the effective cloud producer. Its working tree also contains untracked annual M1 and M2 artifact directories. Do not deploy that checkout as-is. Use `snapshot_code` at `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef` as the immutable base, then layer only the versioned Q4 adapter/runner on top and record the overlay hash. Keep the untracked artifact directories preserved; bind inputs explicitly rather than relying on their presence in this working tree.

## Findings that must be addressed before cloud execution

### 1. Q4 source paths alone do not work with the current episode reservoir

`model/PRE/streaming/data2.py::episode_reservoirs` intentionally raises `FINAL_TEST_EPISODE_MATERIALIZED` for `test`. It also enumerates supplied paths starting at month 1 and builds `month_key` from that counter. Passing only October–December paths would treat them as January–March and discard records. Do not call this Development reservoir for Q4. A separate Q4 pass must derive the month from each path partition, build candidates, run frozen containment, and retain the deterministic lowest 4,096 cohort ranks.

### 2. Weather is clipped before Q4

`model/PRE/development.py::materialize_preselected_cohorts` calls `weather_index(..., end_exclusive=date(year, 10, 1))`. A copied Q4 path that keeps this bound has no October–December weather observations available to `latest_weather` when constructing decision states. The Q4 adapter must read the already available year-specific NOAA stream through the Q4 decision-time window, preserve the replay-lag rule, and enforce `availability_time <= information_cutoff` exactly as before. Record its raw weather manifest/hash and count separately. Confirm whether end-of-December decision nodes can require the next-year observation; containment should exclude nodes outside the year-specific test window, and the adapter must not silently widen the episode window.

### 3. PRE and M1 development-only guards block direct Test materialization

`materialize_preselected_cohorts` requires exactly train/calibration/development partitions, validates dates only against those splits, clips weather before Q4, and returns a Development-specific container. `M1CanonicalRaggedStore.from_partitions` rejects unknown `test` partitions and dates at/after `final_test_start`; the cache manifest hardcodes `final_test_included=false` and access count 0. These frozen guards must remain intact.

The bridge's S34 consumer (`exp/jatm_section5/run_development.py::_iter_nodes`) asks the cache for `partition("development", representation="CURRENT")`, while E1/E2/E3 call the concrete Development iterator directly. Therefore an isolated Q4 adapter must provide an explicit Q4 bridge/cache view for the same typed episodes, PRE states, and M1 examples; preserve true split/date/access provenance as `test`; and dispatch the existing S34 evaluators through a versioned Q4 runner. Do not mutate the M1 cache guard or label Q4 rows as Development in persisted manifests.

### 4. S34 runners and receipts encode Development assumptions

`exp/jatm_s34/e1_information_gain.py::run_bounded_annual` and `e2_e3_exact.py::run_bounded_annual` have no bridge-factory parameter; both call their imported `iter_annual_bridges` directly, use Development-named checkpoints/schema/status, and write `final_test_access_count: 0`. E4's `consequence_stability_battery.py` explicitly has an Aug–Sep hard scope and evaluates `selected_by_year[year]["development"]`; its wrappers and aggregators assume Development outputs.

The Q4 runner needs a separately namespaced manifest/checkpoint format with `split=test`, positive source-read/access accounting, and Q4 status labels. It may reuse the same inner scoring, support, objective, tie, and inference functions. Any runner substitution must be explicit and hash-bound; avoid an implicit module-global monkeypatch that could leak across jobs.

### 5. Hash ranking was corrected in Protocol V2

The exact frozen rank is `SHA256((FIXED_M5_SEED + "||" + episode_id).encode("utf-8"))`, from `data2/scripts/cohort_size_study.py::hash_rank`. Preserve the literal delimiter and deterministic episode-ID tie-break. The selected 4,096 IDs must be persisted before PRE state or model evaluation.

## Execution consequences

- These are adapter/runner/provenance gaps; none by itself invalidates the saved Development results or changes the approved Q4 estimand.
- No Q4 computation should start until the items above have a concrete isolated implementation and input/code hashes are preflighted.
- Three concurrent year workers remain the target, conditional on cloud resources. Each worker needs a separate scratch/output root. Do not let E1, E2/E3, and E4 concurrently rebuild the same mutable PRE states for one year; materialize the fixed cohort once per year and have evaluation stages consume its immutable checkpoint.
- Cloud server details are still needed before deployment, resource measurement, and actual computation.

## Scope of this audit

Static source review only. No tests were run, no code files in the frozen producer were modified, and no Q4 data contents were read.
