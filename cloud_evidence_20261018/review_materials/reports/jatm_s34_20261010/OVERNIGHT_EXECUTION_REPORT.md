# Overnight Execution Report — 2026-10-11

## Status

`OVERNIGHT_PARTIAL_BLOCKED`

Implementation and Development execution progressed on `v2/paper-primary`.
G0 remains partially blocked only where the current scientific contract still
needs exact full-chain integration or claim-level lineage reconciliation. No
Test, Final-Test, held-out tuning, or sealed artifact rewrite was performed.

## Authority and Git

- Repository: `D:\research\air_slot\code\explore`
- Branch: `v2/paper-primary`
- Current HEAD: `35ff68e`
- Pushed commits: `3f27f6e` (G0/D4/exact Marginal), `6e49223` (E1 runner), and `35ff68e` (E4 preflight).
- Existing untracked `figures/` and generated versioned Development directories
  were not staged.
- `FINAL_TEST_ACCESS_COUNT` remained `0`.

## G0 closure progress

- **G0-2:** exact weighted Marginal adapter and 11-node real checkpoint pilot
  pass. Full E2/E3 objective integration remains blocked until the adapter is
  wired into the Stage-II objective path.
- **G0-3:** three real PRE/TURN/TAXI traces pass static unit, time-cutoff,
  `D_TO = D_OB + D_TX`, and CU/priority/u semantic checks. TAXI has a typed
  unavailable-`u` limit in the selected checkpoint; broad raw-to-primitive
  closure remains open.
- **G0-5:** year-replicated PRE reference lineage bug fixed. 2017 H1 R2
  FIXED_COMMON bundle passes identity, fit-window, payload-hash, manifest-hash,
  positive-support, and seven-unit checks. Paper claim-level reconciliation is
  still partial.

Evidence: [G0 manifest](D:/Local_Projects/airslot/reports/jatm_s34_20261010/g0/g0_manifest.json),
[D4 audit](D:/Local_Projects/airslot/reports/jatm_s34_20261010/g0/D4_FIXED_COMMON_AUDIT_R2.json),
[unit trace](D:/Local_Projects/airslot/reports/jatm_s34_20261010/g0/G0_UNIT_TRACE_V2.json).

## Development experiments

### E1 — screening information gain

`DEVELOPMENT_COMPLETE` on 1,769 real Development nodes (PRE 48, TURN 121;
TURN eligible 120). Delay, Delay+Passenger Exposure,
Delay+Downstream Exposure, and Consequence were evaluated on the same cohort,
q grid, support rule, and M3 selector. The run includes 2,000 episode-cluster
bootstrap replicates and writes per-node selections and summary rows.

Artifact: `artifacts/experiment/jatm_s34/e1_development_v1/E1_SUMMARY.json`.

At q=0.10 against the consequence shortlist, Passenger Exposure retained
0.963 of TURN consequence value with 3 replacements; Delay and Downstream
Exposure retained 0.929 with 4 replacements. PRE retained values were 1.0 for
Passenger Exposure and 0.800 for Delay/Downstream. These are Development
results and are not held-out claims.

### E2 — decision layer and representations

The existing Section 5 Development runner completed again over 1,769 nodes,
with Stage-I/Stage-II/M4 outputs and 2,000 bootstrap settings:
`artifacts/experiment/jatm_section5/development/report/JATM_SECTION5_MANIFEST.json`.
Its current HISTORY_MARGINAL path still uses the legacy permutation
representation, so this run is retained as an engineering baseline and is not
reported as exact weighted Marginal E2 evidence.

### E3 — objective × distribution

The independent exact weighted Marginal pilot passed on 11 real checkpoint
nodes, with no blocked nodes and maximum product size 4,131:
`runs/e3_exact_marginal_pilot_r1.json`. Full weight-family objective,
Threshold/Headroom ablation, and Joint-reference evaluation remain
`SCIENTIFIC_BLOCKED` until the Stage-II integration contract is implemented.

### E4 — six-year chain

The six existing year manifests (2017–2022) are all
`PRE_DEVELOPMENT_READY` with Train=128, Calibration=64, Development=128 and
Test=0. The updated matrix is
[RUN_MATRIX_R1.csv](D:/Local_Projects/airslot/reports/jatm_s34_20261010/runs/RUN_MATRIX_R1.csv).
No Test rows were read or executed. The rebuilt 2017 H1 FIXED_COMMON bundle is
ready for a versioned annual Development runner. E4 preflight reports only 2019 and 2020 have existing YEAR_LOCAL M2 bundles; 2017, 2018, 2021 and 2022 need versioned reference materialization before full annual M1–M4 Development. Annual Test remains gated.

## Validation

- Exact Marginal, E1, G0 unit trace, and contract tests: **7 passed**.
- E1 smoke: **DEVELOPMENT_COMPLETE**, 40 real nodes, 20 bootstrap replicates.
- Full E1: **DEVELOPMENT_COMPLETE**, 1,769 real nodes, 2,000 bootstrap replicates.
- Section 5 Development rerun: **COMPLETE**, 1,769 nodes.
- E4 preflight: **ENGINEERING_INCOMPLETE**, six PRE manifests valid; 2/6 YEAR_LOCAL M2 bundles present; FIXED_COMMON 2017 H1 audit ready.
- Sealed robustness/domain replay after clean commit: **38 passed**.
- D4 audit: **PASS_FIXED_COMMON_REBUILT**.
- `git diff --check` and targeted `py_compile`: passed.

## Remaining blockers and next executable work

1. Wire `ExactWeightedMarginalDistribution` into an independent E2/E3
   Stage-II objective runner with lazy exact evaluation and separate C0–C3
   denominators.
2. Build the six-year annual Development runner that binds YEAR_LOCAL and the
   audited 2017 H1 FIXED_COMMON reference without touching Test.
3. Complete raw-to-primitive G0-3 closure for the TAXI actionable `u` case and
   reconcile paper-facing lineage claims.
4. Keep all six Test runs blocked until explicit access authorization; use new
   versioned output roots when authorized.
