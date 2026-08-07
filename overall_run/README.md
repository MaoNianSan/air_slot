# overall_run

`overall_run` owns M1-M4 orchestration. M1, the M1-to-M2 V2 boundary, the M3 V4
structural contract, and the M4 V2 engineering contract are implemented.
Formal M2 valuation, M3 parameter freeze, and formal M3 library generation
remain behind explicit readiness gates.

## M1

The formal M1 contract is `M1_CHAIN_DYNAMIC_DISTRIBUTION_V1`:

```text
PRE Core V2 published bundle
-> availability-safe M1 PRE Adapter
-> single one-layer GRU
-> IB / OB / TX discrete distributions
-> per-target temperature scaling
-> fixed-random-number joint samples
-> independent M1 evaluation
```

The Adapter accepts only `pre/output_core/<mode>/AIR_CHAIN_CORE_V2/` and checks
the PRE contract, schema, research revision, manifest identity, artifact list,
and recorded hashes. Availability is always determined by
`availability_time <= query_time`.

The formal model uses one GRU layer, hidden size 8, zero initial state, and no
attention, bidirectionality, second production path, or independent takeoff
head. Hidden size 16 is capacity sensitivity for the same architecture.

M1 predicts the base variables `R_IB`, `R_OB`, and `T_TX`. Targets without
adequate event, schedule, turnaround, or chain evidence remain inactive and
produce `M1_SCIENTIFIC_NOT_READY`; they are never replaced by proxy labels or
zero-filled.

## M2 V2

`M1ScenarioBundle` exposes `R_IB`, `R_OB`, earliest off-block, predecessor
in-block, successor off-block and takeoff, taxi time, derived delays, support,
tail status, operational-reference provenance, and lineage. Finite bins use a
stable within-bin random stream; overflow uses a training-only empirical tail
or remains explicitly unresolved.

The M2 V2 adapter combines these scenarios with PRE context. The
`DIRECT_STRUCTURAL_COMPACT` reconstruction activates supported flight,
passenger, and resource subitems, converts each native quantity to constructed
units before aggregation, and currently applies the identity mapping
`1 CU = 1 RMB`. Unsupported subitems remain unavailable rather than becoming
zero loss. Unresolved overflow blocks formal q95 and CVaR90 publication.

## Downstream boundary

M1-to-M2 V2 code and synthetic integration tests are complete. Formal M1
training, calibration, resampling, and production M2 reconstruction have not
run. M3 V4 uses 21 version-bound atomic actions, sparse PRIMARY/SECONDARY/NONE
footprints over the nine M2 subitems, one shared Beta intensity per action draw,
and separate F/P/R implementation costs. Formal response and cost parameters
remain `NOT_CONFIGURED`; only synthetic fixtures may exercise the structural
generator. M4 V2 directly accepts `M2InputBundle`, nine-subitem
`M2SampleLoss` objects, and `M3Artifact`; it does not reconstruct M3 randomness
or fall back to channel arrays. PRE R2 is compatibility-only, PRE R3 requires
registry lineage, stage and opportunity contracts are explicit, and resource
availability is never inferred from pressure proxies. Test-only integration
exercises stable shared draw indexing, nine-subitem post loss, weighted
Mean-CVaR, four decision lanes, and Ranking@1/@2/@3/@5. Global execution still
stops at `M3_PARAMETER_NOT_FROZEN`. Engineering implementation does not imply
scientific or production readiness.

```text
M3_CONTRACT_STATUS = PASS
M3_ACTION_LIBRARY_COUNT = 21
M3_PARAMETER_FREEZE_STATUS = NOT_YET_DONE
M3_FORMAL_LIBRARY_STATUS = NOT_YET_RUN
M4_V2_ENGINEERING_STATUS = PASS
M4_V2_SYNTHETIC_INTEGRATION = PASS
M4_V2_FORMAL_STATUS = BLOCKED_BY_UPSTREAM
```

`A51`, `A52`, and `A53` are partial-support aircraft recovery actions with no
formal response or cost parameters. `A54` and `A55` remain forbidden. The old
channel-level `src/m3.py` implementation has moved to
`src/legacy/m3_v3_audit.py`; old M4 screening and evaluation are also isolated
under `src/legacy/`. Retired M4 APIs raise `M4_LEGACY_CONTRACT_RETIRED`.

## Verification

```powershell
D:/Python311/python.exe -m compileall -q overall_run/src overall_run/tests
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
D:/Python311/python.exe -m pytest -q overall_run/tests/m2
D:/Python311/python.exe -m pytest -q overall_run/tests/m3
D:/Python311/python.exe -m pytest -q overall_run/tests/m4
D:/Python311/python.exe -m pytest -q overall_run/tests/test_ranking_1235.py
```

See `../reports/m1_m2_v2/`, `../reports/m3_v2/`, and `../reports/m4_v2/` for
implementation, contract, test, and rerun reports.
