# Dependency Map

Phase 0 read-only map of the current implementation.

## Scientific chain

```text
raw data
  -> model/PRE/adapters and PRE canonical/episode/evidence/reference/realized
  -> typed PREState
  -> model/M1 (history, targets, aligned scenarios)
  -> model/M2 (structured consequence ontology and valuation)
  -> model/M4 (formal lanes, risk, ranking)
```

M3 is a frozen episode-independent action/response catalog instantiated from
typed PRE facts and consumed jointly by M4. It is not an episode-level learner
between M2 and M4.

## Current package ownership

| Package | Owns | May consume | Must not consume |
| --- | --- | --- | --- |
| `model/PRE` | adapters, canonicalization, episode construction, evidence, support, references, realized/posthoc routing, typed PRE state | raw sources, registries, common contracts | M1-M4 or `exp` |
| `model/M1` | admissible history, probabilistic targets, rolling state, aligned scenarios | typed PRE state, common contracts | raw adapters, raw files, `exp`, reporting |
| `model/M2` | scenario consequence ontology, native quantities, valuation, formal estimand | M1 scenarios, typed PRE references, common ontology | raw data, `exp` |
| `model/M3` | frozen atomic action catalog, response provenance, coverage, instantiation | registries, typed PRE facts, common ontology | episode readers, M2 scenario learners, `exp` |
| `model/M4` | identity gates, formal lanes, residual risk, authoritative ranking | PRE state, M1 scenarios, M2 consequences, M3 candidates | raw data, evaluation-only logic |
| `exp` | evaluation cohorts, contrasts, paired metrics, sensitivity, bootstrap, promotion | frozen model artifacts and typed contracts | mutation of formal artifacts |
| `validation` | compile/schema/dependency/bounded smoke/reference audits | model contracts and fixtures | paper-result claims |

## Audit findings

1. Python import scanning currently blocks model-to-exp, PRE-to-downstream,
   M3-to-M2, but does not yet cover raw adapter imports in M1-M4 or model-to-
   reporting/evaluation imports.
2. `model/M1/target_builder.py` exposes a `build_data2_target_labels` API and
   checks `dataset_instance_id == data2_2019`; this is a scientific boundary
   violation even though it is not an import-cycle violation.
3. Validation scripts are intentionally data2-specific and remain outside the
   formal model boundary; they must not be imported by model packages.
4. `exp/common/runner.py` is a development shell that reuses an input `metric`
   rather than constructing variant-specific outputs from frozen artifacts.

## Required dependency gates

The reconciled scanner must enforce:

```text
model/M1-M4 cannot import model.PRE.adapters or raw readers
model/M2-M4 cannot import raw data packages
model/M4 cannot import exp or reporting
model/* cannot import exp/* or exp.reporting
model/* cannot import validation/*
exp/* may import model/*
validation/* may import model/*
reporting/* may consume exp artifacts only
```
