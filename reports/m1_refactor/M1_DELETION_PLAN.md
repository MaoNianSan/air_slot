# M1 Deletion Plan

## DELETE_WITH_OLD_M1

Delete the flat M1 implementation, all dedicated helpers, all
`m1_lineage_*.py` modules, the D6 audit entry point, and the three old-semantic
tests listed in `M1_PRECHANGE_INVENTORY.md`.

Delete retired M1 configuration fields and model-search definitions from
`overall_run/config/*.yaml`. Configuration validation must fail with
`RETIRED_M1_CONFIG_KEY` when an override introduces a retired key.

## REPLACE_WITH_NEW_M1

- Replace `overall_run/src/m1.py` with the `overall_run/src/m1/` package.
- Replace old pipeline imports with the stable package API and readiness gate.
- Replace quantile-lineage metadata with M1 contract/model/temperature/PRE
  identity and engineering/scientific status.
- Replace `require_m1_adapter()` with `require_m1_ready(...)`.
- Replace old metric imports with the new M1 evaluation modules.

## SHARED_WITH_M2_M4

Keep M2, M3, M4, ranking contracts, overall-adv, and part-adv mathematics.
Only their M1 input/readiness checks may change. A request for the retired
movement-sample schema must fail with `M2_CONTRACT_MISMATCH`.

## UNRELATED_FALSE_POSITIVE

Historical paper/audit text, generated code maps, user memory files, and old
experiment output may retain retired vocabulary as historical evidence. They
must not be imported or accepted as current runtime/configuration evidence.

## Deletion safety

- Do not delete raw data, PRE cache, PRE published evidence, or PRE staging.
- Do not delete user experiment output without separate authorization.
- Do not create a legacy, compatibility, fallback, or converted-output layer.
- Do not modify PRE Core V2 mathematical ownership to satisfy M1.

## Phase 1 acceptance

- `OLD_M1_SOURCE_REMOVED=YES`
- `OLD_M1_CONFIG_REMOVED=YES`
- `OLD_M1_TESTS_REMOVED=YES`
- `COMPATIBILITY_LAYER_CREATED=NO`
