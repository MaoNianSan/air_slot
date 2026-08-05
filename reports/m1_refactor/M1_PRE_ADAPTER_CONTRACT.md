# M1 PRE Adapter Contract

## Identity

M1 imports PRE identity from `pre.src.core.contracts` and requires:

- `AIR_CHAIN_CORE_V2`
- `air-chain-core-2.0`
- `AIR_CHAIN_CORE_V2_R2`

The only accepted location is
`pre/output_core/<mode>/AIR_CHAIN_CORE_V2/`. Raw, PRE cache, staging,
historical output roots, path escapes, missing artifacts, and hash mismatches
fail closed.

## Published artifacts

The adapter validates and loads `pre_manifest`, `episodes`, `events`,
partitioned `observations`, partitioned `observation_membership`,
`calibration`, `evidence_audit`, and `column_registry`. Direct files, both
partition manifests, and every non-empty partition are SHA-256 verified.

## Availability

Observations are selected through Membership and the sole time rule is
`availability_time <= query_time`. Event time is retained as evidence but is
not used as an availability substitute. A counterexample with an early event
time and future availability time is covered by tests.

## Model-owned transformation

The M1 adapter, not PRE, owns the five-minute timeline, latest legal evidence,
feature masks, sequence construction, flight-chain stage, target contracts,
and reset signal. Only registry fields with `model_input_allowed=true` are
eligible. Missing inputs use a numeric placeholder together with an explicit
false mask and missing-evidence status.
