# AirSlot V2 — Phase 0 legacy/data audit

Date: 2026-09-18. Scope: Phase 0 of the approved plan (Phases 0-5; no Phase 6/7,
no new Final-Test access). Authority order: latest manuscript main text > V2
instruction rev2 > legacy repo > legacy experimental products.

Engineering instruction for this round: `docs/AirSlot_V2_Instruction_rev2_20260918.md`
(rev2 sha256 `1d38e85af493c8d6ad8e3b51b441e58374e57b405c4b701b86f04d26c5e0d339`).
Original rev1 kept read-only at
`D:\Download_all\AirSlot_V2_Final_Engineering_Implementation_Instruction_20260918.md`
(sha256 `4b3a79a4294650e4b2b1f67526b31b9e27b7f9e647f64fd3a27242eedf482af2` recorded at build time by
`tmp/build_instruction_rev2.py` output).

---

## 1. Attachment inventory and hash lineage

`Rolling_Airline_Recovery (20).zip` — sha256
`4a4e8754894680b83d724b0cc4ca0d07611d06ffc1e09038312be9f97044a1d2`, 17 entries,
produced 2026-09-18 21:20. Treated as read-only authority snapshot.

| zip entry | ties to | status |
|---|---|---|
| `main.tex`, `preamble.tex` | `_review_Rolling_Airline_Recovery_17` (byte-identical) | reused unchanged |
| `references.bib` | updated vs `_review_..._17` (60034 vs 59695 bytes) | reused unchanged |
| `sections/01_intro.tex` | `D:\Download_all\01_introduction_revised_20260918.tex` (identical) | latest main text |
| `sections/02_literature_review.tex` | `02_related_work_revised_20260918.tex` (identical) | latest main text |
| `sections/03_methodology.tex` | `03_methodology_revised_20260918_v3.tex` (identical) | latest main text |
| `sections/04_implement.tex` | `04_implementation_revised_20260918.tex` (identical) | latest main text, corrected in working copy (E1) |
| `sections/05_experiment.tex` | `05_empirical_evaluation_revised_20260918.tex` (one `\label` differs) | latest main text |
| `sections/06_discussion.tex`, `07_conclusion.tex` | 45-byte section stubs | preserved as-is |
| `sections/00_abstract.tex` | 0 bytes | preserved as-is (not rewritten) |
| `sections/appendix.tex` | `_review_..._17` appendix (identical) | **not yet synchronized**; corrected in working copy (E2) |
| `figures/FIG1..FIG5_*_FINAL_TEST.pdf` | `_review_..._17` figures (identical) | prior Final-Test figures, not regenerated |

Working copy: `D:\Local_Projects\airslot\_review_Rolling_Airline_Recovery_20\`
with `MANUSCRIPT_EDIT_LEDGER.md` (before/after hashes and diff shape).

## 2. Rulings ledger (owner, 2026-09-18)

| # | ruling | effect |
|---|---|---|
| R1 | `P_itinerary = N_pax · s_conn · 1(D_TO > 45)` | manuscript corrected (E1); V4 code and DB1B reference retained |
| R2 | CU = five positive Train medians + two assumption event normalizations (scale = one native event unit; not empirical median) | M2 CU rebuilt as V5; appendix corrected (E2) |
| R3 | Stage-II formal path = exact enumeration; Pyomo + HiGHS = parity backend | instruction rev2 §11; no longer a deviation |
| R4 | `P^C` unique consequence-based priority authority; `P^D` parallel delay comparator; one shared Stage-I selector | M3 ownership contract |
| R5 | nominal comparison support `m^CS >= 0.90` owned by the M2/comparison-support layer; PRE owns evidence/data support only | manuscript sentence added (E1); code in M2 |
| R6 | `m^CS` sensitivity uses only manuscript-predefined values; the latest main text predefines none | only nominal 0.90 this round; recorded in freeze draft |
| R7 | Phase 5 freeze artifacts are drafts (`DRAFT_NOT_ACTIVATED`, `freeze_commit: PENDING`) | no formal freeze claim |
| R8 | no push; local checkpoint commits allowed | per-phase commits |

## 3. LEGACY_TO_V2_MIGRATION_MAP

| legacy object | V2 target | action |
|---|---|---|
| `model/PRE/**` (chain, rolling nodes, stages, admissibility, splits, references) | Phase 1 PRE service | reuse; add evidence/data-support contract only (no `m^CS`) |
| `model/M1/**` (GRU, labels, sampling, calibration, runtime) | Phase 2 M1 service | reuse; representation ownership (Point/Marginal/Joint) moves into M1 |
| `model/M2/**` + `registries/m2_data2_formal_cu_v4.json` | Phase 2 M2 service + new CU V5 | rebuild CU partition to five+two; keep native formulas and references |
| `model/M3/**` (A00/candidate registry, action templates A01-A23, factual adapter) | Phase 3 M3 decision layer (Stage I + Stage II) | template action space retired from the paper-primary optimization contract; factual adapter kept |
| `model/M4/**` legacy screening/alignment | Phase 4 M4 evaluator (`L_att`, `L_rec`, diagnostics) | rewrite ownership: M4 no longer selects shortlists |
| `exp/exp1`, `exp/exp2`, `exp/shared` | Phase 5 Development pipelines | reuse metric code; results recomputed under V5 CU where they depend on CU |
| 9/16 uncommitted M3/M4 WIP | none (unreferenced legacy) | kept in place; baseline patch `tmp/v2_wip_baseline_20260918/` |

## 4. DATA_FIELD_MAP (V2-relevant slice)

| source (BTS 2019) | PRE canonical | V2 quantity |
|---|---|---|
| `FlightDate`, `Tail_Number`, `Reporting_Airline` | aircraft chain, `episode_id`, `aircraft_id` | state reconstruction identity |
| `Origin`, `Dest`, `CRSDepTime` | `connection_airport_id`, `sobt` | Stage-II boundary and action grid |
| `ArrTime` (predecessor) | `R_IB` (actual in-block) | `F_continuity = max(0, R_IB - turnaround_reference)`, `LB_OB = max(SOBT, R_IB + T_turn,lb)` |
| `DepTime` (successor) | `AOBT` / `D_OB` | `F_execution = D_OB`; headroom `H = [AOBT - LB_OB]_+` |
| `TaxiOut` | `D_TX` | `R_operating = D_TX` |
| derived | `D_TO = D_OB + D_TX` | `P_time`, `P_itinerary`, `P_service`, `F_propagation` inputs |
| DB1B Q1-Q2 | `s_conn` reference | `P_itinerary = N_pax · s_conn · 1(D_TO > 45)` |
| T-100 | `N_pax` reference | passenger-volume scaling |
| — | scenario weights `w_s`, common-support set `Ω^CS`, mass `m^CS` | `P^D = E[D_TO | Ω^CS]`, `P^C = Φ_C(C^CU)` |

Full per-column provenance remains in `data2/DATA_USAGE.md` and the PRE canonical
contracts; this map records only fields touched by the V2 decision chain.

## 5. REUSABLE_ARTIFACT_MAP

| artifact | role | reuse rule |
|---|---|---|
| `artifacts/models/m1/M1_FROZEN_H16`, `M1_FROZEN_H8` | primary / lower-capacity state models | reuse if same scientific object and split |
| `artifacts/diagnostics/v5_development_freeze/DATA2_*_REFERENCE_TRAIN_FROZEN_V1.json` | turnaround / taxi / downstream / passenger Train references | reuse as references (unchanged definitions) |
| `artifacts/diagnostics/v5_development_freeze/M2_DATA2_TRAIN_SCALES_V1.json` | Train consequence scales | reuse the five principal medians for V5 |
| `artifacts/experiment/shared/development/SHARED_DEVELOPMENT_INPUTS.parquet`, `SHARED_SCENARIO_INPUTS.parquet` | Development node/scenario cohort (1,769 nodes; 64 scenarios/node) | reuse; recompute CU for the two event components under V5 |
| `artifacts/experiment/exp1/development/EXP1_HISTORY_CURRENT_*` | Current vs History Development evidence | reuse state/metric portions; CU-dependent transmission recomputed |
| `artifacts/experiment/exp1/development/EXP1_REPRESENTATION_*` | Point/Marginal/Joint Development evidence | reuse as prior evidence; recomputed under V5 for the decision layer |
| `artifacts/experiment/final_test/**` | prior Final-Test outputs (access count 1) | **not reusable** under the new CU definition; untouched |

## 6. SUPERSEDED_OBJECTS

1. `registry M2_DATA2_FORMAL_CU_V4` — seven-median partition superseded by V5
   (five principal medians + two event normalizations). Historical file retained.
   V4 medians kept for the five principal components: `F_continuity 43.0`,
   `F_execution 17.0`, `F_propagation 10.0`, `P_time 990.3555555555556`,
   `R_operating 5.0`; dropped from the empirical partition:
   `P_itinerary 9.882948210182091`, `P_service 104.88473684210527`.
   Erratum (freeze-precheck 2026-09-19): the `F_continuity 43.0` value was
   derived from the superseded turnaround reference; the V5 chain now uses the
   corrected A2 recomputation `44.0`. See `docs/V2_FREEZE_PRECHECK_REPORT.md`.
2. `registry M2_DATA2_FORMAL_CU_V2` semantics (five+two) — restored as the CU
   *partition*, but its stale medians (`11.0`, `1037820.0`) are **not** adopted;
   V5 uses the V4 recomputed medians for the five principal components.
3. `exp/shared/recovery_priority.py::summarize_delay_score` — deviation from the
   manuscript delay comparator (see §7).
4. M3 action-template optimization contract (A01-A23) for the paper-primary path.
5. The 9/16 uncommitted M3/M4 WIP ownership model (Stage-I screening in M4).
6. Prior Final-Test experimental products under the V4 CU definition.

## 7. `P^D` authority record

- Authority (unique, confirmed): latest manuscript §4,
  `eq:empirical_delay_score` — `P^D_{i,t} = E[D^{TO}_{i,t} | Ω^CS]`
  = `(1/m^CS) Σ_{s∈Ω^CS} w_s D^{TO}_{i,t,s}` (ZIP section 04, lines 336-344).
- Instruction rev2 §7 concurs: the delay-signal adapter belongs to M3 Stage I.
- Legacy implementation deviation: `exp/shared/recovery_priority.py::summarize_delay_score`
  computes `Σ w_s D^{TO}_s` over supported scenarios (no renormalization by
  `m^CS`) and returns `UNSUPPORTED` if any scenario lacks delay support
  (all-or-nothing support). Under partial support the two definitions differ.
- Resolution: V2 M3 Stage-I implements the manuscript conditional mean on the
  M2 comparison-support set; the legacy function is recorded as superseded and is
  not used on the paper-primary path. No escalation required: the authority is
  unambiguous. Interaction between the conditional mean and the `m^CS >= 0.90`
  inclusion rule is defined as "form the full-precision mean on `Ω^CS`, then apply
  the inclusion threshold to the node".

## 8. Manuscript corrections recorded

| id | file | before sha256 | after sha256 |
|---|---|---|---|
| E1 | `sections/04_implement.tex` | `935951250a1cb46aca0d3f4304fa7d9a6ff88c93c75dce069c7eb8c1de802356` | `215c365ece91e0a0855efe3f91120518bb009f8dcc962c12e96f9fa2129b984c` |
| E2 | `sections/appendix.tex` | `eb3cf0854049dc43d80352ef614832b55d53ba70acd22ff6c28f9b60a3c67bbc` | `e71006658f4daf0790a032ce7a4ba233c5c468ff5d659e55d768b6794a737e0e` |

Diff shape: 16 and 23 changed lines respectively; no other files touched.
Ledger: working-copy `MANUSCRIPT_EDIT_LEDGER.md`.

## 9. Open items / escalations

- None blocking. Escalation triggers for later phases: any conflict that would
  change estimand, feasible set, state transition, consequence definition,
  objective, or evaluation population; or an unresolvable authority conflict.
- Recorded but not acted on this round: numeric `m^CS` sensitivity values
  (none predefined by the latest main text) are not adopted; Phase 5 freeze draft
  carries `m^CS_sensitivity = NOT_PREDEFINED_BY_MANUSCRIPT`.
- 9/16 WIP tests (`tests/m3|m4/*_v3.py`) encode the superseded ownership model and
  are reported for status only; they are not acceptance gates.
