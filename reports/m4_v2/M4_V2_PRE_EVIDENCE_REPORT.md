# M4 V2 PRE Evidence Report

Date: 2026-08-07

## Version Boundary

The M4 repository still contains PRE Core V2 R2:

```text
contract = AIR_CHAIN_CORE_V2
schema = air-chain-core-2.0
revision = AIR_CHAIN_CORE_V2_R2
```

M4 recognizes this only as `PRE_R2_COMPATIBILITY_ONLY`. Formal evidence
requires schema `air-chain-core-2.1`, revision `AIR_CHAIN_CORE_V2_R3`, input-rule
registry hash, formula-registry hash, and explicit lineage.

The separate local PRE worktree implements R3, but no Fast bundle was rebuilt
and the implementation was not copied into the M4 repository. This distinction
is preserved rather than relabeling R2 as R3.

## Evidence Rules

```text
DERIVED -> may support FORMAL
EMPIRICAL_REFERENCE -> FORMAL or CONDITIONAL with proxy disclosure
EXTERNAL_STANDARD -> requires assumption match
SCENARIO_PARAMETER -> never FORMAL
UNSUPPORTED -> SCENARIO or EXCLUDED when critical
```

Explicit negative assertions cover flow pressure to resource availability,
ground occupancy to handler availability, future observed chains, proxy to
observed truth, missing to zero, unsupported taxi references, and unsupported
rebooking supply.
