# Exp2 Data2 Development Binding

Status: `DEVELOPMENT_COHORT_MATERIALIZED_M1_M2_BLOCKED`

The Exp2 primary dataset is `DATA2` / `data2_2019`. The frozen pilot cohort is
`artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json`:

- split: `DEVELOPMENT`, successor service date from `2019-08-01` through `2019-09-30`;
- selector: first five eligible episode IDs in stable identity order, before any outcome, risk, or variant comparison;
- cohort hash: `sha256:cc224488e1b6fecfd865dcc494b0004af9ca752dc609eb901d46ad88b82edb63`;
- artifact hash: `sha256:66d1a0bfcea84164713e1db476f98ccf47fe19c494509495080f3c559c10b43e`;
- retained coverage: 5 episodes and 69 five-minute decision nodes;
- `FINAL_TEST_ACCESS_COUNT=0`, `PAPER_FULL_RUN=false`.

The materializer accepts exactly the BTS `month=08` and `month=09` sources,
requires successor-date ownership and full PRE episode containment, then
rebuilds typed records only for selected episodes. It does not read October,
November, or December.

| Legacy/Data experience | Current reusable implementation | Current V2 owner | Reuse decision | Reason |
| --- | --- | --- | --- | --- |
| BTS 2019 ingestion and normalization | `model.PRE.streaming.data2.iter_lightweight_flights` | PRE | REUSE_AS_IS | Existing projected streaming parser and canonical identifiers. |
| Airport/timezone normalization | `load_timezones`, PRE canonical timezone utilities | PRE | REUSE_AS_IS | Required by the current Data2 adapter. |
| Successor-flight episode construction | `build_data2_episode_records` | PRE | REUSE_AS_IS | Preserves approved actual-gate adjacency and episode identity. |
| Five-minute decision nodes | `build_rolling_decision_nodes` | PRE | REUSE_AS_IS | Enforces the frozen five-minute grid. |
| Split containment | `episode_containment_from_rows` | PRE | REUSE_AS_IS | Requires complete episode support in one temporal split. |
| Deterministic cohort engine | PRE streaming/staging patterns plus `select_deterministic_pilot` | Exp2 | ADAPT_TO_V2 | Uses stable first-N identity selection, not outcome- or score-selected sampling. |
| Selected typed-record reload | `load_selected_typed_records` | PRE | REUSE_AS_IS | Avoids broad typed reconstruction after selection. |
| Train-derived reference machinery | `model.PRE.reference.*` | PRE/M2 | REUSE_ENGINE_ONLY | Current seven-component M2 requires a frozen V2 M1 input before use. |
| Cache/resume contracts | `model.PRE.cache.*` | PRE | REUSE_ENGINE_ONLY | No compatible content-addressed Exp2 V2 cohort cache existed. |
| Data2 factual replay | `model.PRE.factual.replay` | PRE | DO_NOT_REUSE | Factual availability remains a human decision; cohort construction does not publish factual evidence. |
| Legacy M1 reference thresholds and V1 scenarios | historical `M1_SIGNED_*` artifacts | M1 historical | DO_NOT_REUSE | V1 warning/scenario semantics are not the current M1 V2 contract. |
| Warning metrics and operating logic | legacy warning code | Exp1 historical | DO_NOT_REUSE | Threshold, FPR/recall, and sustained-warning semantics are outside Exp2. |
