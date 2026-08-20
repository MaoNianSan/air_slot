# Experiment Result Schema Audit

## Current schema coverage

The current primary schema is `ExperimentRunManifest` plus generic result rows from `BaseRunner`.

| Required field | Current field | Status | Gap |
| --- | --- | --- | --- |
| experiment ID | `experiment` | `ALIGNED` | lacks protocol/version identity |
| variant ID | manifest `variant_ids`; row `variant` | `ALIGNED` | no per-variant transform/config hash beyond optional `variant_hashes` |
| model version | none; `model_artifact_hashes` and `git_commit_sha` are indirect | `MISSING` | model version and exact model artifact must be explicit |
| scenario hash | none dedicated; `formal_output_hash`/`input_manifest_hash` are generic | `MISSING` | cannot prove all variants used the same M1 scenario artifact |
| dataset | `dataset_instance_id`, `dataset_role` | `ALIGNED` | split/cohort semantics still need schema validation |
| seed | `random_seed`; manifest-wide RNG stream names | `PARTIAL` | no per-stream seed/key or transformation replicate identity |
| metrics | row `metric`; manifest `primary_metric="metric"` | `STALE` | no metric ID/version/unit/denominator/CI/support |
| support status | row `status=SMOKE/EVALUATED` | `MISSING` | execution status is not scientific support, response support, or ranking authority |

Useful existing provenance includes scientific/evaluation/config/registry/split/cohort hashes, variant hashes, model artifact hashes, scenario count, timestamp, runtime mode, formal output hash, dataset role and Final Test guards.

## Additional schema risks

- `BaseRunner` accepts arbitrary precomputed `variant_metrics`; the manifest cannot prove which model interface produced them.
- `formal/pipeline.py` hashes dictionary-shaped PRE-M4 payloads but does not validate current typed stage contracts.
- current status JSON can report `paper_full_ready=true` under the old V5 checks even when the new experiment implementations do not exist.
- reporting metadata is caller-defined and can omit model/scenario/support lineage.
- historical Exp234 manifests contain useful hashes but bind V1 scenarios, old M2/M3 interfaces, and temporary Development-only semantics.

## Proposed result contract

A future schema should have one immutable run manifest and typed metric records.

### Run manifest

- `schema_version`, `experiment_id`, `experiment_protocol_version`;
- `variant_ids` and `variant_contract_hashes`;
- repository commit and dirty-state declaration;
- dataset ID/role/split, cohort hash and counts;
- PRE contract/config/registry hashes;
- M1 model version/hash, calibration hash, scenario artifact hash/count;
- M2 scope/normalization/output hash;
- M3 registry/response/envelope hashes and response support;
- M4 monetary registry/risk-policy/evaluation hashes and ranking authority;
- named RNG streams with seeds/replicates;
- runtime environment, start/end timestamps and completion status;
- paper-result/Final-Test/approval fields.

### Metric record

- run ID, experiment ID, variant ID and reference variant;
- metric ID/version/family/unit/direction;
- aggregation unit and denominators;
- estimate/CI/bootstrap metadata;
- support state, authority, reason codes and abstentions;
- exact source artifact hashes.

## Validation requirements

- reject `UNSET` provenance on non-smoke outputs;
- require one identical M1 scenario hash across Exp2 variants;
- require current typed M2/M3/M4 schema versions where those stages are used;
- require support and authority for every decision/risk metric;
- reject duplicate run IDs with different content;
- round-trip JSON and verify a content-derived manifest hash;
- make evaluation artifacts write-once and prevent mutation of model/formal inputs.

`RESULT_SCHEMA_STATUS = PARTIAL_REWRITE_REQUIRED`

