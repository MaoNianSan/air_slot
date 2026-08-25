# exp1

Exp1 Development is frozen as `AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE`
(`sha256:a3ef4bd20048658783f36c2234df986409a7adaefbd3cca0bce722beb6ea1c46`).
The runner is orchestration only; variant construction lives in `variants.py` and deep-copies
frozen Development evidence. No Final Test or `paper_full` Exp1 run is authorized.

## 运行入口

```text
python -m exp.exp1.run --check                # 只读 preflight + 十件套 validate
python -m exp.exp1.run --resume               # 校验既有 full-Development 结果
python -m exp.exp1.run --finalize-output      # 由既有 state metrics 重生成十件套
python -m exp.exp1.run                        # 正式 full-Development（需 M1 推理可用）
```

参数：`--scenario-count`（默认 250）、`--include-sensitivity`、
`--input-root`、`--scenario-root`、`--output-root`。

## 输入 / 输出

- 输入：`artifacts/experiment/full_development_inputs_v1/`（冻结 B2 cache、M1
  checkpoint、labels）、`artifacts/experiments/exp1/full_development_scenarios_v1/`。
- 输出：`artifacts/experiment/exp1_full_development/`（`EXP1_FULL_DEVELOPMENT_*`
  JSON + 十件套）。主表当前为 cohort/stage 汇总与 scenario 覆盖率（工程事实）；
  STATE 指标在 M1 推理 gate 前保持 NOT_RUN，不占主表行。

## 十件套清单

`exp1_protocol_manifest.json`、`exp1_variant_manifest.json`、
`exp1_split_audit.json`、`exp1_leakage_audit.json`、`exp1_parity_audit.json`、
`exp1_metrics.csv`、`exp1_summary.json`、`exp1_main_table.csv`、
`exp1_main_table.tex`、`exp1_interpretation.md`。

## 哈希绑定

冻结绑定经 `load_official_frozen_binding`（model/cache/schema/support/m2/
mapping/action/response 七项）。M4 ranking registry 为
`registries/m4_eur_mapping_assumption_grounded_v1.json`
（`registry_hash=sha256:88beec33…`；Exp1 不消费 M4 ranking，仅论文引用）。
