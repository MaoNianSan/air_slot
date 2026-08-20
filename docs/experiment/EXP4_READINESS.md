# Exp4 Readiness

Scientific contract: evaluate prediction, validation, dataset portability, and runtime of the complete decision chain.

## Capability matrix

| Area | Existing components | Gap | Status |
| --- | --- | --- | --- |
| Prediction evaluation | M1 NLL/accuracy helper; calibration policy/diagnostics; CRPS and interval coverage in a quick validation script | no experiment-owned CRPS/Brier/calibration/coverage evaluator on current V2 scenarios | `PARTIAL` |
| Validation evaluation | episode-safe split, bootstrap, final-test immutability guard | no integrated validation evaluator or support-aware chain metrics | `PARTIAL` |
| Dataset portability | Data1/Data2 roles; support transition metrics; silent-substitution and schema-localization gates | historical Exp4 only records a static registry gate and does not execute a typed Data1 chain | `PARTIAL` |
| Runtime evaluation | latency p50/p95/p99 and a 300-second p95 gate; several local timers | no standardized stage timing, warm/cold definition, hardware/environment provenance, or paired end-to-end runner | `PARTIAL` |
| Reporting | generic tables/figures with metadata | schema is too generic to guarantee metric/support/model provenance | `PARTIAL` |

## Reusable components

- `exp/exp4/portability.py` support transitions and hard gates;
- `exp/exp4/metrics.py::latency_percentiles` as a small statistical helper;
- episode-safe splits, episode bootstrap, artifact hashes, write-once evaluation output, and table/figure generation;
- model-local M1 calibration diagnostics, provided they are exported through an experiment-owned metric artifact rather than read as an undocumented dictionary.

## Components requiring replacement

- `Exp4Runner` is variant metadata only and accepts precomputed scalar metrics.
- old response/lambda/alpha sensitivity variants answer the former Exp4 question, not the new four-part adequacy audit.
- `exp/exp234/development_execution.py::exp4_development` uses legacy M3 response and reports deployability as `NOT_RUN`; it is not a runtime evaluator.
- quick CRPS diagnostics use historical scenario semantics and live under `validation/`, so their formula may be ported but their results may not.

## Required evidence boundaries

- Data1 is a portability environment, not pooled training evidence and not a substitute for Data2.
- Prediction metrics may be computed where M1 targets are supported; unsupported targets must have explicit denominators.
- Decision and risk validation must retain M3 response support and M4 ranking authority.
- A test-only monetary mapping can validate engineering behavior but cannot support a real-money or authoritative decision claim.
- Final Test remains inaccessible until the separate approval gate is satisfied.

## Tests required

- metric fixture tests for CRPS, Brier, calibration and predictive coverage;
- episode-cluster aggregation and denominator tests;
- typed Data1/Data2 role and no-silent-substitution tests;
- stage timer accounting and monotonic end-to-end timing tests;
- warm/cold and state-aware/fast path labels are never conflated;
- reporting round-trip preserves source hashes, model versions, seeds, metric definitions and support states;
- blocked M3/M4 outputs remain blocked in validation summaries.

`EXP4_STATUS = PARTIAL_COMPONENTS_REWRITE_REQUIRED`
