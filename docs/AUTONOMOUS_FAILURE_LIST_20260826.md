# AIR_SLOT AUTONOMOUS FAILURE LIST — 2026-08-26

- chain: `AIR_SLOT_AUTONOMOUS_OVERNIGHT_CHAIN_20260826` (incl. V1 `AIR_SLOT_EXP_DEV_GAP_CLOSURE_20260826`, V2 merge, T-cal, T-tex, automatic Final Test).
- policy: HP3=B with mandatory recording; every failure/fix gets an entry with root cause, page-level literature citation (or manuscript intent), `AUTO_ASSUMED_FIX` label, and a decision-log pointer.

## Entries

- `NONE` — no failures were recorded during the dev chain (T0–T5, T-cal, T-tex) or the automatic Final Test rematerialization. All 11 Final Test stages reached `MATERIALIZED`; the figure/table regeneration completed; the dev test suite passed (106 passed); no `AUTO_ASSUMED_FIX` was required and none was created.
- Ledger closes with `FAILURES = 0 resolved / 0 quarantined`.

## Notes for the morning report

- Exp2B family-transitions file is intentionally empty: `TOP1_DIFFERENCE_RATE = 0.0` (0/1,765 common-scope nodes) for both r3 and r1, so there are no transitions to enumerate. Recorded as a result, not a failure.
- `STATE_AWARE_H32` parity vs stored dev metrics shows expected calibration drift (max abs diff 0.1029), documented in the Exp4 Final Test manifest `parity_vs_existing_metrics` block; expected Final Test semantics, not a failure.
