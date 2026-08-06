# PRE Dataset Column Audit

Audit date: 2026-08-04 (Asia/Hong_Kong)

Actual local files and accepted fast Parquet schemas are authoritative. Raw large-source counts, examples, and unique counts are explicitly sampled; accepted Parquet nonmissing counts use full row-group metadata.

## Inventory

| table_or_source          |   column_count |
|:-------------------------|---------------:|
| calibration              |             86 |
| episodes                 |             68 |
| evidence_audit           |             32 |
| raw:aircraft             |             16 |
| raw:eurostat_flights     |              6 |
| raw:eurostat_passengers  |              8 |
| raw:flightlist           |             16 |
| raw:metar                |             20 |
| raw:ourairports_airports |             18 |
| raw:ourairports_runways  |             20 |
| raw:state_vectors        |             16 |
| rules                    |             60 |
| snapshots                |            163 |

## Unsupported Operational Semantics

No local source contains official AOBT, AIBT, ATOT, ALDT, SOBT, rotation ID, cancellation, diversion, or aircraft-swap event fields. OpenSky `firstseen`/`lastseen` and trajectory states remain proxies/reconstruction inputs and must not be relabeled as official events.

## All-Missing Published Columns

| table_or_source   | actual_column                  |
|:------------------|:-------------------------------|
| episodes          | planned_departure_time         |
| episodes          | planned_arrival_time           |
| episodes          | predecessor_registration_match |
| snapshots         | state_imputation_gap_minutes   |
| snapshots         | ceiling                        |
| snapshots         | predecessor_registration_match |
| calibration       | capacity_required              |
| calibration       | window_type                    |

## Gate

`COLUMN_AUDIT_COMPLETE=YES`

`UNRESOLVED_REQUIRED_COLUMNS=0`

`SILENT_COLUMN_DROP=NO`

`LOCAL_SCHEMA_IS_SOURCE_OF_TRUTH=YES`

Unsupported operational semantics are nullable contract facts, not missing mandatory source columns for the build.
