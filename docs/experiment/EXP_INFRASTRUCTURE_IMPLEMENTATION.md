# Experiment Common Infrastructure Implementation

Implementation ID: `AIR_SLOT_EXPERIMENT_COMMON_INFRASTRUCTURE_V1`  
Baseline HEAD: `8f2987294ad2b0b238e01da748243ed8d0bd9bb2`  
Scope status: common infrastructure implemented; Exp1-Exp4 not implemented.

## Created files

| File | Interface | Purpose |
| --- | --- | --- |
| `exp/common/protocol.py` | `ExperimentProtocol` | abstract `prepare/run/evaluate/report` lifecycle |
| `exp/common/registry.py` | `VariantDefinition`, `VariantRegistry` | declarative variant metadata and consistency checks |
| `exp/common/result_schema.py` | `ExperimentResult`, `MetricObservation`, `MetricLevel`, `SupportStatus` | shared provenance-complete result envelope |
| `exp/common/evaluator.py` | `MetricDefinition`, `EvaluationSuite`, `default_evaluation_suite` | state/decision/system metric registration without formulas |
| `exp/common/reporting.py` | `ExperimentReporter` | JSON, metric CSV, and Markdown summary output |
| `docs/experiment/EXP_EXPERIMENT_FRAMEWORK_DESIGN.md` | design contract | architecture and separation rules written before code |
| `tests/experiments/conftest.py` | fixture | in-memory, NOT_RUN result fixture |
| `tests/experiments/test_result_schema.py` | tests | serialization, hash, timestamp and schema guards |
| `tests/experiments/test_variant_registry.py` | tests | registry consistency and required example IDs |
| `tests/experiments/test_protocol.py` | tests | abstract lifecycle and common runner sequencing |
| `tests/experiments/test_evaluator.py` | tests | metric levels, declaration-only defaults and typed registration |
| `tests/experiments/test_reporting.py` | tests | JSON/CSV/summary lineage preservation and overwrite guard |

## Modified files

| File | Change | Compatibility |
| --- | --- | --- |
| `exp/common/runner.py` | appended `ExperimentRunner`, which sequences an `ExperimentProtocol` and requires the new common result type | existing `BaseRunner` implementation and behavior unchanged |

No file under `model/`, PRE, M1, M2, M3, M4, TeX, or an existing Exp1-Exp4 package was modified.

## Interface behavior

### Result schema

`exp.common.result_schema.ExperimentResult` requires:

- `experiment_id`, `variant_id`, `dataset_id`, `seed`, and timezone-aware `timestamp`;
- explicit `model_versions` and `artifact_versions` maps;
- SHA-256 `scenario_hash` and `config_hash`;
- typed metric observations;
- overall `support_status` and structured `provenance`.

Metric dictionary keys must match the embedded metric IDs. Numeric metric values must be finite. Each result exposes a deterministic content hash.

### Variant registry

The registry has no transformation functions and no experiment switch statement. A future package registers declarative definitions and then validates that every allowed metric is present in an `EvaluationSuite`. Tests demonstrate the requested IDs:

- `EXP1_FULL`, `EXP1_NO_DIRECT_REUSE`;
- `EXP2_COLLAPSED`, `EXP2_MARGINAL`, `EXP2_JOINT`;
- `EXP3_ONE_SHOT`, `EXP3_ROLLING`.

The definitions are test fixtures, not active variants.

### Protocol and runner

A future concrete protocol implements:

```text
prepare(context)
  -> run(prepared)
  -> evaluate(execution)
  -> report(evaluation) -> ExperimentResult
```

The common runner only sequences those methods. It does not load data, transform a variant, execute PRE-M4, or calculate a metric.

### Evaluation suite

The default suite declares interfaces for:

- state: calibration, CRPS, coverage;
- decision: action disagreement, ranking change, risk difference;
- system: runtime, latency.

No formula is attached. Evaluation fails explicitly with `METRIC_IMPLEMENTATION_NOT_REGISTERED` until a later authorized experiment supplies a typed callable.

### Reporter

The reporter writes `result.json`, `metrics.csv`, and `summary.md`. JSON and every tabular row retain experiment ID, variant ID, scenario/config hashes, artifact lineage, model versions, support status, provenance, and result hash. Existing files are not overwritten by default.

## Future Exp1-Exp4 usage

- Exp1 will register information-pathway/history definitions and implement them outside `exp/common`.
- Exp2 will register representation/resolution definitions and reuse one scenario hash across variants.
- Exp3 will register decision-loop/replay-timing definitions and preserve cutoff provenance.
- Exp4 will attach approved state, decision, and system metric implementations.

All future protocols must use the frozen model interfaces and must preserve blocked/unsupported states. Common infrastructure readiness does not close any scientific gate.

## Validation

Commands run:

```text
python -m compileall -q exp/common tests/experiments
python -m pytest -q tests/experiments tests/contract/test_experiment_v5_contract.py tests/integration/test_reconciliation_contracts.py tests/static
```

Result:

```text
104 passed in 8.70s
```

No experiment execution, dataset access, Final Test access, parameter choice, scientific result, or paper output occurred.

## Status

`MODEL_MODIFICATION = NO`  
`EXP_IMPLEMENTATION_STATUS = NOT_IMPLEMENTED`  
`READY_FOR_EXP1_4 = YES` (ready to begin separately authorized implementations only)  
`FINAL_STATUS = COMMON_INFRASTRUCTURE_READY_EXPERIMENTS_NOT_IMPLEMENTED`
