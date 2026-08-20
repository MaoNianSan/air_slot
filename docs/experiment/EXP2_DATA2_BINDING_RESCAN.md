# Exp2 Data2 Binding Rescan

Status: `PREPARATION_ONLY_NO_DATA_READ`

## Data2 current status

`data2/DATA_USAGE.md` identifies source instance `data2_2019` as the primary experimental dataset.  The current scientific manifest binds logical Exp2 dataset `DATA2` to that source instance, identifies the available `data2/manifests/data2_bts_2019_sha256.csv` source manifest, and retains `DATA2_VERSION_PENDING`; local raw presence is not a frozen scientific version.

The repository has no `data/` directory and no lowercase `pre/` directory.  The relevant boundaries are `data2/` and `model/PRE/`.  This rescan did not open a Data2 raw table or modify data.

## Available source coverage and episodes

The Data2 raw source tree exposes 2019 BTS On-Time month directories `month=01` through `month=12`; `data2/manifests/data2_bts_2019_sha256.csv` is available as a source-file checksum manifest.  No content-addressed Exp2/Data2 episode registry or frozen episode-ID list is present under `data2/manifests/`.  Consequently, the set and count of eligible scientific episodes are `PENDING`, not inferred from source rows.

`Data2EpisodeSelector` accepts only a supplied frozen registry and caller-specified IDs.  A missing or unknown ID is blocked; it is never substituted with an available raw record.

## Schema compatibility

The registered `data2_2019` profile uses schema `1.0.0`, with `realized_events` designated `EVAL_OUTCOME` and `weather` designated `INFERENCE_EVIDENCE`.  PRE's `DecisionNodeRecord` requires `information_cutoff <= decision_time`; M1's history validator enforces the same causal boundary; M2's typed `M2ScenarioInput` preserves `episode_id`, `decision_node_id`, and `scenario_id` from M1.

The new compatibility checker validates the corresponding binding envelope: legal record availability is at or before the cutoff, PRE/M1 decision timestamps agree, and M2 copies M1 scenario identity and lineage exactly.  It does not claim that concrete M1 or M2 scientific artifacts have been frozen.

## Missing scientific artifacts

- Frozen Data2 version and approved source-manifest hash.
- Frozen split, episode registry, pilot episode IDs, and their hash.
- M1 scenario artifact/checkpoint for that exact cohort.
- M2 seven-component consequence artifact for the same M1 lineage.
- Typed M3 comparison action/response bundle.
- Resolved M4 mapping and frozen residual-risk policy.

These missing items leave both pilot execution and scientific execution blocked.  The rescan is a binding audit only, not evidence or a scientific result.
