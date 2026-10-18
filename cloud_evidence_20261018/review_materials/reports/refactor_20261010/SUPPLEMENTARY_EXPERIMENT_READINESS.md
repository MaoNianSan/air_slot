# Supplementary Experiment Readiness Matrix — 2026-10-10

| Experiment | Purpose | Existing entry point | Required change | Status |
|---|---|---|---|---|
| `STAGE_Q_SCREENING_SENSITIVITY` | Check whether delay-based attention sufficiency changes with stage and screening capacity `q`. | `formal/v2_phase7/stage_q_screening_sensitivity.py` | None; frozen read-only runner and output contract already exist. | `READY_TO_RUN` |
| `CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS` | Descriptive stress test under three predefined consequence-domain emphasis profiles. | `formal/v2_phase7/consequence_domain_emphasis_robustness.py` | Updated one stale manifest-baseline assertion; no scientific implementation change. | `READY_TO_RUN` |

## Shared readiness evidence

- Authority checkout: `D:\research\air_slot\code\explore`, branch `v2/paper-primary`.
- Both runners expose callable CLI entry points and `--help` succeeds.
- Targeted fixture/contract tests: **45 passed**.
- `py_compile`: both supplementary runners, the development runner, and the referenced M2 module passed.
- No formal executor, Final-Test, full experiment, held-out tuning, or scientific recomputation was run.
- Existing `figures/` untracked content was preserved and not staged.

## Run command drafts

```powershell
cd D:\research\air_slot\code\explore
python -m formal.v2_phase7.stage_q_screening_sensitivity `
  --epoch-root <sealed canonical-v2 epoch root> `
  --out-dir <new supplementary output directory>

python -m formal.v2_phase7.consequence_domain_emphasis_robustness `
  --epoch-root <sealed canonical-v2 epoch root> `
  --out-dir <new supplementary output directory> `
  --profiles BALANCED,FLIGHT_EMPHASIS,PASSENGER_EMPHASIS,RESOURCE_EMPHASIS
```

These commands are drafts only; they were not executed in this pass.

## Deferred items

Marginal coupling repair, unit/semantic changes, split changes, and any experiment depending on those unresolved definitions remain blocked or deferred. No new scientific question was introduced.
