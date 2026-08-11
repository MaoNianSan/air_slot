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

`overall_run`, `overall_adv`, and `part_adv` retain profile resolver code for
CLI compatibility. M1, the M1-to-M2 V2 boundary, M3 V4, and M4 V2 are
implemented and covered by synthetic tests, but formal M1 training has not run.
Their entry points remain blocked at the downstream migration gate with
`M2_CONTRACT_MISMATCH` until formal M1 publishes a bundle and the gate is
explicitly satisfied.

Those resolver tokens are not PRE modes, are not evidence of a second PRE
contract, and cannot currently start formal M1-M4 computation.

## Current execution order

1. Verify PRE compile/tests and the single-version gate.
2. Run and finalize a V2 Fast bundle when explicitly authorized (the Fast V2
   bundle already exists and passes validation).
3. Run formal M1 training, calibration, and resampling.
4. Freeze M2 valuation and M3 parameters, then generate the formal M3 library.
5. Re-enable downstream profiles only after Adapter lineage is published.

No downstream profile may fall back to historical PRE output.
