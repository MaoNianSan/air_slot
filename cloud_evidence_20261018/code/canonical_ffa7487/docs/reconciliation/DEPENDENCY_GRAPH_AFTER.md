# Dependency Graph After Reconciliation

Current repository HEAD: `8aa01f9866d12fd7cdf01148087db7e5fb688b8b` (worktree changes are uncommitted).

## Intended direction

```text
raw sources
    |
    v
PRE adapters -> canonical/source-family normalizers -> PREState
    |
    v
M1 typed history/targets -> AlignedScenario
    |
    v
M2 native quantities -> ScenarioConsequence

PREState + AlignedScenario + ScenarioConsequence + M3 CandidateAction
    |
    v
M4DecisionRequest -> eligibility -> post-action -> residual risk -> lanes -> ranking

frozen model/artifacts -> exp cohorts/variants/metrics/promotion
typed model contracts -> validation compile/adapter/bounded smoke checks
```

## Boundary checks

| Boundary | Result | Evidence |
| --- | --- | --- |
| `model/M1-M4` importing raw adapters/readers | PASS | `tests/static/test_dependency_boundaries.py`; foundation fixture-only scan |
| `model` importing `exp`, reporting, or validation | PASS | dependency scanner |
| `M3 -> M1/M2 current episode implementation` | PASS | dependency scanner and public facade imports |
| validation importing model contracts only | PASS | foundation scan |
| Exp variants mutating formal artifacts | PASS | `BaseRunner.run_from_frozen_artifacts`, Exp1-3 copy tests |
| circular imports | PASS (0 cycles) | AST import graph scan on `model`, `exp`, `validation` |

Cross-module calls now use public typed facades: `PRE.build_pre_state`,
`M1.M1Service`/`M1Pipeline`, `M2.map_pre_action_consequence`,
`M3.instantiate_candidates`, and `M4.evaluate_decision`.

## Known non-blocking items

The scanner still marks a handful of 300-440 LOC validation/reference modules as
`REFACTOR_RECOMMENDED` because they combine I/O and reporting. None is over the
800-line required gate, and the P0 validation scripts already delegate shared
loading and artifact I/O to `validation/support` and `validation/scenarios`.
