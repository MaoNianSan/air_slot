# M4 boundary

M4 accepts only the typed request:

```text
PREState + AlignedScenario + ScenarioConsequence + CandidateAction
           + ActionMaterialCoverageContract
  -> M4DecisionRequest
  -> eligibility -> post-action consequence -> residual risk -> lane -> ranking
```

It hard-fails PRE/M1 identity mismatches, scenario lineage mismatches, consequence ontology or
estimand-scope mismatches, coverage-contract violations, missing A00, and duplicate candidate
identity. M4 is the only formal action-comparison/ranking layer. Only `FORMAL` actions receive
authoritative ranks; A00 remains exact identity. Mean-only, no-coverage, no-evidence, and
no-induced modes are not formal production switches.
