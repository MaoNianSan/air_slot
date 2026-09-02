# PRE boundary

PRE defines contracts, registered source adapters, evidence admissibility,
cutoff-gated publication, lineage, and typed `PREState` construction. It
performs no M1-M4 computation.

`DecisionNodeRecord.status = ABSTAINED` is reserved for critical node-level invalidation (invalid episode identity or membership, an unavailable decision-time boundary, or an equivalent node contract failure). Object-level `ABSTAIN` remains local: other supported objects in the same constructed node continue to publish.

Development-frozen values must be configured explicitly. There is no silent fallback.

Source parsing is isolated under `model/PRE/canonical/normalization_*`; the historical
`normalization.py` import path remains a public facade. Dataset-specific adapters produce typed
canonical objects, and downstream M1-M4 code does not parse raw schemas directly.

The exact published-object inventory and read-only data rules are documented in
`docs/DATA_AND_EVIDENCE_BOUNDARY.md`.
