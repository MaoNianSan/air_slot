# PRE Core V2 Changeset

Date: 2026-08-05

## Identity and interface

- `pre/src/core/contracts.py` is the only code authority for contract, schema,
  and research revision constants.
- `pre/config/schema/core_tables.yaml` is the machine-readable table authority.
- `pre/main.py` exposes only `build`, `validate`, `readiness`, `report`, and
  `inspect-config` with `fast`, `middle`, `full`, and `diagnostic` modes.

## Data contract

- Observations are source-global and split-neutral.
- Membership is an independent many-to-many source/date partitioned dataset.
- `PASS_EMPTY` is fileless and valid only with the expected schema fingerprint.
- Episodes expose separate core, engineering, and scientific-chain eligibility.
- References are training-only and deduplicate source-global observations.
- The independent validator recomputes physical and logical bundle facts.

## Structure

- Observation, Membership, and validation aggregate modules were replaced by
  cohesive packages.
- `pipeline.py` is a 90-line public orchestrator; context, stages, and
  finalization are separate.
- The retired PRE implementation, predecessor Core facades, schemas,
  configurations, tests, and reports were deleted.
- State cache handling is V2-only and no longer consults retired PRE output.

## Downstream boundary

The M1-M4 mathematical code is retained, but all three downstream entry points
stop with `PRE_CONTRACT_MISMATCH` until an M1 Adapter is implemented. No
fallback, synthetic compatibility tables, or implied migration is present.

## Verification

- Compile: PASS.
- PRE tests: 71 passed.
- Synthetic Observation/Membership, `PASS_EMPTY`, Resume reuse, and independent
  bundle validation: PASS.
- Full Fast started: NO.
