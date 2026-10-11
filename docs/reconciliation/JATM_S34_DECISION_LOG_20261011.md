# JATM S3–4 engineering decision log — 2026-10-11

This log records the decisions that affect supplementary-experiment preparation.
It does not change a frozen scientific artifact, registry, split assignment, or
formal executor.

## Confirmed

| ID | Decision | Engineering consequence | Status |
| --- | --- | --- | --- |
| D1 | Use an exact discrete product coupling that preserves each primitive weighted marginal. | Use `model/M1/marginal_distribution.py` for new sensitivity work. Keep `build_marginal_representation` and sealed formal outputs unchanged. | `ACCEPTED_ENGINEERING_READY` |
| D2 | Retain the current `r_ib` semantics for `F_continuity`; document the meaning. | Keep `F_continuity = max(0, r_ib_minutes - turnaround_reference)` and record `R_IB = max(0, T_IB_A00 - decision_time)` as an internal remaining-time coordinate. | `ACCEPTED_DOCUMENTATION_ONLY` |

## Awaiting exact specification

The choices below were approved in principle, but a runnable experiment still
needs one concrete formula and one named source artifact.

| ID | Required specification | Current status |
| --- | --- | --- |
| D3 | Select the exact `DELAY_EXPOSURE` formula from the bounded options in the execution report. | `BLOCKED_UNTIL_FORMULA_NAMED` |
| D4 | Name the audited `FIXED_COMMON` reference artifact and hash. | `BLOCKED_UNTIL_SOURCE_NAMED` |

Until D3 and D4 are named, the corresponding experiment branches remain typed
blocked. No proxy formula or cross-year scale is inferred from existing files.

## Validation boundary

The D1 adapter has contract tests and is not wired into the sealed formal
executor in this preparation pass. It is a reusable implementation for a
future E3 run after the integration contract is frozen. D2 changes no numeric
code. No Final-Test, Q4/Test, held-out tuning, or full scientific run is
authorized by this log.
