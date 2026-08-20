# Round 2 Experiment Implication Alignment

This audit identifies what the current experiment labels would need to establish relative to the framework. It does not redesign or run an experiment and does not promote Development evidence to paper evidence.

## Contribution-to-experiment audit

| Experiment | Framework question it must answer | Current manuscript question | Current repository evidence/status | Alignment |
|---|---|---|---|---|
| Exp1 | Does admissible history and the full state representation add decision-relevant information beyond current/static inputs? | Value of cross-stage information retention; history versus direct/current use. | Development freeze exists; no Final Test or `paper_full` run is authorized. | `PARTIALLY_ALIGNED` |
| Exp2 | Does preserving scenario-conditioned consequence decomposition change the representation relative to point or corrupted-lineage alternatives? | Operating-state and recovery-consequence representation. | Development-only point-collapse and lineage-shuffle consequence analysis exists; authoritative ranking is blocked and evidence uses historical M2 V1. | `PARTIALLY_ALIGNED` |
| Exp3 | What is contributed by explicit, provenance-qualified action-response representation, including A00 and support lanes? | Rolling recommendation refresh and state synchronization. | Current Development material is support-boundary evidence; non-A00 V2 responses are gated and M4 fields are not run. | `MISSING_EXPLANATION` |
| Exp4 | How robust/portable are state, consequence, response, and valuation conclusions across data conditions and declared sensitivities? | Overall adequacy, admissibility, cross-data validation, and computational evaluation. | Readiness is partial; no formal Exp4 or Final Test run exists. | `PARTIALLY_ALIGNED` |

## Principal mismatch

Exp3 is the clearest contribution mismatch. The requested framework mapping assigns Exp3 to action-response representation, while the manuscript assigns it primarily to rolling refresh/state synchronization. The current repository's Exp3 evidence concerns support boundaries and authoritative abstention, not validated non-A00 action effects. The next writing/planning phase must decide how to make the paper question and available evidence correspond, but this audit does not prescribe a new experimental design.

## Evidence boundaries that must appear in the manuscript

- Exp1: an engineering/Development comparison does not establish general decision improvement.
- Exp2: historical M2 V1 evidence cannot be relabeled as a seven-component M2 V2 result.
- Exp3: structural action count and numerical scenario evaluability do not establish action effectiveness or causal response.
- Exp4: sensitivity candidates and partial readiness are not evidence of generalization.
- Across all four experiments: no Final Test or `paper_full` evidence is currently authorized or available.

Final experiment status: `PARTIALLY_ALIGNED_NOT_PAPER_READY`, with a material Exp3 role mismatch.
