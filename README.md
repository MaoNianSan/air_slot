# Air Slot

Air Slot is a scientific execution repository for an event- and chain-aware
flight disruption workflow.

## Current contracts

The only PRE contract is `AIR_CHAIN_CORE_V2` with schema
`air-chain-core-2.0` and research revision `AIR_CHAIN_CORE_V2_R2`. PRE publishes
episodes, events, source-global observations, observation membership,
train-only calibration references, evidence audit, column registry, and its
manifest under `pre/output_core/<mode>/AIR_CHAIN_CORE_V2/`.

PRE does not build five-minute model grids, recurrent state, M1 tensors,
predictions, actions, or rankings. Those responsibilities begin at the M1 PRE
Adapter.

## Pipeline

```text
data -> PRE Core V2 -> M1 PRE Adapter -> M1 -> M2 -> M3 -> M4
                                                |-> overall_adv
                                                `-> part_adv
```

M1 is a single lightweight GRU distribution model with IB, OB, and TX heads.
It uses temperature scaling and fixed episode-level random numbers for joint
sampling. M2-M4 mathematical code remains separate; formal downstream runs are
blocked until their input contracts are migrated to the new M1 sample schema.

## Boundaries

- `data/` is read-only and PRE is the only raw-data reader.
- M1 reads only a published PRE Core V2 bundle, never raw, cache, or staging.
- Engineering readiness and scientific target support are reported separately.
- Generated output, cache, staging, raw data, and Parquet artifacts are not
  committed.

## Verification

```powershell
D:/Python311/python.exe -m compileall -q pre/src pre/tests pre/tools
D:/Python311/python.exe -m pytest -q pre/tests
D:/Python311/python.exe -m compileall -q overall_run/src overall_run/tests
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
```

See `pre/README.md` and `overall_run/README.md` for module boundaries.
