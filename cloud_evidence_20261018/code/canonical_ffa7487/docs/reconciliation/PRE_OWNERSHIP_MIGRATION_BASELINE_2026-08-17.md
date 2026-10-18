# PRE Ownership Migration Baseline

- snapshot date: `2026-08-17`
- repository SHA: `88ad2843c8f2713cd4ae6c704b7d9247442ea51e`
- branch: `main`
- worktree at snapshot: modified `artifacts/diagnostics/v5_development_freeze/m1_warning_cohort_audit.json`; untracked `docs/reconciliation/PRE_OWNERSHIP_GATE_2026-08-17.md`
- migration authorization: architecture ownership repair and D3 prerequisite closure
- Final Test access count: `0`

## Frozen scientific provenance

| Object | Hash |
| --- | --- |
| scientific configuration (`config_hash`) | `sha256:dbcc3c5360ce23047b1f40d48fe207abb8c6e8e645b0f8ba3e50b10e71314662` |
| scientific configuration file bytes | `sha256:6570a93c151b3cd6e2d3d6f798e4950bd52cfe4845c70f13d11baf812cf2178d` |
| registry manifest combined hash | `sha256:dbe3da2d8f8b74cf920d2b1bfc75519970ce7e6d71133bba8d19208b90f56aaa` |
| PRE contract hash | `sha256:491747eda8aadca53fa8a4dd917ddae32bc518235356542d7d0fffa427e367cd` |
| M1 contract hash | `sha256:57a0fe92bc83f7c938492f1bd86f6ab015340d02485b22be1ee18b23e27176e2` |
| episode construction hash | `sha256:b81391e3645b60cd7f7462a79375884f0bf0420e7040bdf0ba5c80d3115deb47` |
| feature contract hash | `sha256:9da85a16092181fe56eb1e803420d4d40ac492e5c55a130ca9a25999263e4718` |
| split contract file hash | `sha256:d474570d6115da8b50478d4e7e60e994d168fa4cf16d5a9df2cbb414107fb912` |

The M1 contract snapshot covers `contracts.py`, `data.py`, `coverage.py`,
`target_builder.py`, and `pipeline.py`. The PRE contract hash uses the exact
pre-migration computation embedded in the historical H-selection runner.

## Frozen H/W evidence

| Evidence | Embedded evidence hash | File byte hash |
| --- | --- | --- |
| `m1_hstar_evidence.json` | `sha256:a56a7254e5e08c959d8e9d8be58456469b2f37a293f33495dfaf58cdf452b3a5` | `sha256:438b34a68243c97ae68aa3f32dd4f9e115aca335f3a5da11703fc94ebd588496` |
| `m1_wstar_evidence.json` | `sha256:35fed8273d737762a8c48321a1ce8bbd0aee76ff7c27537a57266430d3038fa1` | `sha256:4c6984effbf8c7d01be935565e0abd5370c74cd52446e2d3e22d3c0cdc32458b` |

Frozen decisions:

- `H_STAR = 32`
- `W_STAR = 30 minutes`
- H/W rerun during ownership migration: `FALSE`
- H/W evidence rewrite during ownership migration: `FALSE`

## Audit provenance

| Audit | File byte hash |
| --- | --- |
| current warning cohort audit | `sha256:cddddc8c82680870bde3ed2c4a7d5dada9c72b5838067a557de448c7914c40b1` |
| PRE ownership audit | `sha256:90938db40e0b43f2dbe23a6d6877b00d36325b2c4c5af42f3ce3388554256d69` |

The warning audit was already modified in the worktree before this migration.
It is treated as user-owned input and will not be overwritten.

## Planned ownership movement

| Current path | Planned responsibility after migration |
| --- | --- |
| `validation/data2_v5_hstar_development.py` | thin CLI compatibility wrapper |
| `validation/data2_v5_wstar_development.py` | thin CLI compatibility wrapper |
| `validation/performance_closure_p0.py` | validation profiler invoking PRE/M1 APIs only |
| `validation/support/data2_m1.py` | validation fixtures and compatibility imports only |
| `exp/exp1/history.py` | compatibility re-export of `model/M1/history.py` |
| `model/M1/history.py` | frozen CURRENT/FIXED/ADAPTIVE model-input semantics |
| `model/PRE/streaming/data2.py` | raw discovery, bounded reads, canonical records, episode/node/weather publication, resume and Development streaming |
| `model/PRE/development.py` | PRE-owned cohort/state construction API |
| `exp/exp1/development/hstar.py` | H experiment orchestration, Development evaluation, evidence logic |
| `exp/exp1/development/wstar.py` | W experiment orchestration, aggregation, recommendation, evidence logic |
| `validation/ownership_gate_v2.py` | static ownership verification and JSON gate output |

No target formula, support/evidence rule, episode identity rule, history
semantics, candidate set, seed set, training objective, equivalence rule, or
frozen H/W value is authorized to change.
