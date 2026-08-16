# M2 boundary

M2 maps `AlignedScenario` to the fixed seven-component `CONSEQUENCE_COMPONENTS` ontology:

```text
AlignedScenario -> native consequence quantities -> valuation
                 -> ComponentVector -> FormalEstimandValue
```

Native quantities and valuation are separate responsibilities. Unsupported quantities remain null
with explicit support; they are never silently converted to zero. `ConsequenceScope` and
`FormalEstimandValue` are the authoritative M4 interface. Available-component diagnostics are not
formal ranking values. The current `ValuationRegistry.smoke()` path is development evidence, not a
paper-frozen valuation registry.
