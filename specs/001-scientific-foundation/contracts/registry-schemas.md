# Contract: Registry Schemas

## General Rules

Registries use UTF-8 YAML, stable identifiers, semantic versions, and explicit freeze state. A
`registry_manifest.json` records each file's SHA-256 and a combined identity. Unknown keys may be
rejected in formal loading to prevent misspelled scientific rules from being ignored.

No registry may contain a machine-specific raw path, secret, runtime output, learned result, or
paper-facing claim.

## Data Usage Rule Registry

Required fields:

```yaml
rule_id: string
rule_version: semver
freeze_state: FROZEN | DEVELOPMENT_FROZEN | UNSUPPORTED
dataset_id: string
logical_source: string
raw_columns: [string]
raw_semantics: string
raw_unit: string | null
canonical_object: string
canonical_variable: string
canonical_unit: string
transformation_rule: string
event_time_source: string | null
availability_rule: string
decision_time_role: enum
evidence_class: enum
support_ceiling: enum
missing_rule: string
stale_rule: string
fallback_rule: string
pre_family: string
downstream_consumers: [PRE | M1 | M2 | M3 | EVALUATION_ONLY]
scientific_purpose: string
semantic_status: string
confidence: HIGH | MEDIUM | LOW
external_evidence_rule_ids: [string]
```

Validation rejects `M4` as a raw/canonical consumer, blank fallback semantics, or an output ceiling
stronger than inputs without a registered external-evidence rule.

## Scientific Variable Registry

Required fields:

```yaml
scientific_variable: string
registry_version: semver
freeze_state: enum
pre_family: string
canonical_inputs: [string]
transformation_rule: string
unit: string
time_semantics: string
availability_rule: string
evidence_class: enum
support_ceiling: enum
missing_rule: string
fallback_rule: string
consumers: [PRE | M1 | M2 | M3 | EVALUATION_ONLY]
development_frozen_dependencies: [string]
dataset_support:
  data1_2019:
    formal_input_support: enum
    realized_outcome_support: enum
    reason_code: string | null
  data2_2019:
    formal_input_support: enum
    realized_outcome_support: enum
    reason_code: string | null
notes: string
```

Every canonical input must be produced by at least one data-usage rule for the relevant dataset, or
the dataset entry must explicitly be unsupported.

## Dataset Capability Registry

Required per dataset/object: profile, decision-time role, maximum evidence class, separate formal and
realized support, freeze state, reason, and permitted source families. The registry explicitly records
unsupported trajectory/weather/flow/resource/action-log objects where applicable.

`cross_dataset_reference_overlay` defaults to false. If a future feature enables it, it must add source
dataset, grain, join key, period, provenance, evidence class, and ceiling; row-level fusion remains
prohibited unless the scientific specification changes.

## Source Priority Registry

Required per scientific object: applicable dataset, source/rule IDs, deterministic integer priority,
scope condition, and version. Equal-priority incompatible values cause `EQUAL_PRIORITY_CONFLICT`; row
order is not a tie breaker.

## Manifest

```json
{
  "manifest_version": "1.0.0",
  "registries": [
    {"path": "registries/data_usage_rules.yaml", "sha256": "..."}
  ],
  "combined_sha256": "...",
  "validation_status": "PASS"
}
```

The generated time is runtime metadata and excluded from the combined scientific identity.

## Required Integrity Checks

- Unique IDs and valid semantic versions.
- Known enums, units, canonical objects, families, rules, and consumers.
- Complete cross-references and no fallback/external-evidence cycles.
- No M4 raw/canonical dependency.
- No unsupported object with non-null formal value permission.
- No development-frozen field with an implicit numeric/categorical default.
- data1/data2 source names do not leak into downstream model contracts.
- Combined manifest identity is reproducible from file contents.
