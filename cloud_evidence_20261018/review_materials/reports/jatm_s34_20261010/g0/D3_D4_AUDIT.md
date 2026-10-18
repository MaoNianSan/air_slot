# D3/D4 decision audit — 2026-10-11

Source HEAD: `2ea652e`

## D3 — Delay+Exposure

- Status: `PASS_FORMULA_FROZEN`
- Primary: `P^D * expected_passengers_per_flight` (expected passenger-time exposure proxy)
- Companion: `P^D * expected_downstream_exposure` (downstream exposure proxy)
- Excluded: three-way product
- References must be train-frozen, decision-time available, and pass the existing common-support gate.
- Implementation: `exp/jatm_s34/delay_exposure.py`

## D4 — FIXED_COMMON

- Requested source: 2017 H1 Train frozen seven-component CU scale.
- Status: `BLOCKED_SOURCE_NOT_FOUND_2017_H1`.
- Missing candidate: `D:\research\air_slot\code\explore\artifacts\models\pre\PRE_MULTIYEAR_V1\2017\M2_REFERENCES\M2_SEVEN_COMPONENT_TRAIN_SCALES.json`.
- 2017 H1 turnaround and taxi references exist, but a seven-component scale artifact does not.
- 2019 H1 scale exists at `D:\research\air_slot\code\explore\artifacts\models\pre\PRE_MULTIYEAR_V1\2019\M2_REFERENCES\M2_SEVEN_COMPONENT_TRAIN_SCALES.json` with hash `sha256:322d9805a9e28aa121d30555dd5cf720c4c75e95075297b6122d9d952eb76ef1`, but it is not substituted.
- No new pooled scale or result-driven source selection was performed.
