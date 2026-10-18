# File Decomposition Report

This report records responsibility decisions, not only line-count changes. The
Phase 0 `CODE_STRUCTURE_AUDIT.md` remains the before snapshot.

## P0 decompositions

| Before path | Before LOC | After modules | Responsibility assignment | Public API | Evidence |
| --- | ---: | --- | --- | --- | --- |
| `model/PRE/transformation.py` | 1003 | facade 29; `transform/contracts.py` 162; `transform/engine.py` 175; `transform/rules.py` 687 | typed transformation objects; execution orchestration; declarative frozen rule registry | retained by facade | PRE transformation focused tests (78) plus cross-module behavioral equivalence |
| `model/M4/decision.py` | 346 | facade 62; `eligibility.py` 28; `post_action.py` 118; `ranking.py` 46; `results.py` 38 | request validation; response/post-action; ranking; typed result assembly | retained by facade | M4 tests and behavioral equivalence |
| `validation/data2_m1_fast_2019_full_year_wx_v2.py` | 796 | entry 442; shared `support/data2_m1.py` 313; `scenarios/data2_m1_full_year.py` 130 | CLI/run orchestration; loaders/streaming/artifact helpers; cohort/scenario construction | entry path retained | validation import/static checks; full-year not executed |
| `validation/data2_m1_fast_january_v1.py` | 588 | entry 400; shared support/scenario helpers | same as above | retained | validation import/static checks |
| `validation/data2_m1_fast_january_wx_v1.py` | 621 | entry 368; shared support/scenario helpers | same as above | retained | validation import/static checks |
| `validation/data2_m1_fast_january_wx_v2.py` | 643 | entry 390; shared support/scenario helpers | same as above | retained | validation import/static checks |

## P1 decomposition and KEEP decisions

| Before path | LOC | Decision | Reason |
| --- | ---: | --- | --- |
| `model/PRE/canonical/normalization.py` | 563 | SPLIT | weather, flight/outcome, and reference/Eurostat source families had independent parsing contracts; facade retained at 41 LOC. |
| `model/PRE/canonical/normalization_common.py` | new 48 | KEEP | shared missing/number/time/identity/provenance primitives only. |
| `model/PRE/canonical/normalization_weather.py` | new 269 | KEEP | NOAA/Metar weather grammar and unit/ceiling semantics are one source-family boundary. |
| `model/PRE/canonical/normalization_flights.py` | new 277 | KEEP | flight schedule/outcome/trajectory event canonicalization shares event-time and provenance semantics. |
| `model/PRE/canonical/normalization_references.py` | new 292 | KEEP | airport/timezone/aggregate/Eurostat reference records share frozen-reference contracts. |
| `model/PRE/transform/rules.py` | 687 | KEEP | declarative frozen rule registry; splitting individual rule families would create a registry re-export maze without removing scientific coupling. |
| `model/PRE/mapping.py` | 256 | KEEP | registry lookup plus typed PRE publication is one mapper boundary. |
| `model/PRE/pipeline.py` | 91 | KEEP | thin production orchestration. |
| `model/M1/data.py` | 229 | KEEP | feature schema, train-only normalization, and typed PRE sequence encoding form one data-preparation contract. |
| `model/M1/scenarios.py` | 86 | KEEP | aligned and ancestral sampling share deterministic lineage semantics. |
| `model/M2/drivers.py` | 249 | KEEP | one native-quantity mapping responsibility; no independent registry/valuation/aggregation implementation is embedded. |
| `model/M2/contracts.py` | 239 | KEEP | cohesive typed scientific contract family; mechanical splitting would reduce readability. |

## Long-file acceptance

Current physical Python files over 500 LOC: `model/PRE/transform/rules.py`
(687 LOC). Its `KEEP_REASON` is the declarative frozen registry described above.
The restored code-size audit reports 675 logical lines as `REVIEW`, with no
`REFACTOR_REQUIRED` file (`>800` logical lines). The current structure scanner
reports 0 required, 11 recommended modules under its responsibility heuristic;
these are non-blocking follow-up candidates.

## Behavior and scope

Public import paths were retained for PRE transformation, canonical normalization,
M4 decision, and module facades. The reconciliation test suite compares repeated
PRE state, M1 scenario identity/`D_TO`, M2 mapping, M3 candidate IDs, and M4
post-total/residual-risk/ranking outputs. Scientific changes are listed in the
conflict ledger; decomposition itself is engineering-only.
