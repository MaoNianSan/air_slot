# AirSlot V2 - Scientific Pipeline

Where each stage of the paper-primary pipeline lives in code, what it owns, and
which authority governs it. This file is a reading map, not a specification: the
frozen definitions live in the freeze registries referenced at the bottom.

```text
PRE                      model/PRE/
  -> admissibility, chain/rolling nodes, canonical stage rule, splits
M1 State Estimation     model/M1/
  -> H16/H8 history models, state representations, calibration, sampling
M2 Consequence + Priority  model/M2/
  -> consequence profile, common support (Omega^CS, m^CS), CU construction, priority
M3 Attention + Recovery  model/M3/
  -> Stage-I selector, Stage-II feasible set, transition, objective, enumeration
M4 Common-Basis Evaluation  model/M4/
  -> L_att, L_rec, A0/A5 diagnostics, common-basis comparison on fixed R_g*
Experiment / Reporting Views  formal/v2_phase7/executor/
  -> one-shot Final-Test DAG, checkpoints, bootstrap, paper-facing views
```

Shared decision contracts live in `model/common/` (dependency direction
`common -> PRE -> M1 -> M2 -> M3 -> M4 -> pipeline/experiments`; M2 never
depends on M3).

## Phase-7 executor DAG

The sealed Final-Test executor is `formal/v2_phase7/executor/`; each DAG stage is
its own module and every stage consumes only the validated checkpoint of the
previous one:

| DAG stage | module |
|---|---|
| CanonicalNodes | `executor/nodes.py` (+ one-shot `executor/raw_entry.py` / `raw_source.py`) |
| StateVariants | `executor/state_variants.py` |
| ConsequenceVariants | `executor/consequence_variants.py` |
| AttentionDecisions | `executor/attention_decisions.py` |
| ReferenceRecoveryCohort | `executor/reference_cohort.py` |
| RecoveryDecisions | `executor/recovery_decisions.py` |
| M4Comparisons | `executor/m4_comparisons.py` |
| Bootstrap | `executor/bootstrap.py` |
| PaperViews | `executor/paper_views.py` |

`executor/runner.py` drives the immutable-checkpoint DAG with resume support;
`executor/pipeline.py` is the Gate-B callback body; `executor/services.py` loads
the frozen M1/M2/M3/M4 services (the executor never restates a scientific
formula). Release validation, access-audit ledger transitions and other guards
sit in the parent package (`formal/v2_phase7/release.py`, `access_audit.py`,
`checkpoint_resume.py`, `gate_a.py`, `gate_b.py`).

## Frozen authority of record

- Stage-II primary solver: `EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID`
  (`deterministic_tie_break = SMALLEST_U`), fixed action grid `{0,5,...,U_max(theta)}`.
- Pyomo+HiGHS: parity backend only, representative PRE/TURN fixtures, never a
  production row requirement (`highs_required_for_production_rows = false`).
- `solver_status` is Stage-II solution provenance / backend identity
  (`PYOMO_HIGHS`, `EXACT_ENUMERATION`, `NOT_RUN`), never a termination state;
  HiGHS termination lives in the separate parity record.
- Reference representation: `H_g^{C,*} = H_g^{C,History+Joint}` with
  `R_g* = H_g^{C,History+Joint} INTERSECT StageIISupported`; comparator variants
  produce their own `H_g^(r)` for `L_att` but are re-scored on the same fixed `R_g*`.
- Reference self-comparison (`L_att = 0`, `L_rec = 0`, `A0 = A5 = 1`) is an
  identity check, not a comparator result; `L_total` is never constructed.
- Typed states (`ABSTAIN_NO_COMMON_SUPPORT`, `UNDEFINED_ZERO_RECOVERABLE_VALUE`,
  `NOT_ACTIONABLE`, `N/A_NOT_DEFINED`) are legal scientific results and are never
  silently coerced to zero.

## Authority files

- `../V2_SCIENTIFIC_FREEZE_SUMMARY.md`, `../V2_PHASE6_FREEZE_REPORT.md`
- `../V2_SCIENTIFIC_FREEZE_R2_CORRECTION_REPORT.md`
- `../../registries/v2_scientific_freeze.json` (Phase-6, immutable)
- `../../registries/v2_scientific_freeze_r2.json` (immutable)
- `../../registries/v2_stage2_solver_authority_reconciliation.json` (active solver authority)
