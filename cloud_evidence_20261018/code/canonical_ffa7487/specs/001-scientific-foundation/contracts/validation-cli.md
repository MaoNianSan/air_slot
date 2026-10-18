# Contract: Foundation Validation CLI

## Commands

The future implementation exposes one module entry point:

```text
python -m validation.cli contracts
python -m validation.cli adapters --fixtures-only
python -m validation.cli pre --fixtures-only
python -m validation.cli all --fixtures-only
```

No command scans full raw data without an explicit source request, and no foundation command runs
M1-M4 or an experiment.

## Inputs

- Registry root and configuration root, defaulting to project-relative locations.
- Optional fixture root.
- Optional output root under `outputs/runtime/foundation_validation/`.
- `--json` for machine-readable stdout.

Machine-specific raw paths may be provided only for a separately authorized adapter-source validation;
they are not allowed in committed scientific configuration or identity hashes.

Commands use the current system/current Python interpreter. Project dependencies come only from
`requirements.txt`; the CLI does not create, activate, locate, require, or record a virtual/Conda-style
environment. Runtime metadata records only Python version, package versions, platform, and device.

## Output Schema

```json
{
  "validation_run_id": "sha256:...",
  "status": "PASS",
  "FIXTURE_ONLY": true,
  "paper_result": false,
  "evaluation_scope": "FOUNDATION_ONLY",
  "registry_manifest_hash": "sha256:...",
  "checks": [
    {
      "check_id": "PRE_FUTURE_EVIDENCE_REJECTED",
      "status": "PASS",
      "severity": "ERROR",
      "object_id": "fixture:...",
      "message": "..."
    }
  ],
  "summary": {"passed": 1, "failed": 0, "blocked": 0, "not_run": 0}
}
```

Allowed overall statuses: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`. `PASS` is engineering foundation
validation only and cannot be labeled scientific readiness or paper evidence.

## Exit Codes

- `0`: requested checks completed with no failure.
- `1`: one or more validation failures.
- `2`: invalid command/config/registry schema.
- `3`: required explicit source/fixture not configured.
- `4`: prohibited scope request, such as algorithm, experiment, cross-dataset pooling, or Git action.

## Mandatory Check Families

- Contract serialization and enum/value invariants.
- Registry schema, referential integrity, content identity, and consumer boundaries.
- Adapter description/capability without raw access.
- Fixture canonical conversion and post-hoc role preservation.
- PRE membership, time admissibility, latest-legal selection, tie conflict, support monotonicity,
  unsupported propagation, and immutable identity.
- Static dependency direction and raw-field isolation.
- Repeated-run byte/hash stability.

## Side-Effect Contract

Validation may write only its explicitly configured runtime report and formal fixture artifacts marked
`FIXTURE_ONLY`. It may not change raw data, registries, source code, formal non-fixture artifacts,
evaluation/paper/manuscript outputs, environment packages, or Git state.
