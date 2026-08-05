# M1 Implementation Status

Generated: 2026-08-05 (Asia/Hong_Kong)

## Completed

- Old flat M1, dedicated helpers, lineage implementation, audit entry point,
  and old-semantic tests were removed.
- The only M1 implementation is `overall_run/src/m1/`.
- PRE published-bundle validation, Membership availability join, timeline,
  feature masks, target support, stage transitions, and reset rules are
  implemented.
- The only model is a one-layer unidirectional GRU with hidden size 8; hidden
  size 16 is accepted only as capacity sensitivity.
- Only `R_IB`, `R_OB`, and `T_TX` distribution heads exist.
- Five-minute bins, overflow, interval soft labels, episode-balanced cross
  entropy, per-target temperature scaling, fixed episode random numbers, joint
  samples, state idempotence, revision truncation, temporary prediction, and
  independent M1 evaluation are implemented.
- Joint samples satisfy `ATOT_successor = AOBT_successor + taxi_time`; total
  takeoff delay uses scheduled off-block plus reference taxi and is not forced
  to equal the sum of two positive-part delay components.
- Retired M1 configuration keys fail with `RETIRED_M1_CONFIG_KEY`.
- Downstream code is blocked with `M2_CONTRACT_MISMATCH`; no compatibility or
  old-output conversion layer exists.

## Status

- `M1_ENGINEERING_STATUS=PASS`
- `M1_PRE_ADAPTER_ENGINEERING_STATUS=PASS`
- `M1_MODEL_UNIT_STATUS=PASS`
- `M1_PROBABILITY_CONTRACT_STATUS=PASS`
- `M1_EVALUATION_ENGINEERING_STATUS=PASS`
- `M1_SCIENTIFIC_STATUS=NOT_READY`
- `M1_M2_INTERFACE_STATUS=M2_CONTRACT_MISMATCH`

The scientific status is conservative because no published Fast Core V2
bundle is present for target-support audit, training, calibration, or test
evaluation.
