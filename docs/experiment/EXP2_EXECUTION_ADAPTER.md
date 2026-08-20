# Exp2 Scientific Execution Adapter V1

## Status

`EXP2_EXECUTION_ADAPTER_STATUS = CODE_READY_ARTIFACT_BINDING_BLOCKED`

This adapter prepares a strict binding between the implemented Exp2 representations and future human-approved M3/M4 scientific artifacts. It does not execute Exp2, choose a variant, choose scientific parameters, or produce results.

## Package

| File | Contract |
| --- | --- |
| `exp/exp2/execution/execution_manifest.py` | Immutable execution manifest and fixed-identity comparison across variants |
| `exp/exp2/execution/artifact_loader.py` | Strict artifact envelope, hash, provenance, and support validation |
| `exp/exp2/execution/downstream_binding.py` | One identity-locked M3 executor and one identity-locked M4 evaluator for all variants |
| `exp/exp2/execution/__init__.py` | Public execution-preparation imports |

## Artifact envelope

Each artifact is an explicit JSON envelope:

```json
{
  "schema_version": "AIR_SLOT_EXP2_EXECUTION_ARTIFACT_V1",
  "artifact_kind": "M1",
  "artifact_version": "HUMAN_SUPPLIED_VERSION",
  "artifact_hash": "sha256:...",
  "payload": {}
}
```

`artifact_hash` is `model.common.identity.content_id(payload)`, the repository's canonical payload hash. The manifest path, kind, version, and hash must exactly match the envelope. Missing files, invalid JSON/schema, contract failures, and hash/version/kind mismatches raise `Exp2ExecutionBlocked` with `BLOCKED_MISSING_ARTIFACT`. No alternate path, default artifact, or synthesized value is attempted.

## Artifact payload contracts

### M1

Required payload:

- non-empty `scenarios` satisfying the Exp2 M1 surface: scenario ID, normalized positive weight, `D_OB`, `D_TX`, derived/declared `D_TO`, and lineage;
- `cutoff_provenance` containing decision node ID, timezone-aware decision time, timezone-aware information cutoff, named availability rule, and source-manifest hash.

The loader rejects an information cutoff after decision time. It validates the source through the JOINT representation adapter without training or resampling.

### M2

Required payload:

- non-empty consequence scenarios containing the exact seven-component ontology and M2-emitted CU values/support/reference lineage;
- CU registry ID/hash, freeze ID, and reference period.

The loader validates the COMPONENT representation. It does not recompute native quantities or CU.

### M3

Required payload:

- ordered, unique action IDs;
- structural action-registry hash;
- response-registry hash.

The adapter records identity only. It does not materialize response parameters or choose LOW/BASE/HIGH sensitivity.

### M4

Required payload:

- monetary-mapping hash and status;
- risk-policy hash and status.

Both statuses must be `FROZEN`. `TEST_ONLY` and `NOT_FROZEN` raise `BLOCKED_UNSUPPORTED_MAPPING`. The adapter never replaces them with the current design registry or a test mapping.

## Execution manifest

`Exp2ExecutionManifest` requires:

- `dataset_id`;
- `split`;
- `seed`;
- exact M1, M2, M3, and M4 `ArtifactReference` objects;
- `variant_id` from the six-entry Exp2 registry;
- SHA-256 `config_hash`.

`validate_variant_manifests` requires every representation variant to share dataset, split, seed, all four artifact identities, and configuration hash. Only `variant_id` may differ.

## Downstream binding

`Exp2DownstreamExecutor` implements the existing `Exp2DownstreamInterface`. Its constructor requires:

- one validated manifest;
- one `READY` loaded-artifact set;
- one already constructed M3 executor callable;
- one already constructed M4 evaluator callable.

Those callables are stored once and shared by all variants. The adapter passes only the bound M3/M4 artifact identities to them; no per-variant parameter argument exists.

If later invoked by an separately authorized run, the adapter enforces:

- representation source hashes and versions equal the loaded M1/M2 artifacts;
- M3 output action IDs exactly equal the frozen action set;
- action-to-response-rule hashes remain identical across variants;
- M4 output action IDs equal M3 action IDs;
- every M4 output cites the exact M3 envelope hash;
- monetary-mapping and risk-policy hashes equal the frozen M4 artifact.

## Readiness statuses

| Status | Meaning |
| --- | --- |
| `READY` | All four supplied artifacts passed structural, hash, identity, cutoff, and frozen-M4 checks; binding may be constructed but execution still requires authorization |
| `BLOCKED_MISSING_ARTIFACT` | Required artifact is absent, invalid, corrupt, wrong kind/version/hash, or fails its M1/M2/M3/M4 payload contract |
| `BLOCKED_UNSUPPORTED_MAPPING` | M4 monetary mapping or risk policy is not scientifically `FROZEN` |

There is no fallback status and no implicit downgrade to test-only execution.

## Current repository gate

The checked-in registries are inputs to future human decisions, not automatic scientific bindings:

- `registries/m3_response_scenarios.yaml` declares `formal_support_upgrade=false` and contains scenario-response parameters;
- `registries/m4_v2_monetary_mapping_design.json` declares `production_mapping_enabled=false` and `SCIENTIFIC_DECISION_REQUIRED`.

Consequently, this implementation is adapter-ready but the repository is not presently `READY` for scientific Exp2 execution. A future run must supply identity-complete, human-approved frozen artifacts and separately authorized executor/evaluator callables.

## Preparation-only example

```python
manifest = Exp2ExecutionManifest.model_validate_json(manifest_path.read_text())
artifacts = Exp2ArtifactLoader(artifact_root=artifact_root).load_all(manifest)
binding = Exp2DownstreamExecutor(
    manifest=manifest,
    artifacts=artifacts,
    m3_executor=human_approved_m3_executor,
    m4_evaluator=human_approved_m4_evaluator,
)
```

This constructs a binding only. No method that executes M3, M4, Exp2, reporting, or result generation is called by the preparation workflow.

## Tests

`tests/experiment/test_exp2_execution/` verifies manifest validation, artifact hashes, missing/unsupported blocked statuses, and cross-variant fixed binding. The injected callable fixtures fail deliberately if invoked, proving that these tests do not execute an experiment.
