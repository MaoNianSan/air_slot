# AIR SLOT Exp 编程工作流

本工作流把论文 Section 1--4 的研究问题转换为可审计的实验代码。工作流只
改变实验表示、过程和评估协议，不重新设计论文框架，不把模型隐含值升级为
真实货币或因果动作效果。

## 0. 总体链与安全边界

```text
E -> S -> C -> CU -> RMB -> residual risk -> decision
```

动作分支只允许：

```text
A -> C^a -> CU^a
```

`RMB` 是 constructed monetary representation，不是真实货币；非 A00 动作的
响应是带 provenance 的 scenario assumption，不是 observed intervention
effect，也不是 causal treatment effect。

开发阶段强制状态：

```text
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
AUTHORITATIVE_RANKING = DISABLED
```

## 1. 阶段与门控

| 阶段 | 代码工作 | 必须产物 | 通过条件 | 停止条件 |
|---|---|---|---|---|
| W0 规范冻结 | 读取定位、Section 1--4、Exp1--4 指令 | `workflow_manifest.json` | 研究问题、variant、claim boundary 一致 | 文档冲突或定位不明确 |
| W1 合同审计 | 检查 E/S/C/CU/M3/M4 输入输出 | `contract_audit.json` | scenario、support、lineage、时间边界可验证 | 缺字段时只输出 BLOCKED，不伪造 |
| W2 共享 artifact | 生成不可变 joint state/consequence/action lineage | `artifact_manifest.json` | source hash、split、seed、cutoff 完整 | 任何未来信息或 post-hoc 信息进入构造 |
| W3 Exp1 | 只改变信息访问/历史条件 | `exp1_result.json` | CURRENT/FULL 或 NO_DIRECT_REUSE/FULL 只改变声明项 | 与 Exp2/Exp4 变量混杂 |
| W4 Exp2 | POINT/MARGINAL/JOINT 与 SCALAR/CHANNEL/COMPONENT 变换 | `exp2_result.json` | 同一 frozen source、同 action set、同 replay basis | coarse variant 偷看 fine composition |
| W5 Exp3 | ONE_SHOT/ROLLING 与 SYNC/LAG 过程比较 | `exp3_result.json` | 同一 action-response contract、明确 aging/synchronization | 写成 action causal effectiveness |
| W6 Exp4 | prediction、validity、portability、runtime | `exp4_result.json` | 指标和 denominator 冻结，Data1/Data2 语义不混 | 宣称 universal generalization |
| W7 验证与报告 | smoke、契约测试、manifest 校验 | `validation_report.json` | compile、unit、synthetic smoke 全通过 | Final Test 或 paper_full 未授权 |

每一阶段只有在前一阶段 `PASS` 后才能进入；`BLOCKED` 必须保留 reason code
并停止相应正式执行。

## 2. Exp ownership

- **Exp1**：信息角色必要性与 history/state dependence。
- **Exp2**：同一 frozen state/consequence basis 下的 representation necessity。
- **Exp3**：既有 rolling setting 下 recommendation aging 与 state synchronization。
- **Exp4**：预测 adequacy、issuance validity、Data1/Data2 portability、runtime。

Exp1 不承担 joint-vs-marginal；Exp2 不跳过 consequence；Exp3 不替换 M3；
Exp4 不承担 causal action effectiveness。

## 3. 证据层级

```text
observed prediction outcome
  > hard decision-time validity
  > controlled representation/process comparison
  > model-implied replay under frozen response assumptions
  > internal J_ref diagnostic
  > auxiliary plausibility audit
```

报告器必须把上述层级写入 manifest，禁止把低层级证据写成高层级结论。

## 4. 运行命令

开发验证只允许：

```text
python -m pytest codex_framework/tests -q
python -m codex_framework.air_slot_framework.cli smoke
```

正式 Exp、Final Test、paper_full 均不由默认 CLI 触发，必须由独立 human gate
显式授权。

### 4.1 实验运行入口（DEVELOPMENT，唯一入口）

```text
python -m exp.exp1.run --check              # Exp1 只读 preflight（含十件套 validate）
python -m exp.exp1.run --finalize-output    # Exp1 由既有 state metrics 重生成十件套
python -m exp.exp2.run --finalize-output    # Exp2 由既有 metrics 重生成十件套
python -m exp.exp3.run --finalize-output    # Exp3 条件 5-ANCHOR 诊断主表
python -m exp.exp4.run --finalize-output    # Exp4 四件套 baseline 输出契约
python -m exp.exp4.e2e_runtime              # Exp4D development E2E repeats（P50/P95/P99）
```

- 5-anchor ranking：条件 5-ANCHOR 诊断排序在 `exp/exp3/global_development.py`
  计算，经 `python -m exp.exp3.run --finalize-output` 输出主表（
  FINITE_SUPPORT_RATE / CONDITIONAL_TOP1_RESPONSE_AGREEMENT /
  GLOBAL_CONSTRUCTED_EUR_SCALE_INVARIANCE / PER_ACTION_CONDITIONAL_RISK_MEAN），
  ranking 语义 CONDITIONAL_DIAGNOSTIC_NOT_PRINCIPAL（constructed EUR，非
  causal/regret/optimal）。
- e2e_runtime：`python -m exp.exp4.e2e_runtime --repeats N`，仅 DEVELOPMENT，
  输出 P50/P95/P99 与 WITHIN_60S/120S/300S，定位工程充分性（operational
  adequacy），与科学结论分开表述。
