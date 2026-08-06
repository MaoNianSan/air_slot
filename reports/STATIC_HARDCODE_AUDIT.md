# Static Hardcode Audit

Audit date: 2026-08-02

STATIC_HARDCODE_AUDIT=FAIL

## Findings

- R3 scientific thresholds are centralized in `pre/config/predecessor_matching.yaml`; no production-code copies of `1568.34` or `2880` were found.
- The ranking depths have one shared definition at `ranking_contract.py:9`, but are independently repeated in production metadata at `overall_run/src/pipeline_finalize.py:255`, `overall_run/src/pipeline_finalize.py:336`, `overall_adv/src/pipeline.py:275`, and `part_adv/src/pipeline.py:192`. This violates the single-authority requirement.
- The formal M3 action set is independently encoded in `overall_run/src/m3.py:13-23`, `overall_run/src/config.py:223-230`, `overall_run/src/selfcheck.py:135-136`, `pre/config/actions.yaml`, and `overall_run/config/m3_response_v3_expanded_provisional.yaml`. A change can therefore pass one layer and disagree with another.
- `fast_three_change_dev` is isolated from formal fast in the run configs and existing outputs. However, all four `clean.py` files restrict `--mode` to a fixed enum (`pre/clean.py:22-33` and equivalents), so the development output name cannot be dry-run cleaned directly.
- Runtime `n_jobs` is propagated through the CLI and run plan rather than hard-coded into scientific calculations.

## Decision

The threshold and output-path checks pass, but duplicated action/ranking authorities and the non-cleanable development profile make the static hardcode audit fail.
