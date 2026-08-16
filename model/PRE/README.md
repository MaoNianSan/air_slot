# PRE foundation skeleton

PRE defines contracts, registries, adapter interfaces, evidence admissibility, lineage foundations, and deterministic fixture-only state construction. It has no production raw reader and performs no M1-M4 computation.

`DecisionNodeRecord.status = ABSTAINED` is reserved for critical node-level invalidation (invalid episode identity or membership, an unavailable decision-time boundary, or an equivalent node contract failure). Object-level `ABSTAIN` remains local: other supported objects in the same constructed node continue to publish.

Development-frozen values must be configured explicitly. There is no silent fallback.

Source parsing is isolated under `model/PRE/canonical/normalization_*`; the historical
`normalization.py` import path remains a public facade. Dataset-specific adapters produce typed
canonical objects, and downstream M1-M4 code does not parse raw schemas directly.
