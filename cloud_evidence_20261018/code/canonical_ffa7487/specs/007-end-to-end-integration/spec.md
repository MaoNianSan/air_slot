# Feature Specification: End-to-End First-Version Integration

Provide one project CLI and a deterministic runtime that connects the implemented PRE, M1, M2, M3/M4, and experiment/reporting components. The runtime shall load the scientific, reproducibility, and engineering configuration layers; emit progress and immutable run manifests; support bounded parallel execution and strict resume; expose cleanup only for project-owned derived artifacts; and validate output contracts.

Required executable paths are: synthetic PRE-to-M4 smoke, bounded read-only data1/data2 smoke, experiment smoke, artifact validation, and a batch executor. Synthetic or smoke outputs must remain `paper_result=false`. Missing model artifacts, unsupported evidence, incomplete M2 components, incompatible resume state, absent raw roots, and invalid configuration must produce typed explicit failures.

The feature must not write beneath raw data roots, infer a virtual environment identity, invoke an LLM, run full experiments, or claim scientific validation.

## Acceptance criteria

- `python -m airslot validate` validates configuration, registries, runtime, and dependency boundaries.
- `python -m airslot smoke-synthetic` writes a traceable PRE -> M1 -> M2 -> M3 -> M4 bundle.
- `python -m airslot smoke-real` performs bounded reads from both raw roots without modifying them.
- Deterministic manifests and strict resume reject mismatched inputs/configuration.
- Parallel results preserve declared task order; progress is machine-readable.
- Cleanup cannot target the project root, either raw root, or paths outside approved derived-output roots.
- Artifact validation rejects paper claims from fixture/smoke outputs and detects missing lineage/manifests.

