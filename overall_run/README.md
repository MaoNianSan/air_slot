# overall_run

`overall_run` contains the retained M1-M4 mathematical pipeline. Its current
entry point is intentionally blocked with `PRE_CONTRACT_MISMATCH` because the
M1 Adapter for `AIR_CHAIN_CORE_V2_R2` has not been implemented.

Do not point this module at historical PRE output and do not synthesize an
adapter-shaped compatibility bundle. Migration must define availability-safe
`query_time` inputs from V2 events, chains, source-global Observations,
Membership, and train-only references before execution is re-enabled.

The block changes only integration availability; it does not claim that the
M1-M4 algorithms have been migrated or scientifically revalidated.
