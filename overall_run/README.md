# overall_run

`overall_run` owns M1-M4 orchestration. M1 is the only module migrated in this
refactor; M2-M4 mathematics are retained behind explicit contract gates.

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

## Downstream boundary

New M1 joint samples contain predecessor in-block time, successor off-block and
takeoff time, taxi time, derived delays, support, evidence, overflow, and
lineage. A consumer requesting the retired movement-sample schema receives
`M2_CONTRACT_MISMATCH`. Engineering implementation does not imply scientific or
downstream readiness.

## Verification

```powershell
D:/Python311/python.exe -m compileall -q overall_run/src overall_run/tests
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
D:/Python311/python.exe -m pytest -q overall_run/tests
```
