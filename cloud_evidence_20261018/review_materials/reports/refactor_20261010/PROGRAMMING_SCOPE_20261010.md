# Air Slot JATM programming scope

This file translates the 2026-10-10 review memo into programming work. It is
an engineering plan only. It does not edit the manuscript, decide scientific
claims, or authorize a new experiment.

## Scope boundary

- Code, audit scripts, schemas, manifests, lineage tables, and validation outputs are in scope.
- Manuscript prose, Supplement layout, literature verification, and claim wording are out of scope.
- Final-Test, held-out exploration, model retraining, calibration changes, and scientific recomputation remain gated.
- Existing `Exp1`-`Exp4` module names remain unchanged; paper modules `E1`-`E4` are mapped onto them and new runners only where an actual gap is confirmed.

## Engineering order

1. **G0 read-only evidence layer**: materialize source-to-table lineage, timestamp availability checks, unit traces, support-flow summaries, and weighted-marginal audits.
2. **Contract freeze**: record the verified estimand, cohort, representation, objective, capacity, grid, and support semantics in machine-readable form.
3. **E1/E2 implementation gaps**: add only missing diagnostics for Stage-I retrospective screening, eligible-cohort Stage-II evaluation, action response, and matched History/Current comparisons.
4. **E3 objective × distribution**: implement only after Marginal passes weighted-measure audit; keep HJ reference per objective and separate additive/threshold/headroom diagnostics.
5. **E4 cross-year runner**: reuse existing year PRE/M2 inputs and apply the same frozen contract; report unsupported years and negative results explicitly.
6. **Validation**: import, compile, dependency, contract regression, then bounded audit fixtures. No formal executor or Final-Test in this phase.

## Current source mapping

| Paper module | Existing engineering surface | Programming status |
|---|---|---|
| E1 screening sufficiency | `model/M3/stage1.py`, `model/M2/comparison_support.py`, `model/M4/evaluation.py`, `formal/v2_phase7/executor/attention_decisions.py` | Existing retrospective benchmark; window semantics still require audit |
| E2 decision-layer asymmetry | `model/M1/state_representation.py`, `model/M3/stage2.py`, `model/M3/transition.py`, `model/M4/evaluation.py`, `formal/v2_phase7/executor/recovery_decisions.py` | Existing fixed HJ cohort path; eligible-cohort and action-response audit gaps remain |
| E3 objective × distribution | `model/M1/state_representation.py`, `model/M3/stage2.py`, `model/M2/comparison_support.py`, `formal/v2_phase7/consequence_domain_emphasis_robustness.py` | Blocked until weighted Marginal audit passes |
| E4 rolling/cross-year | `model/PRE/streaming/development.py`, `data2/scripts/run_multiyear_pre.py`, `data2/scripts/run_paper_formal.py`, `artifacts/models/pre/PRE_MULTIYEAR_V1/` | Existing development/runtime inputs; held-out cross-year evaluation is not yet authorized |

## Uncertainty register requiring user confirmation

| ID | Uncertainty | Proposed engineering solution | Gate |
|---|---|---|---|
| U-G0-1 | Whether current candidate rows form real same-time capacity windows | Build a read-only window audit; if unsupported, retain explicit retrospective benchmark metadata | G0-1 |
| U-G0-2 | Whether deterministic Marginal permutation preserves weighted primitive measures | Compare every discrete weighted CDF/mass table per node; fail closed with `BLOCKED_REPRESENTATION` | G0-2 |
| U-G0-3 | Whether `T_IB` and `F_continuity` use compatible units/time bases | Produce representative PRE/TURN/TAXI traces from raw field to consequence | G0-3 |
| U-G0-4 | Which components respond to Stage-II target `u` | Emit per-scenario, per-target seven-component deltas and classify responsive/invariant/conditional/unsupported | G0-4 |
| U-G0-5 | Whether current support/cohort filtering changes the estimand | Produce node-flow counts and reason-coded exclusions from canonical node through Stage II | G0-5 |
| U-G0-6 | Whether History gain is capacity/model-specification confounded | Add matched-capacity and model-manifest comparison diagnostics before any retraining | G2/G3 |
| U-G0-7 | Whether Point medoid is an adequate sole point baseline | Add audit-only alternative point summaries; do not replace the frozen Point result automatically | G2 |
| U-G0-8 | Whether `lambda` and `U_max` are separable policy parameters | Add contract-level sensitivity metadata and separate fixed-cost/fixed-grid analysis design; no rerun yet | G2/G3 |

## Immediate implementation decision

The next code change should be the **read-only G0 audit layer**, not a new
scientific runner. It should write under
`D:\Local_Projects\airslot\reports\refactor_20261010\` or a separately
approved diagnostics root, include input hashes and git HEAD, and preserve
`ABSTAIN`, `UNKNOWN`, `NOT_RUN`, and `BLOCKED` states.
