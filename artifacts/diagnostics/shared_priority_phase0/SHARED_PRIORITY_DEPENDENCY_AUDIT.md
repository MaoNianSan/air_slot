# Shared Recovery-Priority Phase 0 Dependency Audit

- Audit date: `2026-09-06`
- Repository HEAD: `b6ed055d3ce92892b76eca99624d865f9d83444c`
- Status: `PASS`

## Authoritative Dependencies

| Object | Authority | Status |
|---|---|---|
| M1 scenario contract | `model/M1/contracts.py:M1V2Scenario` | `FOUND` |
| M1 `d_to_minutes` | `M1V2Scenario.d_to_minutes` | `FOUND` |
| Scenario weight | M1/M2 scenario contracts | `FOUND` |
| M2 V4 formal scope | `model/M2/cu/registry.py` plus active registry | `FOUND` |
| Seven-component ontology | `model/common/consequence_ontology.py` | `FOUND` |
| M2 native quantities | `NativeQuantity` / `ConsequenceRow.native_quantity` | `FOUND` |
| M2 CU quantities | `CUQuantity` / `ConsequenceRow.constructed_value_cu` | `FOUND` |
| V4 scales | Active M2 registry | `FOUND` |
| V4 registry hash | Active registry loader | `FOUND` |
| Support semantics | M2 contracts plus active registry | `FOUND` |
| Development fixture | Frozen M1 scenarios plus frozen M2 consequences | `FOUND` |
| Final Test access needed | Phase 0 interface-only execution | `PASS: false` |

## Active Authority

- Active registry: `M2_DATA2_FORMAL_CU_V4`
- Registry hash: `sha256:a566efb5ff02980f10eb22eaa1a27a47d9a52f88abe302cd00c1627363022f99`
- Derived CU-normalization registry hash: `sha256:8c9bfbed9d6b64c288cb5591f77fab9c3896ebc8d29d0a6450333ef2cc104d8e`
- Seven-component scope hash: `sha256:d95b404f683440b296b1897df9b8453cbb1161db88215c6fa1efc164d5ae4621`
- Support rule: `UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY`

## Development Fixture Decision

The existing Development-only M2 golden fixes the node and carries CU records whose normalization-registry digest is `sha256:8c9bfbed9d6b64c288cb5591f77fab9c3896ebc8d29d0a6450333ef2cc104d8e`. This is the current derived CU-normalization registry digest produced from the active M2 V4 scientific registry; it is distinct from, and compatible with, the scientific-registry hash `sha256:a566efb5ff02980f10eb22eaa1a27a47d9a52f88abe302cd00c1627363022f99`. The integration smoke may reuse the fixed M1/M2 records without selecting a node by score.

## Guards

No Final Test input, raw-data reconstruction, model training, parameter selection, ranking, correlation, Kendall, Top-K, or paper-result computation was used in this audit.
