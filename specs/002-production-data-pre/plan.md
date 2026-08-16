# Implementation Plan: Production Data and PRE

## Summary

Extend the 001 contracts into read-only production adapters, canonical Parquet caches, real episode construction, rolling admissibility, complete evidence/lineage publication, and deterministic resume manifests. Bounded real smoke is required; full-year execution is deferred to local debugging.

## Technical Context

- Python 3.11.x current interpreter; no virtual environment.
- pandas/pyarrow for bounded CSV/Parquet streams; standard tarfile/gzip/zipfile for archives; zoneinfo for timezone conversion; pydantic/PyYAML for contracts.
- Windows/Linux paths via pathlib; CPU/GPU has no effect on PRE semantics.
- Raw roots are configured external read-only inputs; all cache/metadata/output is project-owned.

## Constitution Check

PASS: evidence before computation, independent dataset instances, formal/evaluation separation, raw immutability, deterministic lineage, explicit abstention, and no Git side effects are direct design invariants.

## Project Structure

```text
model/PRE/
  adapters/{base,data1,data2,readers,validation}.py
  canonical/{normalization,timezone,units,storage}.py
  episode/{membership,builder,node_builder}.py
  evidence/{admissibility,support,publication}.py
  cache/{manifest,resume}.py
  pipeline.py
registries/source_adapter_registry.yaml
metadata/datasets/{data1,data2}/dataset_profile.yaml
validation/pre_production.py
tests/{contract,unit,integration,real_smoke}/
```

## Design Gates

- Unknown scientific parameters are typed blockers, not defaults.
- Post-hoc actual fields are emitted only as realized/train/evaluation objects.
- No dataset-name condition occurs after adapter output/capability selection.
- Cache identity covers source metadata, registry, scientific config, canonical schema, and code contract version.

## Delivery Phases

1. Source registry and read requests.
2. Streaming raw readers and canonical conversions.
3. Episode and rolling evidence construction.
4. Project-owned storage, resume, and manifests.
5. Synthetic and bounded real smoke, validation, and unresolved-issue report.
