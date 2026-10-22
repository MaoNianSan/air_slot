# AGENTS.md — Air Slot working conventions

This repository is the single canonical Air Slot code authority
(`D:\research\air_slot\code\explore`, branch `v2/paper-primary`). Read
`REPOSITORY_AUTHORITY.md` before changing anything scientific.

## Scientific contracts (frozen)

- Stage-I screening: `K = ceil(q * N)`, q grid (0.05, 0.10, 0.20, 0.30),
  nominal q = 0.10, tie-break `(-score, episode_id, node_id)`, common-support
  nodes only, unsupported canonical nodes are typed abstention (never
  replaced). Do not retrain, recalibrate, or reselect.
- Stage-II: exact enumeration over the finite 5-minute action grid is the
  production authority; HiGHS is parity-only. `u*` ties resolve to the
  smaller u; `V = J(0) - J(u*)`; lambda nominal 0.25.
- Final-Test cohort: 128 episodes, seed 20260813, frozen in
  `formal/FINAL_TEST_COHORT_AUTHORITY_V1.json`.
- Frozen registries live in `registries/` (v2_scientific_freeze.json,
  v2_scientific_freeze_r2.json, v2_stage2_solver_authority_reconciliation.json)
  and must never be rewritten.

## Layout

- `model/` — scientific implementations (PRE/M1/M2/M3/M4 + common).
- `exp/` — experiment drivers and the layers they build on:
  `exp/jatm_section4` (M1 history-capacity), `exp/jatm_section5`
  (Section-5 development layer), `exp/shared` (reusable analysis helpers:
  forecast/rank metrics, protocol constants, priority population and bootstrap,
  similar-delay, informativeness, perturbation views, screening triage),
  `exp/inputs` (the preserved data-input chain: cache -> canonical -> PRE ->
  typed model inputs). The V1 Exp1-Exp4 drivers were retired on 2026-10-21 and
  survive only in Git history.
- `formal/v2_phase7/` — sealed Final-Test runner (read-only projections; the
  executor never recomputes science from raw data).
- `validation/` — validation gates and materialization scripts.
- `artifacts/` — three classes: alpha (byte-stable canonical results),
  beta (authorized deterministic diagnostic re-runs), gamma (supplementary
  analyses, e.g. `paper_results_v2_final_test_rmb/stage_q_sensitivity/`).
  Sealed Final-Test epochs live under `artifacts/experiment/final_test_v2*`;
  checkpoints are local-only (gitignored) and hash-validated.
- `data1/`, `data2/` — read-only raw data (gitignored). Never write into them.
  `data1/` is not present in this checkout; the V2 chain reads `data2/` only,
  and the `data1_2019` adapter contract in `registries/` is retained on purpose.
  Tests that need those raw files skip themselves.

## Running things

- Fast model tests:
  `python -m pytest -q tests/pre tests/m1 tests/m2 tests/m3 tests/m4 tests/contract tests/integration`
- Full suite incl. phase7 gates: `python -m pytest -q tests`
  (run from the repository root; several tests read committed artifacts).
- Validation CLIs: `python -m validation.<module>` with the module's own
  `--help`. Final-Test / paper experiments are only re-run by explicit
  human authorization.
- Sparse shells: `torch._dynamo` needs `getpass.getuser()`, which on Windows
  falls back to the (POSIX-only) `pwd` module when `USERNAME`/`USER`/`LOGNAME`
  are unset. Without them the first optimizer construction raises inside
  `torch._dynamo` import and a retry then fails with
  `Artifact of type=precompile already registered in mega-cache artifact
  factory`. Set `USERNAME` (any value) before running the M1 suites from a
  stripped environment; the tests themselves are fine.

## Rules for agents

1. Never `git push --force`, never rewrite history, never `git branch -D`
   or delete remote branches.
2. Never touch files under `artifacts/experiment/final_test_v2*` or the
   frozen registries unless a human explicitly authorizes a documented
   regeneration.
3. Line endings: the repository stores LF (`* text=auto` + `eol=lf`). Use
   canonical-LF hashing (`canonical_text_file_hash` in
   `validation/v2_phase6/common.py` and `validation/v2_phase6_r2/common.py`)
   when comparing text artifacts; do not mass-rewrite line endings.
4. When quoting byte literals in scripts, remember `bytes((10))` is ten NUL
   bytes; `bytes((10,))` is a single LF.
5. New experiments must record input hashes, git head, and
   `model_retrained=false`-style flags in their manifest, per the existing
   Stage-q manifest convention.
6. When in doubt about any scientific authority, stop and ask; do not guess.
