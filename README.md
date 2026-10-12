# Air Slot

Air Slot is an evidence-aware airline-recovery research implementation. Its
current scientific chain is:

```text
raw data (read only) -> PRE -> M1 -> M2 -> M3 -> M4
```

- `model/PRE/` owns decision-time admissibility, typed publication, evidence,
  and lineage.
- `model/M1/` models unresolved operational state.
- `model/M2/` maps state scenarios to the seven-component consequence ontology.
- `model/M3/` owns atomic action, factual-eligibility, and response contracts.
- `model/M4/` owns monetary mapping, residual-risk evaluation, and labelled
  ranking. Ranking is not an operational recommendation.
- `registries/` contains versioned source and scientific contracts.
- `validation/` contains bounded model/scientific checks.
- `artifacts/diagnostics/` contains justified model diagnostics; it is not a
  paper-results pipeline.

`data1/` and `data2/` are independent, read-only data environments. Raw schema
differences stop at PRE. Model code must not create caches, indexes, temporary
files, or documentation inside either data root.

The old Exp1-Exp4 implementation and old Section 5 paper-result pipeline are
retired as primary authorities; they remain under `exp/exp1..exp4` and
`artifacts/experiment/final_test/` as historical development evidence only.

Current experiment and reporting layers:

- `exp/jatm_section4/` — M1 history-encoder capacity selection (H8/H16/H32;
  H16 is the frozen primary).
- `exp/jatm_section5/` — hash-locked Section-5 development layer
  (attention/recovery/information/robustness).
- `formal/v2_phase7/` — the sealed, audited Final-Test runner and read-only
  paper-facing projections (epoch evidence under
  `artifacts/experiment/final_test_v2_stage_matched_canonical_v2/`).
- `artifacts/paper_results_v2_final_test_rmb/stage_q_sensitivity/` — the
  Stage x screening-capacity (q) supplementary analysis.

Stage-II solver authority: exact enumeration is the production path;
Pyomo+HiGHS is parity-only (see `REPOSITORY_AUTHORITY.md`).

Authoritative current documentation:

- [Repository authority](REPOSITORY_AUTHORITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data and evidence boundary](docs/DATA_AND_EVIDENCE_BOUNDARY.md)
- [Action and decision contract](docs/ACTION_DECISION_CONTRACT.md)
- [Model validation](docs/MODEL_VALIDATION.md)

Use the current Python 3.11 environment directly. Run model tests with
`python -m pytest -q tests/pre tests/m1 tests/m2 tests/m3 tests/m4 tests/contract tests/integration`.
No Final Test or paper experiment is authorized by this command.
