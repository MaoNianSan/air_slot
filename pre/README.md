# Air Slot PRE

## 1. Role

`pre/` is the only layer that reads the immutable `data/` tree. It converts raw
source records into event, chain, source-global observation, Membership,
reference, registry, and manifest artifacts. Downstream modules never read raw
data or PRE staging directly.

## 2. Current contract

There is one authoritative PRE identity:

```text
contract_id=AIR_CHAIN_CORE_V2
schema_version=air-chain-core-2.0
research_code_revision=AIR_CHAIN_CORE_V2_R2
```

The constants in `src/core/contracts.py` are the single code authority. The
machine-readable schema is `config/schema/core_tables.yaml`.

## 3. CLI

Run from the repository root with Python 3.11:

```powershell
D:/Python311/python.exe pre/main.py build --mode fast
D:/Python311/python.exe pre/main.py validate --mode fast
D:/Python311/python.exe pre/main.py readiness --mode fast
D:/Python311/python.exe pre/main.py report --mode fast
D:/Python311/python.exe pre/main.py inspect-config --mode fast
```

Supported modes are `fast`, `middle`, `full`, and `diagnostic`. The command set
has no compatibility aliases. This refactor does not authorize or start a Fast
build.

## 4. Inputs

- `../data/raw/`: immutable raw sources.
- `../data/manifests/`: frozen source-selection evidence when required.
- `config/sources.yaml`: source discovery and schema declarations.
- `config/default.yaml`: shared defaults and mode overrides.
- `config/predecessor_matching.yaml`: current chain construction rules.

PRE must not modify raw data. `cache/state_extract_v2/` is reusable local
compute state and is preserved unless cache rebuilding is explicitly requested.

## 5. Outputs

The formal artifacts are:

```text
episodes
events
observations
observation_membership
calibration
evidence_audit
column_registry
pre_manifest
```

Published bundles live under
`output_core/<mode>/AIR_CHAIN_CORE_V2/`. A build first writes a compatible
staging directory and publishes only after validation succeeds.

## 6. Event and chain boundary

Events retain source field, record, file, hash, event time, availability time,
construction method, confidence, and support level. OpenSky `firstseen` and
`lastseen` values are supported proxies, not official operational milestones.

Chains preserve ambiguity and expose separate eligibility fields:

```text
core_eligible
engineering_eligible
scientific_chain_eligible
```

The observed-chain proxy is not an official aircraft rotation. Scientific
eligibility therefore remains stricter than engineering eligibility.

## 7. Observations

Observations are source-global and split-neutral. Each native source record is
represented once for the union of relevant request intervals. Chain, request,
interval, and split fields are prohibited from the Observation rows.

Observation data is partitioned by:

```text
source=<source>/observation_date=<YYYY-MM-DD>
```

Native timestamps and admissible raw columns are retained. PRE does not create
a five-minute grid, recurrent-model masks, or model predictions.

## 8. Membership

`observation_membership` is a separate many-to-many interval relation between
source-global observations and chain requests. It uses the same source/date
partitioning as Observations and carries the chain, request interval, split,
role, availability support, and membership reason.

One observation may belong to multiple overlapping requests. Empty legal
partitions use `PASS_EMPTY` and have no Parquet file.

## 9. References

References are fit from training Membership joined to source-global
Observations. Observation IDs are deduplicated before sufficient statistics are
computed. Every reference records its fit period, `fit_split=train`, support,
fallback level, and source hash.

## 10. Resume

Resume requires an exact scientific/data identity: contract, schema, research
revision, frozen configuration, source and request identities, episode
intervals, cache key, and expected partitions. Worker count, progress display,
temporary paths, and process identity are operational metadata and do not
change the frozen configuration hash.

Valid `PASS` and `PASS_EMPTY` partitions are reused. Missing, in-progress,
failed, hash-mismatched, schema-mismatched, or row-count-mismatched partitions
are rebuilt.

## 11. Validation

The independent validator loads the manifest, enumerates the bundle, verifies
identity and file hashes, checks table schemas and keys, validates Observation
and Membership manifests, recomputes critical statistics, checks train-only
references and future-information rules, and writes a recomputed report. It
does not trust a stored validation status by itself.

## 12. Readiness

Engineering readiness and scientific readiness are separate. A structurally
valid bundle can still be scientifically unavailable when required event or
label support is absent. Readiness commands inspect an existing published
bundle and do not rebuild data.

## 13. Scientific limitations

- The observed-chain proxy is not an official rotation record.
- Local AIBT, AOBT, and SOBT evidence is insufficient for official-event use.
- Current `y_ob`, `y_tx`, and `y_to` outcomes may be empty.
- Engineering readiness does not imply scientific readiness.
- Unsupported evidence remains explicit and is never silently zero-filled.

## 14. M1 Adapter boundary

PRE does not create recurrent-model tensors, M1 predictions, action effects, or
rankings. Instantaneous model updates belong in the future M1 Adapter, which
must select the latest evidence available at each `query_time`.

The existing `overall_run`, `overall_adv`, and `part_adv` entry points are
blocked with `PRE_CONTRACT_MISMATCH` until that Adapter is implemented. No
fallback or compatibility bundle is generated.

## 15. Published evidence

Implementation and pre-run validation reports are under
`reports/published/core_v2/`. They are not a formal Fast data bundle. Runtime
output, cache, staging, raw data, and Parquet files remain local and excluded
from version control.
