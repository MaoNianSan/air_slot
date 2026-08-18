# exp2

Point collapse and lineage shuffle are evaluation-only transforms over frozen M1 scenario
artifacts. They preserve source hashes and per-target marginals.

Current status (2026-08-18, Development only):

- `M2_DATA2_FORMAL_CU_V1` is frozen; the frozen M1 Development scenario artifact is reused
  (`sha256:ca3370a3...1dfec`, `M1_PURE_INFERENCE_REUSED=TRUE`);
- temporary Development consequence analysis is completed (`EXP2_CONSEQUENCE_DEVELOPMENT =
  COMPLETED_TEMPORARY`): distributional vs point-collapse consequence distortion, strata, and the
  frozen lineage-corruption grid are recorded in `docs/results/EXP2_DEVELOPMENT_TEMP_RESULT_SUMMARY.md`;
- scenario-conditioned action comparison is available where applicable
  (`EXP2_SCENARIO_ACTION_DEVELOPMENT = COMPLETED_TEMPORARY`), labeled
  SCENARIO_CONDITIONED / NON_AUTHORITATIVE / TEMPORARY_DEVELOPMENT_ONLY;
- authoritative formal ranking remains blocked by `M4_MATERIAL_COVERAGE_UNFROZEN`
  (`EXP2_AUTHORITATIVE_FORMAL_RANKING = BLOCKED_BY_M4_MATERIAL_COVERAGE_UNFROZEN`).

No Final Test or `paper_full` Exp2 run exists; the temporary result is not final paper evidence.
