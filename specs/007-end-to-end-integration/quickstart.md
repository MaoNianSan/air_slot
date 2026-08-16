# Quickstart

Use the current system Python 3.11 interpreter:

```powershell
python -m pip install -r requirements.txt
python -m airslot validate
python -m airslot smoke-synthetic --output outputs/runtime/e2e_smoke
python -m airslot smoke-real --data1-root <read-only-data1> --data2-root <read-only-data2> --output outputs/runtime/real_smoke
python -m airslot experiment-smoke --output outputs/experiments/integration_smoke
python -m airslot artifact-validate --root outputs/runtime/e2e_smoke
```

These commands do not create or activate a virtual environment. Smoke artifacts are `FIXTURE_ONLY=true`, `paper_result=false`, and `evaluation_scope=FOUNDATION_ONLY` or `SMOKE_ONLY` as applicable.

