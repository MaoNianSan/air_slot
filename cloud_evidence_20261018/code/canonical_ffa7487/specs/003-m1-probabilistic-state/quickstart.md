# M1 Quickstart

```powershell
python -m model.M1.cli train-smoke --output outputs/runtime/m1_smoke
python -m model.M1.cli infer-smoke --artifact outputs/runtime/m1_smoke/m1.pt
python -m pytest tests/m1 -q
```
