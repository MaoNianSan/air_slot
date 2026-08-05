# Run Profiles

## PRE profiles

The current PRE CLI accepts exactly four modes:

| Mode | Purpose |
|---|---|
| `fast` | Bounded engineering build and validation |
| `middle` | Frozen intermediate data selection |
| `full` | Complete-month or otherwise qualified full data |
| `diagnostic` | Explicit debugging profile |

The profile-specific overrides live in `pre/config/default.yaml`. Separate PRE
mode files and aliases are not part of the current contract.

## Downstream profiles

`overall_run`, `overall_adv`, and `part_adv` retain historical profile resolver
code because their mathematical implementations have not yet been migrated.
Their entry points are unconditionally blocked with `PRE_CONTRACT_MISMATCH`
until an M1 Adapter consumes `AIR_CHAIN_CORE_V2_R2`.

Those resolver tokens are not PRE modes, are not evidence of a second PRE
contract, and cannot currently start M1-M4 computation.

## Current execution order

1. Verify PRE compile/tests and the single-version gate.
2. Run and finalize a V2 Fast bundle when explicitly authorized.
3. Implement and validate the M1 Adapter.
4. Re-enable downstream profiles only after Adapter lineage is published.

No downstream profile may fall back to historical PRE output.
