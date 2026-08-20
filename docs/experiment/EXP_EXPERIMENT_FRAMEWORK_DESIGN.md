# Experiment Framework Design

Design ID: `AIR_SLOT_EXPERIMENT_COMMON_INFRASTRUCTURE_V1`  
Repository baseline: `8f2987294ad2b0b238e01da748243ed8d0bd9bb2`  
Scope: common experiment interfaces only; no Exp1-Exp4 implementation and no scientific execution.

## 1. Experiment architecture

The common framework follows one directional flow:

```text
Data
  -> Scenario preparation
  -> Variant transformation
  -> Decision-chain execution
  -> Evaluation
  -> Result storage
```

The stages have the following responsibilities:

| Stage | Common-layer responsibility | Experiment-specific responsibility |
| --- | --- | --- |
| Data | carry dataset identity and provenance | select an authorized cohort |
| Scenario preparation | preserve scenario/artifact identity | choose which frozen input artifact is used |
| Variant transformation | register a declarative variant contract | implement the declared Exp1-Exp4 transformation later |
| Decision-chain execution | sequence protocol hooks | call the frozen PRE -> M1 -> M2 -> M3 -> M4 interfaces later |
| Evaluation | register metric definitions by level | supply scientifically approved metric implementations later |
| Result storage | validate and serialize provenance-complete results | select approved output destinations later |

The common infrastructure does not load raw datasets, train a model, construct a scientific variant, invoke the model chain, or calculate a paper metric. It provides contracts into which later experiment implementations can plug.

## 2. Separation principle

The experiment layer may:

- change declared information availability;
- change declared representation resolution;
- change declared replay timing;
- change the evaluation setting;
- compare variants under fixed model and artifact identities;
- store support-aware metrics and provenance.

The experiment layer may not:

- modify model parameters or calibration artifacts;
- bypass PRE, M1, M2, M3, or M4 contracts;
- inject unsupported or future information;
- create a new scientific assumption, proxy, cost, response, or ranking rule;
- convert unavailable support to zero;
- relabel conditional/test outputs as authoritative results.

## 3. Common modules

```text
exp/common/
  protocol.py       abstract prepare/run/evaluate/report lifecycle
  registry.py       declarative variant metadata and consistency checks
  runner.py         protocol sequencing; legacy BaseRunner remains unchanged
  result_schema.py  provenance-complete result and metric schemas
  evaluator.py      metric-level registry; no built-in calculations
  reporting.py      JSON, CSV, and summary-table serialization
```

No module contains an Exp1, Exp2, Exp3, or Exp4 branch. Experiment identity is data carried by contracts and registry entries, never a dispatch `if/else` in common code.

## 4. Result contract

Each `ExperimentResult` records:

- experiment, variant, dataset, seed, and UTC timestamp;
- model and artifact version maps;
- scenario and configuration hashes;
- typed metric observations;
- overall support status;
- structured provenance.

Metric observations separately record state/decision/system level, value, unit, support status, and metadata. Execution success and scientific support are not conflated.

## 5. Variant registry contract

`VariantRegistry` stores only declarative `VariantDefinition` records:

- `variant_id`;
- `description`;
- `changed_factor`;
- `fixed_factor`;
- `allowed_metrics`;
- `claim_scope`.

The registry rejects duplicates and self-contradictory changed/fixed factors. It does not implement transformations. Future entries such as `EXP1_FULL`, `EXP2_JOINT`, or `EXP3_ROLLING` use the same generic API.

## 6. Protocol and runner contract

`ExperimentProtocol` defines four abstract hooks:

1. `prepare()`;
2. `run()`;
3. `evaluate()`;
4. `report()`.

`ExperimentRunner` only sequences these hooks and verifies that `report()` returns the common `ExperimentResult`. The framework does not supply a concrete protocol in this phase.

## 7. Evaluation contract

`EvaluationSuite` registers metric specifications at exactly one level:

- `STATE`: for future calibration, CRPS, and predictive coverage metrics;
- `DECISION`: for future action disagreement, ranking change, and risk difference metrics;
- `SYSTEM`: for future runtime and latency metrics.

Metric declarations contain no formula. A callable may be attached by a later approved experiment implementation. Calling an undeclared or unimplemented metric fails explicitly.

## 8. Reporting contract

`ExperimentReporter` writes:

- canonical JSON results;
- a metric-level CSV table;
- a Markdown summary table.

Every row contains experiment ID, variant ID, scenario/config hashes, serialized artifact lineage, and support status. Existing paths are not overwritten unless explicitly requested.

## 9. Compatibility boundary

The old `BaseRunner` and `exp.common.contracts.ExperimentResult` remain unchanged for existing tests and historical behavior. New code imports `exp.common.result_schema.ExperimentResult`. Later Exp1-Exp4 migration must be explicit; there is no silent compatibility adapter.

## 10. Validation boundary

Phase-1 tests cover schema serialization, registry consistency, abstract protocol enforcement, metric registration, reporter lineage, and runner sequencing on in-memory fixtures. They do not execute PRE-M4, access datasets, produce scientific metrics, or read Final Test.
