# exp3

Ablations are transformed copies of frozen consequence/candidate artifacts. They do not retrain,
mutate formal inputs, or imply paper eligibility.

Current status (2026-08-24, Development only; Path B assumption grounding active):

- Exp3 Development execution is completed as temporary support-boundary evidence
  (`EXP3_DEVELOPMENT_V1`: 1,824 nodes numerically evaluable; FormalA00Rate/ConditionalRate/
  ScenarioOnlyRate = 1.0; authoritative abstain on all nodes);
- the DeepSeek V2 operational reasonableness audit is completed as an auxiliary,
  evaluation-only result (`docs/results/EXP3_DEEPSEEK_V2_AUDIT_SUMMARY.md`); it does not validate
  the model and cannot alter M3/M4;
- 22 non-A00 actions carry ASSUMPTION_GROUNDED mechanism responses (G2); the
  SCENARIO/CONDITIONAL lane is READY, the FORMAL lane remains A00-only;
- CU material coverage is frozen as `FROZEN_ASSUMPTION_GROUNDED`; Exp3 variants/ablations
  (MODULE_REMOVAL_*, ROLLING, ONE_SHOT, SYNC, LAG_*) are DEFERRED_OPTIONAL by user decision
  2026-08-24 (not re-run, not in paper); the conditional ranking uses the frozen
  5-ANCHOR SUBSET in constructed EUR (F_continuity/F_execution/F_propagation/P_time/R_operating;
  EUROCONTROL 2004 EUR-basis anchor; LOW/BASE/HIGH = 0.5x/1.0x/2.0x) and is
  CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL — not causal/regret/optimal;
  `P_itinerary`/`P_service` stay event counts with `monetary=NOT_ANCHORED`; the complete
  seven-component monetary ranking and Final Test remain human gates.
- no Final Test run exists; the result is development evidence only.

## 运行入口

```text
python -m exp.exp3.run --check                # 只读 preflight + 十件套 validate
python -m exp.exp3.run --resume               # 校验既有 full-Development 结果
python -m exp.exp3.run --finalize-output      # 由既有 metrics + risk parquet 重生成十件套
python -m exp.exp3.run                        # 正式 full-Development（128 episodes / 1769 nodes / 23 actions）
```

参数：`--response-scenario-limit`、`--exp2-root`、`--input-root`、
`--output-root`。

## 输入 / 输出

- 输入：`artifacts/experiments/exp2/full_development_v1/`
  （`M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet`）、
  `artifacts/experiment/full_development_inputs_v1/`、
  `registries/m3_v2_action_response_design.json`、
  `registries/m4_eur_mapping_assumption_grounded_v1.json`。
- 输出：`artifacts/experiments/exp3/full_development_v1/`
  （`EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet`、`EXP3_FULL_DEVELOPMENT_METRICS.json`、
  `EXP3_FULL_DEVELOPMENT_TABLE.csv`、manifest + 十件套）。主表行 =
  条件 5-ANCHOR 诊断汇总（FINITE_SUPPORT_RATE /
  CONDITIONAL_TOP1_RESPONSE_AGREEMENT / GLOBAL_CONSTRUCTED_EUR_SCALE_INVARIANCE /
  PER_ACTION_CONDITIONAL_RISK_MEAN）；NOT_RUN 决策级指标不占行，原因保留在
  `exp3_metrics.csv` / `exp3_summary.json` / `exp3_interpretation.md`。

## 十件套清单

`exp3_protocol_manifest.json`、`exp3_variant_manifest.json`、
`exp3_split_audit.json`、`exp3_leakage_audit.json`、`exp3_parity_audit.json`、
`exp3_metrics.csv`、`exp3_summary.json`、`exp3_main_table.csv`、
`exp3_main_table.tex`、`exp3_interpretation.md`。

## 哈希绑定

冻结绑定经 `load_official_frozen_binding`；response registry 为
`registries/m3_v2_action_response_design.json`；M4 ranking registry 为
`registries/m4_eur_mapping_assumption_grounded_v1.json`
（`registry_hash=sha256:88beec33…`，constructed_EUR，5-ANCHOR SUBSET；
ranking 语义 CONDITIONAL_DIAGNOSTIC_NOT_PRINCIPAL）。
