# M2 boundary

The principal V2 path maps a strict `M2ScenarioInput` copied from
`M1V2Scenario` to the fixed seven-component `CONSEQUENCE_COMPONENTS` ontology:

```text
M1V2Scenario envelope -> native consequence quantities -> CU normalization
                 -> ComponentVector -> FormalEstimandValue
```

Native quantities and CU normalization are separate responsibilities. Unsupported quantities remain null
with explicit support; they are never silently converted to zero. `ConsequenceScope` and
`FormalEstimandValue` are the authoritative M4 interface. Available-component diagnostics are not
formal ranking values. The current `ValuationRegistry.smoke()` path is development evidence, not a
paper-frozen normalization registry. CU is not money; monetary mapping belongs to M4.

`M2Mapper.map_m1_scenarios` is the V2 scientific interface. It preserves each
scenario and its PRE/reference lineage and emits baseline `C^{0,CU}` only.
`M2Mapper.map_m1_distribution` packages every scenario ID and weight without
top-k filtering or point collapse. Frozen CU rows carry a distinct typed CU
object and version-sensitive registry/rule/scale artifact identity.
`M2Mapper.map_scenarios` remains a historical dictionary compatibility path.
See `docs/reconciliation/ROUND2_M2_V2_DESIGN.md` for the frozen design and
unresolved scientific gates.
