# Air Slot

## Project purpose

Air Slot studies airline disruption recovery under delayed information. The
repository contains a raw-data preparation layer, an M1-M4 modeling pipeline,
and overall and component-level advantage analyses.

## Current repository state

The only current PRE contract is:

```text
PRE=AIR_CHAIN_CORE_V2_R2
CONTRACT=AIR_CHAIN_CORE_V2
SCHEMA=air-chain-core-2.0
M1_M4_MIGRATION=PENDING
RETIRED_PRE_REMOVED=YES
```

The existing downstream pipeline is temporarily not runnable against PRE Core
V2 until the M1 Adapter migration is completed. The three downstream entry
points stop with `PRE_CONTRACT_MISMATCH`; they do not read historical PRE
output, synthesize compatibility tables, or rebuild a retired contract.

## Architecture

```text
data -> pre -> M1 Adapter (pending) -> overall_run
                                      |-> overall_adv
                                      `-> part_adv
```

`data/` is read-only. PRE is the only raw-data reader. Published PRE artifacts
are the sole future input to the Adapter; downstream modules must not read raw
data, cache, or staging.

## PRE artifacts

PRE publishes event and chain facts, source-global Observations, partitioned
many-to-many Membership, train-only references, evidence lineage, a column
registry, and a manifest. Observation and Membership datasets are partitioned
by `source` and `observation_date`.

PRE does not produce five-minute grids, recurrent-model masks, M1 predictions,
recovery actions, or rankings.

## Scientific modules

- M1: calibrated distributional residual-risk modeling.
- M2: operational quantities and RMB cost conversion.
- M3: a frozen stochastic action-response library.
- M4: physical and decision-value screening, residual-risk scoring, and action
  ranking.
- `overall_adv`: paired overall-policy comparison.
- `part_adv`: selected module baselines and ablations.

Their mathematical implementations are retained, but execution remains blocked
until the new Adapter contract is explicit and tested.

## Environment

Use the system Python 3.11 installation:

```powershell
D:/Python311/python.exe --version
D:/Python311/python.exe -m pip install -r requirements.txt
```

No repository virtual environment is authoritative.

## PRE commands

Run from the repository root:

```powershell
D:/Python311/python.exe pre/main.py inspect-config --mode fast
D:/Python311/python.exe pre/main.py build --mode fast
D:/Python311/python.exe pre/main.py validate --mode fast
D:/Python311/python.exe pre/main.py readiness --mode fast
D:/Python311/python.exe pre/main.py report --mode fast
```

The current refactor permits verification only; it does not itself start Fast.
See `pre/README.md` for the complete contract and scientific boundaries.

## Validation

```powershell
D:/Python311/python.exe -m compileall -q pre/src pre/tests pre/tools
D:/Python311/python.exe -m pytest -q pre/tests
```

The independent validator recomputes bundle facts instead of trusting a stored
status file. A structurally passing bundle can still be scientifically not
ready.

## Runtime data policy

Do not commit generated output, cache, staging, raw data, or Parquet files.
Cleaning is always explicit. `pre/cache/` and raw data are preserved by the PRE
single-version refactor.

## Next engineering step

After the single-version gates pass, the next allowed PRE action is a Fast V2
build and finalization. Downstream execution remains disallowed until the M1
Adapter consumes V2 observations, Membership, events, chains, references, and
availability semantics directly.
