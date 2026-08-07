# M3 V2 Contract Report

Date: 2026-08-06

## Identity

```text
contract_identity = M3_RESPONSE_V4_ATOMIC_SUBITEM
action_library = M3_ATOMIC_ACTION_LIBRARY_V1
response_contract = M3_SUBITEM_RESPONSE_V1
parameter_freeze = NOT_YET_DONE
scientific_approved = false
publication_allowed = false
```

The active action identity is `(action_library_version, action_id)`. V4 must be selected explicitly; V3 remains a historical audit contract and cannot enter the active formal path.

## Atomic Catalog

The V4 catalog contains exactly 21 actions:

```text
A00 A11 A12 A13 A21 A22 A23 A31 A33
A41 A42 A43 A51 A52 A53
A61 A62 A63 A64 A71 A72
```

`A51`, `A52`, and `A53` are new atomic aircraft recovery identities under the V4 library. They are `PARTIAL_SUPPORTED` and `NOT_CONFIGURED`. `A54` and `A55` remain forbidden. Names containing `PLUS`, `WITH`, `PACKAGE`, `INTEGRATED`, `BALANCED`, or `AGGRESSIVE` are rejected.

## Subitem Response

The response targets are:

```text
F_TURN F_WAIT F_PROPAGATION
P_DELAY P_CONNECTION P_CARE
R_GROUND R_TAXI R_SCARCITY
```

Each footprint cell is `NONE`, `PRIMARY`, or `SECONDARY`. `NONE` produces exact zero recovery. Each nonzero response uses one shared action intensity per response draw:

```text
success_draw ~ Bernoulli(1 - failure_probability)
response_intensity ~ Beta(response_mean * concentration,
                          (1 - response_mean) * concentration)
subitem_recovery_rate = success_draw * footprint_weight * response_intensity
```

The implementation cost remains F/P/R channel-level. No exposure-scaled cost interface is active in V4.

## Artifact

The artifact contains action catalog, footprint table, response draw IDs, success draws, response intensities, subitem recovery rates, implementation costs, version metadata, compatibility status, and reproducibility hashes. M3 does not consume episode IDs, M1 predictions, M2 loss values, M4 rankings, or M1/M2 sample IDs.

## M2 Compatibility

Required identities are:

```text
EPISODE_PRE_ACTION_LOSS_RECONSTRUCTION_V2
M2_NINE_SUBITEM_V1
CU_V2
REQUIRES_DEVELOPMENT_FREEZE
```

M2 contract, subitem contract, CU, and valuation mismatches fail with `M3_M2_CONTRACT_MISMATCH`; there is no silent fallback.

## Runtime Gate

The pipeline loads and validates the V4 contract before checking readiness. The current ordered boundary is:

```text
M3 contract load
M3-to-M2 compatibility
M3 parameter freeze
M3 formal library generation
M4 contract
```

The current formal stop is `M3_PARAMETER_NOT_FROZEN`.
