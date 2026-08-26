# AIR_SLOT_G2_MONETARY_LITERATURE_PROPOSAL_20260826

Status: PROPOSAL FOR HUMAN REVIEW — NOT FROZEN.
Scope: DEVELOPMENT_ONLY. `paper_result=false`, `FINAL_TEST_ACCESS_COUNT=0`,
no Git, no Final Test, no `paper_full`.
Covers the two remaining G2 monetary items: (A) `P_itinerary` / `P_service`
anchor literature pass; (B) RMB `beta_k^m` anchor decision.
Frozen F1-F6 decisions are unchanged and restated only for reference.

## A. P_itinerary / P_service literature pass

### A.1 Manuscript contract (what the paper already requires)

- `Rolling_Airline_Recovery_v2/sections/04_implement.tex` L306-307,
  Table `tab:consequence_valuation_interface`:
  - `P_itin` row: `ABSTAIN; no current formal mapping`, literature anchor
    `bratuFlightOperationsRecovery2006, arikanIntegratedAircraftPassenger2016`.
  - `P_serv` row: `ABSTAIN; no current formal mapping`, literature anchor
    `ballTotalDelayImpact2010, cookEuropeanDelayCost2015`.
- `Rolling_Airline_Recovery_v2/sections/03_methodology.tex` L176-206,
  Eqs. `eq:m2_general_valuation_interface` / `eq:m2_cu_mapping` /
  `eq:m2_monetary_mapping`: `rho=ABSTAIN` implies `bot`; components are never
  zero-filled, never silently removed, never renormalized into a total.
- F5 (`AIR_SLOT_EXP23_G2_FREEZE_DECISIONS_20260825.md`): `P_itin`/`P_serv`
  stay ABSTAIN (event counts only, `monetary=NOT_ANCHORED`).
- Registry `registries/m4_eur_mapping_assumption_grounded_v1.json`:
  `P_itinerary` and `P_service` are `HUMAN_DECISION_REQUIRED` with no numeric
  `per_cu_money`; base reference is the EUROCONTROL 2004 text only
  (sec. 2.3.2.3.7 documents missed-connection costs qualitatively:
  compensation, rebooking, accommodation; no per-passenger numeric value).

### A.2 Evidence retrieved in this pass

- Cook & Tanner 2015 (EUROCONTROL European Airline Delay Cost Reference
  Values, Version 4.1, December 2015): official PDF downloaded and
  page-verified. Local copies:
  `D:\Cache\Python\Temp\cook_tanner_2015_v4_1.pdf` and
  `D:\Cache\Python\Temp\cook_tanner_2015_text.txt`.
  - §3.6.4: "It only relates to departure delay; nothing is due to the
    passenger for any type of arrival delay or missed connection per se."
    Consequence: an EU261-derived per-event anchor for missed connections
    would contradict the cited regulatory basis, and no such anchor may be
    claimed as EU261-grounded.
  - §3.6.7: "There is very little literature on actual passenger hard costs."
  - §3.6.8: Bratu and Barnhart [19] passenger-centric metrics; qualitative
    conclusion that flight-leg delays underestimate passenger delays for
    hub-and-spoke airlines. No per-event cost coefficients.
  - §3.6.9: care costs (meal vouchers, hotel accommodation, tax-free
    vouchers, frequent-flyer-programme miles, phonecards) from the empirical
    airline source Jovanovic [18], combined with a theoretical distribution
    of reaccommodation costs (rerouting/rebooking, ticket reimbursements,
    compensation). The report publishes no per-event EUR values from this
    source.
  - §3.6.20: only 10% of the soft costs in Table 18 are used in the report's
    own calculations: "this is a working estimate (limited evidence)".
  - Table 17 (passenger hard costs, EUR per passenger per minute, 2010), base
    scenario by delay magnitude: 5 min 0.06; 15 min 0.14; 30 min 0.24;
    60 min 0.41; 90 min 0.56; 120 min 0.70; 180 min 0.96; 240 min 1.20;
    300 min 1.44. Low scenario 0.04-0.88; high scenario 0.07-1.75.
  - Table 18 (passenger soft costs, EUR per passenger per minute, 2010), base
    scenario: 5 min 0.02; 15 min 0.09; 30 min 0.25; 60 min 0.69; 90 min 0.91;
    120 min 0.96; 180+ min 0.97. Low 0.01-0.27; high 0.03-1.08.
  - Tables 17-18 are per-passenger-minute rates conditioned on delay
    duration. They are NOT per-event rates, so they cannot anchor the
    event-count CUs (`N_miss = n_pax x 1[D_TO >= tau_itinerary]`,
    `N_svc = n_pax x 1[D_TO >= tau_service]`) without an additional
    duration-integration assumption.
- EUROCONTROL 2004 text (already in registry): §2.3.2.3.7 missed-connection
  costs qualitative only; 72 EUR/min network average and 0.30 EUR/pax/min are
  per-minute anchors (used for F_cont/F_exec/F_prop/R_oper/P_time), not
  per-event.
- Bratu & Barnhart 2006 (J. Scheduling 9(3):279-298, DOI
  10.1007/s10951-006-6781-0) and Arikan, Gurel & Akturk 2016 (AOR 236(2):
  295-317, DOI 10.1007/s10479-013-1424-2): recovery-optimization literature
  cited in the manuscript table; their role is structural (passenger-centric
  recovery modeling), and no per-event EUR coefficients were found in the
  retrieved material.
- Ball et al. 2010 (NEXTOR Total Delay Impact Study, Revised Final Report):
  US-focused; ROSAP download returned 403 and no local copy exists in either
  repo; it could not be page-verified in this pass and is therefore NOT used
  to anchor any value.

### A.3 Options for the human decision

- `OPTION_A_KEEP_ABSTAIN` (RECOMMENDED). Keep both components ABSTAIN in the
  monetary layer; the event-count CUs stay visible as native consequence
  units with `monetary=NOT_ANCHORED`. Matches the manuscript table, F5, the
  frozen registry status, and the standing rule that unsupported components
  are ABSTAIN, never zero-filled or fabricated. Zero additional assumption
  load; no manuscript edit needed.
- `OPTION_B_USER_AUTHORIZED_ASSUMPTION`. The user supplies an explicit
  per-event anchor plus its label and provenance (e.g. a named
  `USER_ASSUMED` value). This becomes a declared assumption, documented as
  non-literature, and only then is it implemented. This pass found no
  literature basis, so no numeric value is proposed by us.
- `OPTION_C_DERIVED_EVENT_ASSUMPTION` (NOT RECOMMENDED). Convert a
  per-minute Table 17/18 rate into an event value by multiplying a
  representative delay duration. This would fabricate a per-event anchor
  from a per-minute table, violates the no-fabricated-values rule, and is
  listed only for completeness.

### A.4 Supporting literature values (already frozen elsewhere; for reference)

- Ops layer (constructed EUR per CU, CU = minutes): BASE 72.0 EUR/min
  (EUROCONTROL 2004 network average), LOW/HIGH 0.5x/2.0x; applies to
  `F_continuity`, `F_execution`, `F_propagation` (unit-consistent linear
  assumption, no separate literature), `R_operating`.
- `P_time`: BASE 0.30 EUR/pax-min (EUROCONTROL 2004 summary item 6, carrier
  range 0.27-0.32); LOW/HIGH 0.5x/2.0x.
- EU261 layer (regulatory fact, frozen): tiers 250/400/600 EUR; 1500/3500 km
  thresholds; trigger 180 min (sensitivity 150/210); Option A dual-layer
  recommended, no cross-currency conversion.

## B. RMB beta_k^m decision

- Manuscript `04_implement.tex` L275-282: "For a supported reporting system
  m (with RMB represented by m=RMB when such a mapping is available)" — the
  RMB mapping is explicitly conditional on availability.
- F5: no fabricated RMB `beta_k^m` values.
- This pass found no RMB/CNY per-minute or per-event airline delay-cost
  literature; the retrieved anchors are EUR-based (EUROCONTROL 2004/2015)
  and the only cited US source (Ball et al. 2010) could not be retrieved.
- PROPOSAL: keep `m=RMB` uninstantiated (no `beta_k^RMB`); the constructed-EUR
  five-component system remains the single instantiated reporting system.
  Record the G2-RMB gate as closed by system-level ABSTAIN, consistent with
  the ABSTAIN semantics of Eqs. `eq:m2_general_valuation_interface` /
  `eq:m2_monetary_mapping`. This requires human approval.

## C. Proposed decisions awaiting approval

1. G2-P_itin/P_serv: `OPTION_A_KEEP_ABSTAIN` (recommended).
2. G2-RMB: close by system-level ABSTAIN; no `beta_k^RMB` values.
3. After approval, `registries/m4_eur_mapping_assumption_grounded_v1.json`
   `HUMAN_DECISION_REQUIRED` statuses are re-resolved in a new registry
   version (registry edits are NOT performed in this draft), and the G3
   spec draft is updated to freeze the monetary reporting fields.

## D. Files and boundaries

- New in this pass: this proposal doc and
  `codex_framework/PAPER_OUTPUT_SPEC_V1_DRAFT_20260826.json` (draft, not the
  frozen `PAPER_OUTPUT_SPEC_V1.json`).
- Downloaded literature: `D:\Cache\Python\Temp\cook_tanner_2015_v4_1.pdf`,
  `D:\Cache\Python\Temp\cook_tanner_2015_text.txt`.
- Boundaries honored: no `model/**`, `registries/**`, `configs/**` edits; no
  Final Test; no Git; no `paper_full`; existing frozen artifacts untouched.
- `FINAL_TEST_ACCESS_COUNT = 0`; `PAPER_FULL_RUN = FALSE`; `GIT = NO_COMMIT`.
