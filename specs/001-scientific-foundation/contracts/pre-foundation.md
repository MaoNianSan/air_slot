# Contract: PRE Foundation

## Purpose

Construct the decision-time admissible and supported information envelope for one episode node. This
is a skeleton contract and selection/validation implementation, not preprocessing shorthand and not a
prediction model.

## Input

```text
PREBuildRequest
  dataset_instance_id
  episode: EpisodeRecord
  decision_time: UTC datetime
  information_cutoff: UTC datetime
  canonical_records: iterable[CanonicalSourceRecord]
  frozen_references: iterable[AggregateReference]
  registry_manifest_hash
  scientific_config_hash
  reproducibility_config_hash
```

Requests containing multiple dataset instance IDs are rejected. Missing development-frozen rules do
not receive defaults.

## Processing Contract

1. Validate registry and configuration identities.
2. Validate episode membership independently of decision-time role.
3. Evaluate availability: only `availability_time <= information_cutoff <= decision_time` is eligible,
   under a registered availability basis.
4. For each dynamic scientific object, select the latest legal event; resolve equal-time candidates by
   registered source priority.
5. If an equal-priority conflict remains, flag and abstain for the affected object.
6. Apply missing, stale, fallback, and criticality rules only when explicitly frozen.
7. Enforce dataset and rule support ceilings and support monotonicity.
8. Construct immutable node, evidence, lineage, reference, and target-support artifacts.

Node-level invalidation and object-specific insufficiency are distinct. The node becomes `ABSTAINED`
only when the request, episode, dataset identity, time ordering, registry identity, or configuration
identity makes the whole node invalid. An object-specific `ABSTAIN` affects only that object and MUST
NOT suppress other supported objects in the same constructed node.

## Output

```text
PREBuildResult
  pre_state: PREState
  episode: EpisodeRecord
  decision_node: DecisionNodeRecord
  evidence_ledger: list[EvidenceLedgerEntry]
  variable_lineage: list[VariableLineageEntry]
  reference_state: ReferenceState
  target_support: list[TargetSupportState]
  validation_findings: list[ValidationFinding]
```

## Invariants

- Every non-null scientific value has complete lineage and an admissible selected record.
- Unsupported or abstaining values are null with a reason; no silent fallback exists.
- A later request may create a different node but cannot mutate a prior result.
- A valid constructed node may contain any mix of supported, degraded, and object-specific abstaining
  objects. In the required data1 example, `R_IB = SUPPORTED`, `R_OB = ABSTAIN`, and
  `T_TX = DERIVED / SUPPORTED`; the node remains constructed and publishes R_IB and T_TX.
- Raw field names are absent from PRE output contracts.
- PRE output contains no M1 prediction, M2 consequence, M3 candidate, or M4 decision.
- Fixture results are labeled `FIXTURE_ONLY` and cannot become paper evidence.

## Failure Contract

Node-level request failures raise typed errors or a node-level `ABSTAINED` result. Object-specific
insufficiency produces an explicit `ABSTAIN` artifact rather than aborting unrelated supported objects.
Stable reasons include
`FUTURE_EVIDENCE`, `NOT_EPISODE_MEMBER`, `AVAILABILITY_UNKNOWN`, `STALE_RULE_UNFROZEN`,
`EQUAL_PRIORITY_CONFLICT`, `SUPPORT_CEILING_EXCEEDED`, `FALLBACK_NOT_PERMITTED`,
`TARGET_SEMANTICS_UNSUPPORTED`, and `LINEAGE_INCOMPLETE`.
