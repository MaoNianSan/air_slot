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
retired. There is no active `exp/` package, and the future experiment suite has
not yet been redesigned. No model import or execution path may depend on an old
experiment output.

Authoritative current documentation:

- [Architecture](docs/ARCHITECTURE.md)
- [Data and evidence boundary](docs/DATA_AND_EVIDENCE_BOUNDARY.md)
- [Action and decision contract](docs/ACTION_DECISION_CONTRACT.md)
- [Model validation](docs/MODEL_VALIDATION.md)

Use the current Python 3.11 environment directly. Run model tests with
`python -m pytest -q tests/pre tests/m1 tests/m2 tests/m3 tests/m4 tests/contract tests/integration`.
No Final Test or paper experiment is authorized by this command.
