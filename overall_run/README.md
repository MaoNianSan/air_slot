# overall_run

`overall_run` owns M1-M4 orchestration. M1, the M1-to-M2 V2 boundary, and the
M3 V4 structural contract are implemented. Formal M2 valuation, M3 parameter
freeze, and M4 migration remain behind explicit readiness gates.

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
run. M3 V4 uses 18 version-bound atomic actions, sparse PRIMARY/SECONDARY/NONE
footprints over the nine M2 subitems, one shared Beta intensity per action draw,
and separate F/P/R implementation costs. Formal response and cost parameters
remain `NOT_CONFIGURED`; only synthetic fixtures may
exercise the structural generator. The retired scalar M2-to-M4 contract is not
used as a compatibility path, and old M4 explicitly rejects V4 artifacts.
Global execution currently stops at `M3_PARAMETER_NOT_FROZEN`. Engineering
implementation does not imply scientific or production readiness.

## Verification

```powershell
D:/Python311/python.exe -m compileall -q overall_run/src overall_run/tests
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
D:/Python311/python.exe -m pytest -q overall_run/tests/m2
D:/Python311/python.exe -m pytest -q overall_run/tests/m3
```

See `../reports/m1_m2_v2/` and `../reports/m3_v2/` for implementation,
contract, test, and rerun reports.
