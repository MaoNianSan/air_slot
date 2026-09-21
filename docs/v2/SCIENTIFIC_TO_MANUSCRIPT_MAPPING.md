# AirSlot V2 - Scientific Framework to Manuscript Mapping

The single place to update when the manuscript structure changes. It maps each
paper object to its owning module, source artifact, paper-facing artifact and
manuscript destination. No manuscript text is modified by this file.

## Section 4 - framework

| Scientific object | Owning module | Source artifact | Paper-facing artifact | Manuscript destination | Status |
|---|---|---|---|---|---|
| PRE: admissibility, chain/rolling nodes, canonical stage rule, splits | `model/PRE/` | `validation/split_isolation.py`, `docs/V2_PHASE1_REPORT.md` | Section 4.1 text (to be authored) | Section 4.1 | COMPLETE |
| M1: state estimation and representation ownership | `model/M1/` | `artifacts/diagnostics/v2_phase5_development/FAMILY_A_*.json`, `FAMILY_B_*.json` | Section 4.2 text (to be authored) | Section 4.2 | COMPLETE |
| M2: consequence construction, common support, CU | `model/M2/` | `registries/m2_data2_formal_cu_v5.json` | Section 4.3 text (to be authored) | Section 4.3 | COMPLETE |
| M3: Stage-I attention + Stage-II recovery optimisation | `model/M3/` | `registries/v2_stage2_solver_authority_reconciliation.json` | Section 4.4 text (to be authored) | Section 4.4 | COMPLETE |
| M4: common-basis comparison / evaluation design | `model/M4/` | `artifacts/experiment/final_test_v2/checkpoints/M4_COMPARISONS.json` (local) | Section 4.5 text (to be authored) | Section 4.5 | COMPLETE |

## Section 5 - experiments

| Scientific object | Owning module | Source artifact | Paper-facing artifact | Manuscript destination | Status |
|---|---|---|---|---|---|
| Final-Test Stage-I attention (stage x q) | `formal/v2_phase7/executor/attention_decisions.py` | `ATTENTION_DECISIONS` checkpoint (local) | `artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md` (5.2 table) | Section 5.1 / 5.2 | COMPLETE |
| Stage-II recovery decisions (u*, V) | `formal/v2_phase7/executor/recovery_decisions.py` | `RECOVERY_DECISIONS` checkpoint (local) | same view (5.3 table) | Section 5.3 | COMPLETE |
| CURRENT_JOINT vs reference | `formal/v2_phase7/executor/m4_comparisons.py` | `M4_COMPARISONS` checkpoint (local) | same view (5.4 table) | Section 5.4 | COMPLETE |
| HISTORY_POINT vs reference | same | same | same view | Section 5.4 | COMPLETE |
| HISTORY_MARGINAL vs reference | same | same | same view | Section 5.4 | COMPLETE |
| Paired episode bootstrap CIs | `formal/v2_phase7/executor/bootstrap.py` | `BOOTSTRAP` checkpoint (local) | same view | Section 5.4 | COMPLETE |
| Predefined sensitivity scope (lambda, turnaround, U_max, H8) | `formal/v2_phase7/executor/` | freeze registries | same view (5.5 table) | Section 5.5 / Appendix | Axes COMPLETE; RESULTS BLOCKED (require a new authorized epoch) |

## Rules for this layer

- Comparator results come from the persisted `M4_COMPARISONS` payload; the
  reference self-comparison identity (`L_att = 0`, `L_rec = 0`, `A0 = A5 = 1`)
  must never be presented as the CURRENT_JOINT / HISTORY_POINT /
  HISTORY_MARGINAL result.
- `L_total` is never constructed; monetary conversion remains secondary
  interpretation only.
- Solver authority in any paper text: `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`
  is the primary solver; Pyomo+HiGHS is an independent parity backend on
  representative fixtures. The historical checkpoint field
  `M3_FORMAL_HIGHS_OBJECTIVE_ON_FIXED_REFERENCE_COHORT` is provenance of an
  earlier label and is not the active authority.
- Fixed-window history stays `NOT_AVAILABLE_NOT_FROZEN`; no substitute model is
  trained to fill it.
- similar-delay 5/10/15, itinerary 30/60, service 150/210 are
  `NOT_ACTIVATED_BY_PHASE6_FREEZE` and carry no formal paper claim.
