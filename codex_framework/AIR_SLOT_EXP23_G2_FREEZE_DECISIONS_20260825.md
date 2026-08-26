# AIR_SLOT_EXP23_G2_FREEZE_DECISIONS_20260825

Human-approved freeze decisions (2026-08-25) for the Exp2/Exp3 G2 paper-facing
contracts.  Values are fixed and must not be changed.

## F1 Exp2 POINT

Weighted medoid: `argmin_c sum_s w_s ||z_s - z_c||^2`; coordinates are only
the three manuscript primitives `(T_IB_A00, D_OB, D_TX)` (manuscript
`R^IB, Delta^OB, T^TX`; mapped via
`exp/workflows/m1_v2_current_stage_scenario_envelope.py` `R_IB -> T_IB_A00`).
`D_TO` is derived and used only for identity validation; it never enters the
distance.  Ties break deterministically by scenario order.  Output: the
selected scenario copied as a unit-weight degenerate representation (S=1);
lineage and field sources preserved.  The marginal-median-vector point is
Appendix-only and may not replace the principal after Test.

## F2 q-series

Not implemented.  The paper scope has only q=1.0 full rearrangement;
partial-q (0.25/0.50/0.75/1.00) does not exist in the manuscript and appears
neither in the main text nor in an appendix.  Recorded in
`docs/HUMAN_DECISION_LOG.md`: "partial-q 未采用（原稿未定义）".

## F3 Exp3 perturbation

`delta in {0, 5, 10}` minutes; `S_{t-delta}` is the frozen state identity of
the past node at `t - delta`, never re-estimated, interpolated, or read back
from the current state.  Nodes without a legal vintage are typed-excluded as
`EXP3B_VINTAGE_NOT_AVAILABLE`; fallback to the most recent/current state is
forbidden.  Lags 15/20/30 are forbidden.  `E_t`, `A_t`, consequence,
response, and `J` are all fixed.

## F4 G2-M3

Production = the frozen declared scenario-response registry (22 non-A00
`theta_a` / footprint / `ell_a`); support class `SCENARIO` is carried
throughout and never promoted.  A00 = samplewise identity.  Paper wording is
a declared-assumption model-implied ordering, never a causal/empirical
effect.

## F5 G2-M4 monetary

Paper reporting system = constructed-EUR reference-basis five-component
aggregate `(F_cont, F_exec, F_prop, P_time, R_oper)`; BASE principal with
LOW/HIGH = 0.5x/2.0x sensitivity; status
`ASSUMPTION_GROUNDED/REFERENCE_BASED`.  `P_itin`/`P_serv` stay ABSTAIN
(event counts only, `monetary=NOT_ANCHORED`).  No fabricated RMB `beta_k^m`
values.

## F6 G2 positive tail

`alpha = 0.90`; empirical weighted VaR/CVaR over the frozen S=250 aligned
ensemble; `OVERFLOW_TAIL` retains raw values (no clamp, no truncation, no
extrapolation, no zero-fill).  `model/M4/residual_risk.py::weighted_var_cvar`
is already compliant; this item is documentation and decision record only -
no model change.

## F7 G2 P_itin / P_serv (approved 2026-08-26)

`P_itinerary` / `P_service` = `OPTION_A_KEEP_ABSTAIN`.  Event-count CUs
(`N_miss`, `N_svc`) remain visible as native consequence units; the monetary
layer is `monetary=NOT_ANCHORED`; no zero-fill, no inference, no derived
per-event anchor.  Literature basis (Cook & Tanner 2015 v4.1, page-verified):
section 3.6.4 EU261 covers departure delay only ("nothing is due to the
passenger for any type of arrival delay or missed connection per se");
sections 3.6.7/3.6.9 hard/care costs are qualitative only; Tables 17-18 are
EUR per passenger per minute rates conditioned on delay duration, not
per-event rates.  Registry:
`registries/m4_eur_mapping_assumption_grounded_v2.json` (v1 untouched;
`anchor_status=ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY`,
`base_per_cu_money=null`, bands null).

## F8 G2 RMB reporting (approved 2026-08-26)

RMB = system-level ABSTAIN.  `m=RMB` is not instantiated; no `beta_k^RMB`
values exist and none may be fabricated.  The constructed-EUR five-component
system is the single instantiated reporting system.  This closes the
G2-RMB-beta numeric anchor gate by ABSTAIN, consistent with Eqs.
`eq:m2_general_valuation_interface` / `eq:m2_monetary_mapping` (ABSTAIN =>
bot).  Registry field:
`rmb_reporting_system=NOT_INSTANTIATED_NO_BETA_K_RMB`.

## Manuscript references

- `Rolling_Airline_Recovery_v2/sections/05_experiment.tex` L121-127
  (`z=(R^IB, Delta^OB, T^TX)`), L128-134 (Marginal = independent permutation
  of the three primitives, marginals unchanged), L148 (Point = central joint
  scenario, no component splicing), L150-159 (Variogram p=0.5), L206-237
  (Exp3 anchor and `D(delta)=F_D(E_t, S_{t-delta}, A_t)`, `delta in {0,5,10}`).
- `Rolling_Airline_Recovery_v2/sections/03_methodology.tex` L400-444
  (interface contract, `A^eval/A^cmp`, support is never promoted,
  `J=(1-lambda)E[L]+lambda*CVaR_alpha`).
- `Rolling_Airline_Recovery_v2/sections/04_implement.tex` L275-289
  (support-gated monetary, RMB "when available"), L291-316 (`P_itin`/`P_serv`
  ABSTAIN), L319-345 (23 templates, declared scenario-response), L388-396
  (`lambda=0.25`, `alpha=0.90`).

## Residual items

- G2 monetary items closed on 2026-08-26: F7 (`P_itin`/`P_serv` ABSTAIN) and
  F8 (RMB system-level ABSTAIN; no `beta_k^RMB` values).  The former
  RMB-beta undetermined item is removed; no numeric anchor exists and none
  is fabricated.
- Positive tail is frozen per F6 (documented; no model change).
- Section 4<->5 manuscript text corrections are handled as a separate case
  (not part of this freeze).

## Safety

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
GIT = NO_COMMIT
