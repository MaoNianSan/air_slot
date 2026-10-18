# AirSlot V2 - Section 4 / Section 5 Experiment Status

Completion matrix over already-persisted artifacts. No experiment was re-run to
produce this page. Allowed labels only: `COMPLETE`, `COMPLETE_CHECKPOINT_ONLY`,
`COMPLETE_NEEDS_PAPER_VIEW`, `NOT_AVAILABLE_NOT_FROZEN`, `NOT_REQUIRED`, `BLOCKED`.

## Section 4 - Development / construction items

| Item | Status | Evidence |
|---|---|---|
| History vs Current comparison (H16 primary) | COMPLETE | `../../artifacts/diagnostics/v2_phase5_development/FAMILY_A_STATE_FAMILIES.json` |
| H16 primary model | COMPLETE | `../../artifacts/models/m1/M1_H16_HISTORY_PRIMARY/` |
| H8 capacity sensitivity | COMPLETE | `../../artifacts/models/m1/M1_V2_PHASE5_H8_SENSITIVITY/` (matched audit PASS) |
| Point / Marginal / Joint representations | COMPLETE | `../../artifacts/diagnostics/v2_phase5_development/FAMILY_B_REPRESENTATION_FAMILIES.json` |
| Consequence / CU construction | COMPLETE | `../../registries/m2_data2_formal_cu_v5.json` |
| Stage-II Train support | COMPLETE | `../../registries/v2_scientific_freeze_r2.json` (artifact identity contract) |
| q policy grid | COMPLETE | Frozen grid `{0.05, 0.10, 0.20, 0.30}`; executed in Section 5.2 |
| lambda policy grid | COMPLETE | Frozen grid `{0.10, 0.25, 0.50, 1.00}`, nominal `0.25` |
| Turnaround support | COMPLETE | Train Q10/Q20/Q30 = 34 / 41 / 47 |
| U_max support | COMPLETE | Train headroom Q80/Q90/Q95 = 25 / 45 / 75 |

Section 4 Development evidence is complete; nothing here depends on new
Final-Test access.

## Section 5 - Final-Test items

| Item | Status | Evidence |
|---|---|---|
| Final-Test canonical cohort | COMPLETE | `../../formal/FINAL_TEST_COHORT_MANIFEST_V1.json` (128 episodes) |
| HISTORY_JOINT (reference variant) | COMPLETE | `../../artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md` |
| CURRENT_JOINT | COMPLETE | same view, Section 5.3 / 5.4 tables |
| HISTORY_POINT | COMPLETE | same view |
| HISTORY_MARGINAL | COMPLETE | same view |
| Stage-I attention evaluation (stage x q) | COMPLETE | same view, Section 5.2 table |
| Stage-II recovery decisions (u*, V) | COMPLETE | same view, Section 5.3 table (aggregates) |
| M4 L_att | COMPLETE | same view, Section 5.4 table |
| M4 L_rec | COMPLETE | same view, Section 5.4 table |
| A0 / A5 diagnostics | COMPLETE | same view, Section 5.4 table |
| Bootstrap (paired episode-level, seed 20260906) | COMPLETE | same view (95% CIs); seed provenance PASS |
| Post-run scientific integrity audit | COMPLETE | `../../artifacts/experiment/final_test_v2/PHASE7_POSTRUN_SCIENTIFIC_AUDIT.json` |
| Paper views | COMPLETE | `../../artifacts/experiment/final_test_v2/PAPER_FACING_SECTION5_VIEWS.md` |
| Section 5.5 sensitivity RESULTS (lambda / turnaround / U_max / H8) | BLOCKED | Axes are frozen and declared; no Final-Test sensitivity run is persisted, and producing one requires a new human-approved access epoch |
| Full per-node / per-row checkpoint payloads (9 stages, 587,375,479 bytes) | COMPLETE_CHECKPOINT_ONLY | Local `artifacts/experiment/final_test_v2/checkpoints/`; identities in `../../artifacts/experiment/final_test_v2/CHECKPOINT_MANIFEST.json` |
| similar-delay 5/10/15 | NOT_REQUIRED | `NOT_ACTIVATED_BY_PHASE6_FREEZE`; no paper claim |
| itinerary 30/60, service 150/210 | NOT_REQUIRED | `NOT_ACTIVATED_BY_PHASE6_FREEZE`; no paper claim |
| fixed-window history | NOT_AVAILABLE_NOT_FROZEN | No substitute model trained |

## Notes

- Section 5.2 `stage x q` is the primary operating design; `q` is not an OFAT
  sensitivity axis (see `PAPER_FACING_SECTION5_VIEWS.md`).
- Sensitivity axes are declared in the same view with
  `sensitivity_results_status = DECLARED_SCOPE_ONLY_NO_SENSITIVITY_RESULTS_IN_THIS_RUN`.
- Final-Test access accounting after this run: historical total 1, Phase-7
  increment 1, current total 2. No further epoch is planned or authorized.
