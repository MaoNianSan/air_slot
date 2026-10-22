# JATM S3–4 engineering decision log — 2026-10-11

This log records the decisions that affect supplementary-experiment preparation.
It does not change a frozen scientific artifact, registry, split assignment, or
formal executor.

## Confirmed

| ID | Decision | Engineering consequence | Status |
| --- | --- | --- | --- |
| D1 | Use an exact discrete product coupling that preserves each primitive weighted marginal. | Use `model/M1/marginal_distribution.py` for new sensitivity work. Keep `build_marginal_representation` and sealed formal outputs unchanged. | `ACCEPTED_ENGINEERING_READY` |
| D2 | Retain the current `r_ib` semantics for `F_continuity`; document the meaning. | Keep `F_continuity = max(0, r_ib_minutes - turnaround_reference)` and record `R_IB = max(0, T_IB_A00 - decision_time)` as an internal remaining-time coordinate. | `ACCEPTED_DOCUMENTATION_ONLY` |
| D3 | Freeze two separate Delay+Exposure views: passenger-time primary and downstream-exposure companion. | Use `exp/jatm_s34/delay_exposure.py`; compute `P^D * expected_passengers_per_flight` and `P^D * expected_downstream_exposure` separately. Do not use the three-way product. | `ACCEPTED_ENGINEERING_READY` |

## Awaiting exact specification

The choices below were approved in principle, but a runnable experiment still
needs one concrete formula and one named source artifact.

| ID | Required specification | Current status |
| --- | --- | --- |
| D4 | Name the audited `FIXED_COMMON` reference artifact and hash. | `PASS_FIXED_COMMON_REBUILT` |

The D3 branch is engineering-ready, subject to the existing Test and
common-support gates. D4 was rebuilt from legal 2017 H1 Train rows into the
versioned bundle `artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_R2/2017/M2_REFERENCES`.
The audited bundle is reported at
`D:\\Local_Projects\\airslot\\reports\\jatm_s34_20261010\\g0\\D4_FIXED_COMMON_AUDIT_R2.json`.
It binds all payloads to `data2_2017_2022`, uses T100 H1 and DB1B Q1+Q2, and
passes seven-component positive-support, unit, payload-hash, and manifest-hash
checks. No 2019 or Test scale is substituted.

## Validation boundary

The D1 adapter has contract tests and is not wired into the sealed formal
executor in this preparation pass. It is a reusable implementation for a
future E3 run after the integration contract is frozen. D2 changes no numeric
code. No Final-Test, Q4/Test, held-out tuning, or full scientific run is
authorized by this log.
