# V5 Split Containment Closure

Date: `2026-08-17`

## Engineering result

- `V5_SPLIT_CONTAINMENT = PASS`
- `PRE_OWNERSHIP_GATE = PASS`
- `STATIC_VOLUME_GATE = PASS`
- `FINAL_TEST_ACCESS_COUNT = 0`
- Containment is owned by `model/PRE/**` and uses O(1) closed-interval checks.
- The five-minute grid is not enumerated for containment. Endpoint membership
  proves every canonical node is inside the same contiguous V5 split.
- Monthly carry remains enabled. The audit observed `326` allowed August to
  September cross-month episodes.

## Boundary audit

The authoritative audit is
`artifacts/diagnostics/v5_development_freeze/PRE_SPLIT_CONTAINMENT_AUDIT.json`.
It read only June through September 2019 and did not select October through
December raw data.

| Historical successor-assigned pool | Cross-split episodes | Removed nodes |
| --- | ---: | ---: |
| Train | 3,291 | 52,085 |
| Calibration | 4,382 | 108,335 |
| Development | 4,378 | 113,444 |

Transition counts are `TRAIN_TO_CALIBRATION = 4324`,
`CALIBRATION_TO_DEVELOPMENT = 4440`, and
`DEVELOPMENT_TO_FINAL_TEST = 3287`. Transition counts are not pool counts:
the pool column follows the historical successor-date assignment, while a
single containment failure can expose a different adjacent boundary.

## Development delta

The authoritative corrected count is
`artifacts/diagnostics/v5_development_freeze/PRE_DEVELOPMENT_STREAM_MANIFEST_V2.json`.

- `OLD_PRE_ELIGIBLE_EPISODES = 951359`
- `NEW_PRE_ELIGIBLE_EPISODES = 946981`
- `OLD_PRE_ELIGIBLE_NODES = 13721540`
- `NEW_PRE_ELIGIBLE_NODES = 13608096`
- `CROSS_SPLIT_REMOVED_EPISODES = 4378`
- `CROSS_SPLIT_REMOVED_NODES = 113444`
- `ABSTAIN_EPISODES = 0`
- `INSUFFICIENT_HISTORY_EPISODES = 731`

Delta accounting is exact because episode identity, the canonical node grid,
PRE support semantics, and monthly carry are unchanged. The only publication
change is exclusion with reason `CROSS_V5_SPLIT_EXCLUDED`.

## Historical H/W impact

`H_SELECTION_EPISODES_TOTAL = 320` and `W_SELECTION_EPISODES_TOTAL = 320`.
Both used the same stored base cache. Three selected episodes fail the new
containment invariant:

| Episode ID | Historical split | Transition | Nodes | Split evaluation weight |
| --- | --- | --- | ---: | ---: |
| `sha256:3121e48085ffada2bb136fdf3a619683c2ce6813b09e8bdbb8949ac3c4dc7e14` | train | TRAIN_TO_CALIBRATION | 8 | 0.0078125 |
| `sha256:8bb9e56be0e1e4f7e53689026f314757349786f94b0125ff974e3ef40c4a9424` | calibration | TRAIN_TO_CALIBRATION | 95 | 0.015625 |
| `sha256:669e578f23cbbf94ae421ae886944cd53138c69fd3c21d389978a8132038d3ea` | development | DEVELOPMENT_TO_FINAL_TEST | 16 | 0.0078125 |

Therefore this is `CASE B`:

- `H_SELECTION_CROSS_SPLIT_EPISODES = 3`
- `W_SELECTION_CROSS_SPLIT_EPISODES = 3`
- `H_W_FREEZE_STATUS = REQUIRES_RECONSIDERATION`
- `H_STAR_CURRENT = 32`
- `W_STAR_CURRENT = 30`
- `H_W_RERUN_THIS_ROUND = FALSE`

The evidence files `m1_hstar_evidence.json` and `m1_wstar_evidence.json` were
not modified.

## Next scientific round

`SIGNED_OB_TARGET_REQUIRED = TRUE` and Option A changes the M1 target/joint
objective. The split correction and signed-target change must therefore be
combined into one new Development H/W freeze, not two sequential reruns.

See
`artifacts/diagnostics/v5_development_freeze/D3_OPTION_A_IMPACT_MANIFEST.json`.

- `D_TO_TAIL_IDENTIFIABILITY = NOT_IDENTIFIED_FROM_CURRENT_M1_OUTPUTS`
- `OPTION_A_REQUIRES_NEW_H_W_FREEZE = TRUE`
- `CURRENT_H_W_ARTIFACTS_REUSABLE = NO_FOR_NEW_MODEL_SELECTION`
- `NEXT = READY_FOR_AGGRESSIVE_M1_SIGNED_TARGET_REFREEZE`
