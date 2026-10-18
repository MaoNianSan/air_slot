# Production PRE CLI Contract

```text
python -m model.PRE.cli inspect-source --dataset data1_2019 --source metar --raw-root <path>
python -m model.PRE.cli canonicalize --dataset <id> --source <family> --raw-root <path> --max-rows <n> --max-files <n>
python -m model.PRE.cli build-episodes --dataset <id> --canonical-root <path> --max-episodes <n>
python -m model.PRE.cli publish --dataset <id> --canonical-root <path> --max-episodes <n>
python -m model.PRE.cli smoke-real --data1-root <path> --data2-root <path> --max-rows <n>
```

Every command returns stable JSON and exit code 0 on success, 1 on contract failure, 2 on configuration/argument failure. Raw roots are never output roots. Resume requires exact manifest identity.
