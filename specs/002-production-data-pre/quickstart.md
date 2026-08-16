# Quickstart: Production Data and PRE

Use the current Python 3.11 interpreter. Configure raw roots explicitly; do not create or activate an environment.

```powershell
python -m pip install -r requirements.txt
python -m model.PRE.cli inspect-source --dataset data1_2019 --source metar --raw-root "D:/research/air_slot/code/explore/data1"
python -m model.PRE.cli inspect-source --dataset data2_2019 --source bts_ontime --raw-root "D:/research/air_slot/code/explore/data2"
python -m model.PRE.cli smoke-real --data1-root "D:/research/air_slot/code/explore/data1" --data2-root "D:/research/air_slot/code/explore/data2" --max-rows 32
python -m pytest tests/contract tests/unit tests/integration tests/real_smoke -q
```

Expected: bounded real schemas are recognized; canonical rows are written only below project outputs; post-hoc fields are excluded from formal state; manifests are deterministic; unresolved development-frozen inputs are explicit.
