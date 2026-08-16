# Feature Specification: Experiments and Reporting

Implement Exp1 history/state ablations, Exp2 2x2 and lineage shuffle, Exp3 contract/risk ablations plus auxiliary LLM audit interface, and Exp4 sensitivity grids. All runners consume frozen formal artifacts, split/bootstrap by episode, write evaluation only, and never redefine PRE-M4. Generate reproducible figure/table/source-data bundles, gated paper-candidate promotion, paper_numbers.json and manuscript macros. LLM calls are provider-injected and absence yields NOT_RUN, never fabricated output.

Success: runner schemas/baselines/ablations, bootstrap/sensitivity, reporting four/three-piece bundles, promotion provenance and no-LLM negative tests pass; experiment smoke executes on synthetic frozen artifacts.
