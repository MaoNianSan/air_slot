# Experiments Quickstart
```powershell
python -m exp.cli smoke-all --output outputs/evaluation/smoke
python -m exp.cli report --input outputs/evaluation/smoke --output outputs/evaluation/report_smoke
python -m pytest tests/experiments -q
```
