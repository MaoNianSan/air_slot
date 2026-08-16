# Experiment boundary

`exp/common/contracts.py::ExperimentCrossContract` is the V5 source of truth for split, statistical
units, bootstrap, rolling grid, lead times, risk policy, scenario scales, and RNG stream names.
Formal experiment modes are `smoke`, `development`, `paper_full`, and `numerical_stress`; M1 `FAST`
remains a computational path only.

Exp1 changes history representation, Exp2 changes uncertainty representation, Exp3 changes one
decision-support contract rule at a time, and Exp4 owns sensitivity, portability, and deployability.
All evaluation artifacts reference an immutable formal hash. Publication code reads artifacts and
does not rerun PRE-M4.

`paper_full` is guarded by explicit approval and the generated
`EXPERIMENT_CROSS_CONTRACT_STATUS.json`. Smoke/foundation validation is not an experiment or a paper
result.
