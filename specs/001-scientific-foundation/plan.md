# Implementation Plan: Executable Scientific Foundation

**Branch**: `none (non-Git workspace)` | **Date**: 2026-08-12 | **Spec**: [spec.md](spec.md)

**Input**: Approved feature specification in `specs/001-scientific-foundation/spec.md`

## Summary

Create the clean executable foundation for Air Slot without implementing any M1-M4 algorithm. The
milestone establishes package boundaries, machine-readable evidence and lineage contracts, independent
data1/data2 adapter interfaces, a support-aware PRE skeleton, deterministic validation, and explicit
downstream placeholder contracts. All work is local to this new workspace; authoritative documents and
raw data remain read-only, and no Git or experiment operation is included.

The implementation proceeds contract-first. Pydantic models define runtime validation and canonical
serialization; YAML registries define scientific permissions and support ceilings; adapter interfaces
translate small fixtures or configured read-only sources into canonical records; PRE constructs
immutable decision-node states using membership and time admissibility. Unsupported or unresolved
objects are represented as typed states with no fabricated scientific value.

## Technical Context

**Language/Version**: Python 3.11.x using the current system/current interpreter directly. The project
does not create, activate, identify, or depend on a virtual or Conda-style environment.

**Primary Dependencies**: Pydantic 2.x for validated contracts and deterministic serialization;
PyYAML for registries/configuration; pytest for tests. pandas and pyarrow are admitted only at the
adapter/canonical-storage boundary when a later task requires fixture-level tabular interchange.
Scientific algorithm packages (`torch`, `scipy`, `scikit-learn`) are not needed for this milestone.
All project dependencies are declared only in `requirements.txt` and installed through the current
interpreter with `python -m pip install -r requirements.txt`; no environment activation exists.

**Storage**: Versioned YAML for registries/configuration; canonical JSON for validation artifacts and
identity hashing; optional fixture CSV/JSON. Apache Parquet/ZSTD remains the frozen future canonical
cache format but no full-data cache is produced in this feature.

**Testing**: pytest unit, contract, integration, and static dependency tests using synthetic fixtures;
offline, CPU-only, deterministic, and independent of full raw datasets.

**Target Platform**: Windows 10/11 and Linux x86_64 with identical scientific semantics; filesystem
access through `pathlib.Path`; UTF-8 text and UTC timestamps.

**Project Type**: Scientific Python library plus validation CLI. There is no web service, database,
notebook runtime, or model-training service in this milestone.

**Performance Goals**: Foundation validation completes in under 60 seconds on a CPU-only development
machine; registry loading and fixture PRE construction remain small-memory and do not scan full data.

**Constraints**: Clean implementation; no legacy compatibility; raw data read-only; no hard-coded local
paths; no data1/data2 row pooling; no silent fallback; no algorithmic M1-M4 behavior; no experiment,
paper-promotion, Git, or GitHub side effects; development-frozen values remain unresolved and visible.
No `.venv`, `venv`, virtualenv, Conda, Poetry, or Pipenv environment may be created, required, assumed,
activated, bootstrapped, or used as an identity. Runtime records are limited to Python version, package
versions, platform, and device.

**Scale/Scope**: Two independent dataset profiles; five principal canonical source-object families plus
static airport references; seven PRE artifact families; initial curated rule/variable registries based
on the supplied audit; fixture-only executable validation; placeholder boundaries for M1-M4 and exp1-4.

## Constitution Check

_GATE: Evaluated before Phase 0 and re-evaluated after Phase 1 design._

| Gate | Pre-design | Design evidence |
| --- | --- | --- |
| Evidence before computation | PASS | Adapter and PRE contracts require availability, membership, provenance, support ceiling, and explicit unsupported states. |
| Frozen scientific boundaries | PASS | M1-M4 are placeholders only; M3 consumes PRE plus frozen registry, while M4 later joins M1/M2/M3. |
| Independent dataset instances | PASS | Dataset instance identity is mandatory and cross-dataset pooling/overlay defaults are prohibited. |
| Formal/evaluation isolation | PASS | Contract types and output namespaces separate formal, evaluation-only, and realized-outcome objects. |
| Reproducibility and auditability | PASS | Canonical JSON, content hashes, versioned registries, deterministic tie handling, and validation manifests are specified. |
| Simplicity and honest abstention | PASS | Minimal foundation dependencies; unsupported/development-frozen objects cannot acquire values or formal eligibility. |
| Authorized side effects | PASS | Plan produces local design/source artifacts only; no raw-data mutation, experiment, Git, or publication action. |

No constitution violation requires a complexity exception.

## Project Structure

### Documentation (this feature)

```text
specs/001-scientific-foundation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── README.md
│   ├── adapter-protocol.md
│   ├── pre-foundation.md
│   ├── registry-schemas.md
│   ├── downstream-boundaries.md
│   └── validation-cli.md
└── tasks.md                    # Created only after plan review approval
```

### Source Code (repository root; prospective implementation layout)

```text
model/
├── common/
│   ├── enums.py
│   ├── identity.py
│   ├── serialization.py
│   └── errors.py
├── PRE/
│   ├── adapters/
│   │   ├── base.py
│   │   ├── data1.py
│   │   └── data2.py
│   ├── contracts/
│   │   ├── canonical.py
│   │   └── pre_state.py
│   ├── evidence/
│   │   ├── admissibility.py
│   │   └── support.py
│   ├── episode/
│   │   ├── membership.py
│   │   └── node_builder.py
│   ├── feature_registry/
│   │   └── loader.py
│   └── README.md
├── M1/
│   └── README.md               # Boundary placeholder only
├── M2/
│   └── README.md               # Boundary placeholder only
├── M3/
│   └── README.md               # PRE + frozen action-registry boundary only
└── M4/
    └── README.md               # M1 + M2 + M3 decision boundary only

exp/
├── README.md
├── exp1/README.md
├── exp2/README.md
├── exp3/README.md
└── exp4/README.md              # Documentation placeholders; no runners

metadata/
└── datasets/
    ├── data1/dataset_profile.yaml
    └── data2/dataset_profile.yaml
docs/
└── datasets/README.md          # Raw roots are external and read-only

configs/
├── scientific/foundation.yaml
├── reproducibility/smoke.yaml
└── engineering/local.example.yaml

registries/
├── data_usage_rules.yaml
├── scientific_variables.yaml
├── dataset_capabilities.yaml
├── source_priority.yaml
└── registry_manifest.json

validation/
├── cli.py
├── foundation.py
├── dependency_rules.py
└── reporting.py

tests/
├── contract/
├── unit/
├── integration/
├── static/
└── fixtures/
    ├── data1/
    ├── data2/
    └── pre/

outputs/
├── runtime/.gitkeep
├── formal/.gitkeep
├── evaluation/.gitkeep
├── paper_candidate/.gitkeep
└── manuscript_values/.gitkeep

pyproject.toml
requirements.txt
README.md
```

**Structure Decision**: Preserve the authoritative `model/PRE/M1/M2/M3/M4` and `exp` architecture.
The names `data1` and `data2` identify external read-only raw-data roots, so all project-owned dataset
profiles live under `metadata/datasets/` and explanatory material under `docs/datasets/`. No source,
README, metadata, registry, cache, canonical output, or validation artifact is written into either raw
root. Shared contracts live in `model/common`; dataset-specific raw names
appear only inside PRE adapters, data-usage registries, source validators, and fixtures. M1-M4 and
experiment folders contain boundary documentation only in this milestone. Registries are top-level
auditable scientific inputs, while outputs are pre-separated into the five frozen artifact layers.

## Phase 0: Research Decisions

Phase 0 is complete in [research.md](research.md). It resolves foundation engineering decisions while
retaining scientific parameters marked `DEVELOPMENT_FROZEN` or `UNSUPPORTED`. No open `NEEDS
CLARIFICATION` marker remains.

Principal decisions:

1. Use validated immutable Pydantic contracts and canonical JSON identities.
2. Represent unsupported values structurally, never as a numeric sentinel.
3. Keep adapters source-specific but expose one dataset-neutral protocol.
4. Make availability basis and decision-time role mandatory and independent.
5. Treat registries as versioned scientific inputs with referential-integrity checks.
6. Build PRE as pure selection/validation composition over canonical records.
7. Use fixture-only validation and block all algorithmic/experiment scope.

## Phase 1: Design and Contracts

Phase 1 outputs are:

- [data-model.md](data-model.md): entities, invariants, identities, relationships, and state changes.
- [contracts/adapter-protocol.md](contracts/adapter-protocol.md): independent adapter capability and
  canonical-emission interface.
- [contracts/pre-foundation.md](contracts/pre-foundation.md): PRE inputs, outputs, admissibility,
  latest-legal selection, support propagation, and immutability.
- [contracts/registry-schemas.md](contracts/registry-schemas.md): data-use, scientific-variable,
  capability, priority, and manifest schemas.
- [contracts/downstream-boundaries.md](contracts/downstream-boundaries.md): non-executable M1-M4 and
  experiment boundaries, including the confirmed M3/M4 split.
- [contracts/validation-cli.md](contracts/validation-cli.md): offline validation commands, result
  schema, exit status, and prohibited side effects.
- [quickstart.md](quickstart.md): future implementation validation scenarios, not implementation code.

## Post-Design Constitution Re-check

PASS. The design contains no algorithm implementation, no experimental protocol execution, no legacy
interface, no raw-data mutation, and no Git operation. It keeps unsupported and development-frozen
objects explicit; gives each dataset an independent capability profile; prevents M4 raw access; makes
M3 candidate instantiation dependent only on PRE plus a frozen registry; and reserves decision mapping
for M4 after M1/M2/M3 inputs exist.

## Complexity Tracking

No entries. All gates pass without exception.

## Plan Review Gate

This plan MUST be reviewed and approved before `/speckit-tasks`. Approval authorizes task generation,
not implementation, experiment execution, raw-data access, or Git/GitHub operations.
