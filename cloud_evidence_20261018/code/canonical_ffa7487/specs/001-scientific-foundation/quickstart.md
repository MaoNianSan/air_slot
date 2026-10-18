# Quickstart: Validate the Executable Scientific Foundation

This guide describes the validation experience expected after implementation tasks are approved and
completed. It is not an instruction to run M1-M4, experiments, full data, or Git operations.

## Prerequisites

- Python 3.11.x on Windows 10/11 or Linux x86_64.
- Use the current system/current Python interpreter directly; no virtual environment or activation step
  is part of this project.
- Install project dependencies with `python -m pip install -r requirements.txt`.
- No full raw dataset is required for the default quickstart.
- Work from the repository root; do not configure paths to legacy code.
- Treat configured data1/data2 roots as read-only inputs. Dataset profiles are loaded from
  `metadata/datasets/data1/` and `metadata/datasets/data2/`; no project file is written to raw roots.

## 1. Inspect the contracts without raw data

```powershell
python -m validation.cli contracts
```

Expected outcome:

- All registry schemas and references validate.
- The manifest hash is reported.
- No M4 raw consumer or data1/data2 pooling permission exists.
- Output status may be `PASS`, but `paper_result` remains `false`.

## 2. Exercise both adapter interfaces with fixtures

```powershell
python -m validation.cli adapters --fixtures-only
```

Expected data1 interface declarations:

- METAR temperature/wind canonicalization is declared but no raw conversion is run.
- QNH/MSLP semantics remain explicit (`QNH_NOT_MSLP`).
- Missing gust/cloud/weather code remains explicit missingness.
- True schedule and 2019 aircraft metadata capabilities are unsupported.

Expected data2 interface declarations:

- CRS schedule is declared as a reference with CRS semantics.
- actual departure/arrival/wheels/taxi fields are declared post-hoc before realization.
- aggregate passenger fields remain proxy/reference.
- trajectory and decision-time weather/flow remain unsupported.

Both adapters must retain different dataset instance IDs; no pooled output is created.

## 3. Construct a synthetic PRE node

```powershell
python -m validation.cli pre --fixtures-only
```

The fixture contains episode members/non-members and observations before/after the cutoff. Expected:

- Only legal episode members at or before the cutoff can be selected.
- Latest legal observation selection is deterministic.
- Evidence ledger and lineage are complete for every non-null scientific value.
- Unsupported/development-frozen objects have null value plus reason.
- Re-running yields identical fixture artifact bytes and identity hashes.

## 4. Run all foundation validation

```powershell
python -m validation.cli all --fixtures-only
pytest -q
```

Expected:

- Completion under 60 seconds on a normal CPU-only development machine.
- Negative fixtures for future leakage, membership, silent zero, support upgrade, raw downstream access,
  and dataset mixing are all rejected.
- M1-M4 report `NOT_IMPLEMENTED_BY_SCOPE`; no prediction, action, decision, or experiment output exists.

## 5. Inspect output separation

Only these outputs are expected:

```text
outputs/runtime/foundation_validation/<validation-run>/validation_result.json
outputs/formal/foundation_fixture/<fixture-id>/pre_state.json
```

The formal fixture identity card must include:

```text
FIXTURE_ONLY = true
paper_result = false
evaluation_scope = FOUNDATION_ONLY
```

The evaluation, paper-candidate, and manuscript-value namespaces remain empty.

## Failure Interpretation

- `FAIL`: a foundation contract or boundary check failed; it is not a failed scientific hypothesis.
- `BLOCKED`: an explicitly required frozen input is unavailable; do not invent a default.
- `NOT_RUN`: the requested check was outside configured scope or not invoked.
- `NOT_IMPLEMENTED_BY_SCOPE`: expected for M1-M4 and experiment behavior in this milestone.

Do not respond to a blocked/unsupported case by enabling a hidden fallback or importing old code.
