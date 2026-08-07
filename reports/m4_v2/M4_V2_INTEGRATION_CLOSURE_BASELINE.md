# M4 V2 Integration Closure Baseline

Baseline captured: 2026-08-07 (Asia/Hong_Kong)

## Repository state

- Repository: `D:\Local_Projects\airslot`
- Branch: `main`
- Local HEAD: `c7060c8 M4v2`
- Remote `origin/main`: `c7060c8eaa33ce9cd5f007ce24761b3954e27a26`
- Tracked worktree state before closure edits: clean
- Pre-existing untracked material: present under `.workbuddy/`, `output_logs/`, `outputs/`, paper/audit folders, historical configs, and historical reports. These paths are outside this closure and must not be staged or modified.

## Active M4 implementation

The active package is `overall_run/src/m4/` and contains:

```text
__init__.py
compatibility.py
contracts.py
draw_pairing.py
evaluation.py
evidence.py
explanation.py
input_adapter.py
lane_assignment.py
opportunity.py
output.py
pipeline.py
post_loss.py
ranking.py
risk.py
rolling.py
stage_adapter.py
```

The old ambiguous active modules `src/m4.py`, `src/m4_screening.py`, and `src/m4_evaluation.py` are absent. Historical copies exist only as:

```text
src/legacy/m4_v1_api.py
src/legacy/m4_v1_screening.py
src/legacy/m4_v1_evaluation.py
```

## Authoritative implementation

`overall_run/src/config.py::AUTHORITATIVE_CODE` already contains every currently present formal file in `src/m4/`, plus the shared ranking contract adapter and root ranking contract. It does not include the three legacy M4 V1 files.

## Scientific configuration

`overall_run/config/scientific.yaml` already selects:

- `M4_CONTEXTUAL_RESIDUAL_RISK_V2`
- atomic actions with combinations disabled
- PRE Core V2 R2/R3 compatibility with R3 formal lineage
- M2 V2 and M3 V4 contracts
- `STABLE_SHARED_DRAW_INDEX`
- weighted Mean-CVaR weights `0.75/0.25`, alpha `0.90`
- Ranking@1/@2/@3/@5 with explicit null padding
- one `evaluation.m4` configuration block, disabled by default

The strict config validator already rejects retired top-level M4 decision-value keys and validates most M4 V2 invariants. It does not yet prove that the evaluation directory is outside the formal output directory.

## Pipeline and gates

`overall_run/src/pipeline.py` preserves the M3 contract, parameter-freeze, and formal-library gates. With the current scientific configuration, the first formal blocker remains `M3_PARAMETER_NOT_FROZEN`. A fixture that passes both M3 gates can reach `run_m4_formal_stage`; there is no unconditional M4 mismatch in this main entrypoint.

Remaining integration issues:

- optional evaluation is not invoked after formal artifact publication;
- `overall_run/src/pipeline_finalize.py` still raises an unconditional historical `M4_CONTRACT_MISMATCH`;
- publication eligibility is currently reduced to `formal_mode and not test_only`;
- formal output is written file-by-file without a bundle staging boundary.

## Ranking contract

M4 sorts lane ranks using the intended five-key order, but `build_authoritative_ranking` then calls shared `full_ranking_from_scores`, which applies another sort. Prefix construction is therefore not yet guaranteed to preserve one authoritative M4 order. The root ranking contract version must be inspected and unified during closure.

## Evaluation state

`overall_run/src/m4/evaluation.py` exists, but `run_optional_evaluation` currently reads from `config["m4"]` rather than `config["evaluation"]["m4"]`. The formal pipeline does not call it, and formal/evaluation statuses are not represented independently in the M4 artifact manifest.

## Baseline conclusion

```text
M4_V2_CORE_IMPLEMENTATION = PASS
M4_V2_REPOSITORY_INTEGRATION = INCOMPLETE
M4_FORMAL_STATUS = BLOCKED_BY_UPSTREAM
GLOBAL_RERUN_ALLOWED = NO
```
