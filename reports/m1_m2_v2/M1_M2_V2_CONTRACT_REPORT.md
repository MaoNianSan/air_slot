# M1-M2 V2 Contract Report

Date: 2026-08-06

## M1ScenarioBundle

Metadata includes episode, snapshot, query/cutoff, flight-chain stage, PRE
bundle identity, M1 contract, model, and temperature versions.

Operational references include successor SOBT, turnaround floor, taxi
reference, and observed predecessor in-block/successor off-block/takeoff
values with support and provenance.

Sampling metadata includes sample count, sampling version, base seed,
dependence mode, bin representative mode, overflow mode, tail artifact
versions, tail resolution status, and unresolved targets.

Each joint sample includes:

    sample_id
    r_ib_minutes
    r_ob_minutes
    earliest_offblock_time
    T_predecessor_inblock
    AOBT_successor
    ATOT_successor
    taxi_time
    offblock_delay
    extra_taxi_delay
    total_takeoff_delay
    overflow_flags
    evidence_status
    fallback_status

## M2InputBundle

    metadata
    joint_scenarios
    flight_context
    passenger_context
    resource_context
    subitem_activation
    valuation_context
    audit_context
    input_status

Input status values:

    VALID
    PARTIAL
    PROXY_SUPPORTED
    ABSTAIN

Subitem activation values:

    ACTIVE
    PROXY_ACTIVE
    UNSUPPORTED
    DISABLED_BY_CONFIG

## M2 Sample Output

Identity/audit fields include episode_id, snapshot_id, sample_id,
sample_weight, m2_input_status, tail_resolution_status, evidence_status,
proxy_status, audit_status, and overflow_present.

Event fields:

    turn_deficit_minutes
    turn_deficit_semantics
    extra_offblock_wait_minutes
    extra_taxi_minutes
    takeoff_delay_minutes

Quantity/CU fields cover TURN, WAIT, PROPAGATION, DELAY, CONNECTION, CARE,
GROUND, TAXI, and SCARCITY.

Channel/total fields:

    flight_constructed_units
    passenger_constructed_units
    resource_constructed_units
    total_constructed_units
    flight_loss_rmb
    passenger_loss_rmb
    resource_loss_rmb
    total_pre_action_loss_rmb

## M2 Episode Summary

Both constructed-unit and RMB summaries contain mean, median, q90, q95, and
cvar90. The summary also contains channel/subitem contributions, dominant
channel/subitem, unsupported and proxy-active subitems, overflow probability,
and tail resolution status.

## Versions

    M1_CONTRACT_ID=M1_CHAIN_DYNAMIC_DISTRIBUTION_V1
    M1_FEATURE_SCHEMA=M1_FEATURE_SCHEMA_V1
    M1_SAMPLING_VERSION=M1_SAMPLING_V2
    M2_CONTRACT_VERSION=EPISODE_PRE_ACTION_LOSS_RECONSTRUCTION_V2
    M2_PRIMARY_MODE=DIRECT_STRUCTURAL_COMPACT
    CONSTRUCTED_UNIT_VERSION=CU_V2
    CURRENCY_MAPPING_VERSION=IDENTITY_V1

## Pending Downstream Interface

M3 must migrate from old channel/scalar inputs to M2 V2 sample-level loss and
contribution fields. M4 must then migrate action-after risk and ranking.

    M3_STATUS=M3_CONTRACT_MISMATCH
    M4_STATUS=MIGRATION_REQUIRED
