# exp4

Sensitivity candidates include hidden sizes 16/32 and rolls 5/10. Operational heterogeneity is
decomposed with development-frozen strata and `retrain_by_stratum: false`; no stratum-specific
retraining, Final Test, or formal Exp4 run is performed. Valuation and response sensitivity
numerical profiles require the M2/M3 scientific freezes, so `EXP4_READINESS` is `PARTIAL`.

## 运行入口

```text
python -m exp.exp4.run --check                # 只读 preflight + 十件套 validate
python -m exp.exp4.run --resume               # 校验既有 full-Development 结果
python -m exp.exp4.run --finalize-output      # 由既有 metrics 重生成十件套
python -m exp.exp4.run                        # 正式 Data2 baselines + Data1 bounded smoke
python -m exp.exp4.e2e_runtime --repeats N    # Exp4D development E2E repeats（P50/P95/P99）
```

参数：`--input-root`、`--output-root`。

## 输入 / 输出

- 输入：`artifacts/experiment/full_development_inputs_v1/`、data1/data2 只读。
- 输出：`artifacts/experiments/exp4/full_development_v1/`
  （HISTORICAL / LIGHTGBM / RANDOM_FOREST / STATE_AWARE_H32 四件套 +
  `EXP4_FULL_DEVELOPMENT_METRICS.json`、`EXP4_DATA1_BOUNDED_ACCEPTANCE.json`、
  manifest + 十件套）。Data2 = main evaluation；Data1 = bounded smoke only、
  non-pooled，不报 Data1 预测误差。

## 十件套清单

`exp4_protocol_manifest.json`、`exp4_variant_manifest.json`、
`exp4_split_audit.json`、`exp4_leakage_audit.json`、`exp4_parity_audit.json`、
`exp4_metrics.csv`、`exp4_summary.json`、`exp4_main_table.csv`、
`exp4_main_table.tex`、`exp4_interpretation.md`。

## 哈希绑定

冻结绑定经 `load_official_frozen_binding`；M4 ranking registry 为
`registries/m4_eur_mapping_assumption_grounded_v1.json`
（`registry_hash=sha256:88beec33…`）；baseline 契约映射
（LIGHTGBM_FAST -> LIGHTGBM、STATE_AWARE_FULL -> STATE_AWARE_H32）只出现在
`exp/exp4/formal_preparation.py` 绑定层。Exp4D 延时指标定位 operational
adequacy，与科学结论分开表述。
