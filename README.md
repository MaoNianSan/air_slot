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
It uses temperature scaling and fixed episode-level random numbers to produce
structurally coupled scenario bundles. The M1-to-M2 V2 contract and compact
pre-action loss reconstruction are implemented and covered by targeted tests.
Formal training, calibration, resampling, and production M2 reconstruction have
not run. M3 V4 now defines the 21-action atomic-subitem response contract,
sparse nine-subitem footprints, deterministic test-only response generation,
and explicit M2 compatibility checks. The catalog includes three partial-support
aircraft recovery actions, while the legacy V2/V3 implementation is isolated
under `overall_run/src/legacy/`. M4 V2 now consumes M2 V2 sample losses and the
M3 V4 atomic-subitem artifact, preserves PRE R2/R3 evidence distinctions,
uses stable shared draw indices and weighted Mean-CVaR, assigns explicit
decision lanes, and derives Ranking@1/@2/@3/@5 from one authoritative sort.
The repository integration now includes strict M4 V2 configuration,
authoritative implementation hashing, bundle-level artifact publication,
an isolated optional evaluation interface, explicit result status priority,
and a multi-condition publication gate. Only synthetic fixture integration has
run. Formal M3 response and cost parameters remain unfrozen, so the formal
pipeline still stops at `M3_PARAMETER_NOT_FROZEN`.

```text
M4_CONTRACT_IMPLEMENTATION = READY
M4_V2_REPOSITORY_INTEGRATION = PASS
M4_V2_SYNTHETIC_INTEGRATION = PASS
M4_FORMAL_EXECUTION = BLOCKED_BY_UPSTREAM
GLOBAL_RERUN_ALLOWED = NO
```

## Boundaries

- `data/` is read-only and PRE is the only raw-data reader.
- M1 reads only a published PRE Core V2 bundle, never raw, cache, or staging.
- Engineering readiness and scientific target support are reported separately.
- Generated output, cache, staging, raw data, and Parquet artifacts are not
  committed.

## Verification

```powershell
$env:PYTHONPATH='overall_run'
D:/Python311/python.exe -m compileall -q pre/src pre/tests pre/tools
D:/Python311/python.exe -m pytest -q pre/tests
D:/Python311/python.exe -m compileall -q overall_run/src overall_run/tests
D:/Python311/python.exe -m pytest -q overall_run/tests/m1
D:/Python311/python.exe -m pytest -q overall_run/tests/m2
D:/Python311/python.exe -m pytest -q overall_run/tests/m3
D:/Python311/python.exe -m pytest -q overall_run/tests/m4
D:/Python311/python.exe -m pytest -q overall_run/tests/test_ranking_1235.py
```

See `pre/README.md`, `overall_run/README.md`, `reports/m1_m2_v2/`,
`reports/m3_v2/`, and `reports/m4_v2/` for
module boundaries, contract details, validation evidence, and rerun decisions.
