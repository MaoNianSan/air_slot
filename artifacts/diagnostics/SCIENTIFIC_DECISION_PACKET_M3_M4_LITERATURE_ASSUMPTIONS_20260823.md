# M3/M4 文献假设决策包（2026-08-23）

> 文献检索状态：本轮网络检索未返回可稳定引用的期刊页面/DOI 记录，因此下述
> 内容是“待文献逐条落源”的候选假设包，不作为已完成的文献证据结论。它只用于
> 约束后续实验实现，不解除任何科学 gate。

## 目的

本文件只补充实验执行所需的**文献支持的结构假设和情景参数边界**，不改变
Section 1--4、M1、M3 action identity 或 CU/RMB 科学边界。缺少可观测信息的
组件仍保持 `ABSTAIN/NOT_RUN`。

## 文献支持的可用假设

### H1：后果分解可以按运营对象组织

航空恢复研究通常把恢复影响拆成航班/飞机、机组、乘客/转机和取消等对象，
并以恢复总成本或负面影响作为综合目标。该文献共识支持当前
`F_continuity/F_execution/F_propagation/P_time/P_itinerary/P_service/R_operating`
的语义分解，但只支持“表示结构”，不支持本项目缺失组件的数值填充。

**允许：** 作为 M2 consequence representation 的 literature provenance。

**不允许：** 用文献平均值替代当前节点缺失的 itinerary/service/airline internal cost。

### H2：不确定性可用场景表示，并用期望/风险敏感函数比较

场景随机规划和动态扰动管理研究使用多场景不确定性、期望成本和风险约束来
表达未来扰动与传播影响。该假设支持 `M1 scenarios -> C -> CU` 以及
`expected loss/variance/VaR/CVaR` 的计算接口。

**允许：** Exp2 的 point/distribution/dependence sensitivity；Exp3 的
scenario-conditioned residual-risk comparison。

**不允许：** 把场景响应解释成历史干预的 causal effect。

### H3：延误后果可包含传播、吸收能力和航班特定差异

延误成本函数研究明确考虑 downstream propagation、schedule buffer/absorption
capacity 和 flight-specific delay cost。该假设支持
`F_propagation`、`F_continuity` 和 scenario response 的相对方向。

**允许：** 将非 A00 response 参数定义为带 provenance 的 LOW/BASE/HIGH 情景范围。

**不允许：** 由该文献直接推断本数据集中的动作效果大小。

### H4：乘客损失可用延误/转机/取消阈值表达，但需外部行为或政策证据

文献常把 passenger transfer、misconnection、cancellation、utility loss 或
compensation 纳入恢复目标；然而这些量依赖航司政策、票价、旅客行为和网络状态。

**允许：** `P_time` 在已有 passenger exposure reference 下使用；对 threshold event
做独立 Brier/calibration。

**仍 ABSTAIN：** `P_itinerary`、`P_service`，除非新增可审计的数据源或冻结的外部政策
参数。不得用 0 或平均 proxy 填充。

### H5：constructed RMB 可作为相对比较坐标，不是真实货币

文献支持多目标/成本加权的比较形式，但没有为本项目提供内部航司成本真值。
因此保留当前 `RMB_k = 1.0 * CU_k`，并允许 `0.5x/1x/2x` sensitivity。

**允许：** 研究映射敏感性、风险排序稳定性（在所有 support/tail gate 闭合后）。

**不允许：** 使用外部货币系数后宣称 real currency 或 monetary ground truth。

## 可用于 runner 的最小假设接口

```yaml
assumption_profile: LITERATURE_INFORMED_SCENARIO_V1
interpretation: SCENARIO_CONDITIONED_NON_CAUSAL
response_levels: [LOW, BASE, HIGH]
response_scope: [F_execution, F_propagation, P_time, R_operating]
unsupported_policy: ABSTAIN
passenger_policy:
  P_itinerary: ABSTAIN
  P_service: ABSTAIN
rmb_mapping:
  baseline: 1.0
  sensitivity: [0.5, 1.0, 2.0]
ranking_authority: DISABLED_UNTIL_M4_MAPPING_AND_TAIL_FROZEN
```

该 profile 只能用于 Development sensitivity / scenario-conditioned outputs，不能
解除当前 Exp3 formal cohort 或 Exp4 Data2 baseline blockers。

## 对当前 Exp 的影响

| 实验 | 可立即使用 | 仍不能补齐 |
|---|---|---|
| Exp1 | 已有 M1 state metrics | 无需引入 M3/M4 假设 |
| Exp2 | 场景分布、point collapse、7-component typed vector、tail-aware Brier/calibration | scalar CRPS/variogram、完整 7-component numeric aggregate、authoritative ranking |
| Exp3 | scenario-conditioned action consequence 与 support-boundary characterization | formal multi-action cohort、authoritative residual-risk ranking |
| Exp4 | Data1 bounded run/applicability、Data2 runtime/pre-replay checks | Data2 baseline predictive metrics、Data1 predictive accuracy |

## 结论

文献可以合法补足“为什么这样分解、为什么使用场景、为什么考虑传播和风险”的
方法论依据；不能合法补足当前缺失的观察标签、动作干预效果、航司内部成本或
乘客服务政策。后续 runner 应消费上述 profile 生成 `SCENARIO_ASSUMPTION` lineage，
并继续对不支持组件输出 `ABSTAIN/NOT_RUN`。
