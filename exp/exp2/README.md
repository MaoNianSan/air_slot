# exp2

Point collapse and lineage shuffle are evaluation-only transforms over frozen M1 scenario
artifacts. They preserve source hashes and per-target marginals.

Current status (2026-08-24, Development only; Path B assumption grounding active):

- `M2_DATA2_FORMAL_CU_V2` (seven components) is bound; `P_itinerary`/`P_service` carry
  ASSUMPTION_GROUNDED literature-parameterized provenance (unit weights + 0.5/1.0/2.0 sensitivity);
  the frozen M1 Development scenario artifact is reused
  (`sha256:ca3370a3...1dfec`, `M1_PURE_INFERENCE_REUSED=TRUE`);
- temporary Development consequence analysis is completed (`EXP2_CONSEQUENCE_DEVELOPMENT =
  COMPLETED_TEMPORARY`): distributional vs point-collapse consequence distortion, strata, and the
  frozen lineage-corruption grid are recorded in `docs/results/EXP2_DEVELOPMENT_TEMP_RESULT_SUMMARY.md`;
- scenario-conditioned action comparison is available where applicable
  (`EXP2_SCENARIO_ACTION_DEVELOPMENT = COMPLETED_TEMPORARY`), labeled
  SCENARIO_CONDITIONED / NON_AUTHORITATIVE / TEMPORARY_DEVELOPMENT_ONLY;
- CU material coverage is frozen as `FROZEN_ASSUMPTION_GROUNDED`; assumption-grounded
  (non-authoritative, non-regret) 5-ANCHOR SUBSET ranking is unlocked at the full-chain gate:
  F_continuity/F_execution/F_propagation/P_time/R_operating in constructed EUR
  (EUROCONTROL 2004 EUR-basis anchor; LOW/BASE/HIGH = 0.5x/1.0x/2.0x; TOP1/EXPOST/FORMAL are
  ASSUMPTION_GROUNDED).
- `P_itinerary`/`P_service` event counts are annotated `monetary=NOT_ANCHORED` in the
  consequences parquet; their per-event monetary anchors and the complete seven-component
  monetary ranking remain human gates. Final Test remains a human gate.

No Final Test or `paper_full` Exp2 run exists; the result is development evidence only.

## 运行入口

```text
python -m exp.exp2.run --check                # 只读 preflight + 十件套 validate
python -m exp.exp2.run --resume               # 校验既有 full-Development 结果
python -m exp.exp2.run --finalize-output      # 由既有 metrics 重生成十件套
python -m exp.exp2.run                        # 正式 full-Development（128 episodes / 1769 nodes）
```

参数：`--scenario-count`（默认 250）、`--skip-scenarios`、
`--input-root`、`--scenario-root`、`--output-root`。

## 输入 / 输出

- 输入：`artifacts/experiment/full_development_inputs_v1/`、
  `artifacts/experiments/exp2/full_development_scenarios_v1/`、
  `registries/m2_data2_formal_cu_v2.json`。
- 输出：`artifacts/experiments/exp2/full_development_v1/`
  （`EXP2_FULL_DEVELOPMENT_METRICS.json`、`M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet`、
  `EXP2_FULL_DEVELOPMENT_TABLE.csv`、manifest + 十件套）。主表列
  `N episodes` 来自 metrics 的 `supported_episode_count`，无 bootstrap 时
  `95% CI` 统一写 `—`。

## 十件套清单

`exp2_protocol_manifest.json`、`exp2_variant_manifest.json`、
`exp2_split_audit.json`、`exp2_leakage_audit.json`、`exp2_parity_audit.json`、
`exp2_metrics.csv`、`exp2_summary.json`、`exp2_main_table.csv`、
`exp2_main_table.tex`、`exp2_interpretation.md`。

## 哈希绑定

冻结绑定经 `load_official_frozen_binding`；CU registry 为
`registries/m2_data2_formal_cu_v2.json`（`sha256:0fcb524c…`）；M4 ranking
registry 为 `registries/m4_eur_mapping_assumption_grounded_v1.json`
（`registry_hash=sha256:88beec33…`）。
