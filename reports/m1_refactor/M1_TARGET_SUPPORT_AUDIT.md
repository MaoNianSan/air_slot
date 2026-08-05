# M1 Target Support Audit

## Engineering fixture

The synthetic published Core V2 fixture supports all three base targets and
passes the full adapter-to-joint-sample path:

| Target | Synthetic status | Semantics |
|---|---|---|
| `R_IB` | `OFFICIAL_OPERATIONAL` | Remaining time to predecessor in-block |
| `R_OB` | `OFFICIAL_OPERATIONAL` | Extra wait after earliest feasible off-block |
| `T_TX` | `OFFICIAL_OPERATIONAL` | Successor actual taxi time |

The mapping preserves PRE event support level, chain support level,
reconstruction method, confidence, availability time, event time, and source
hash. Missing schedule or operational evidence deactivates a target with
`UNSUPPORTED`; it is not filled with zero or replaced by a retired movement
label.

## Actual Fast bundle

`pre/output_core/fast/AIR_CHAIN_CORE_V2/` does not exist in the writable
repository as of August 5, 2026. Therefore actual Fast target support was not
audited and no M1 training was started.

- `M1_TARGET_SUPPORT_STATUS=ACTUAL_NOT_AUDITED`
- `M1_TRAINING_STATUS=NOT_RUN`
- `M1_SCIENTIFIC_STATUS=NOT_READY`
