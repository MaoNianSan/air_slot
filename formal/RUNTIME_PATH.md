# Formal Runtime Path

The current runtime path is the V2 chain:

- `exp/jatm_section4/` — M1 history-capacity selection (H16 is the frozen
  primary).
- `exp/jatm_section5/` — hash-locked Section-5 development layer.
- `exp/jatm_s34/` — shared annual science, cloud scheduler/worker and store.
- `formal/v2_phase7/` — the sealed Final-Test runner and its read-only
  paper-facing projections.

Those drivers stand on two explicit library packages:

- `exp/inputs/` — the preserved data-input chain (frozen cache -> canonical
  nodes -> PRE state -> typed model inputs): `development`, `formal`,
  `common_support`, `model_inputs`, `writers`.
- `exp/shared/` — reusable analysis helpers: `forecast_metrics`,
  `rank_metrics`, `protocol_constants`, `priority_population`,
  `priority_bootstrap`, `similar_delay`, `informativeness`,
  `perturbation_views`, `screening_triage`, plus `resampling`,
  `analytical`, `output`, `contracts`, `priority`, `recovery_priority`.

Retired on 2026-10-21 and preserved in Git history only: the V1 typed protocol
runners `exp/exp1` .. `exp/exp4` and the V1 report generator
`formal/final_test_run.py`. Their frozen results remain under
`artifacts/experiment/final_test/` and must not be treated as live runtimes.
