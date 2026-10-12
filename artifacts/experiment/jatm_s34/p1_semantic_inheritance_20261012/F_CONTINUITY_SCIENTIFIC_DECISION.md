# F_continuity：科学待决与时间坐标

状态：`SCIENTIFIC_DEFINITION_PENDING`。本报告不采用 A/B，不修改原模型/原结果。

## 1. 明确两个候选量

记 t 为决策时点、T 为 predecessor 实际/场景 in-block 时间、S 为 successor SOBT，均在同一绝对时间系；分钟差记 x=T−t、c=S−t。tau 是 M2 的机场/全局 fallback Train turnaround reference（时长），**不是** Stage-II nominal ell=41。

| | A：剩余到达暴露超阈值 | B：相对 SOBT 的排班窗口短缺 |
| --- | --- | --- |
| 绝对写法 | A=[max(0,T−t)−tau]+ | B=[T+tau−S]+ |
| 相对写法 | A=[max(0,x)−tau]+ | B=[x+tau−c]+，x 必须有符号 |
| 原生单位 | minutes | minutes |
| 直接依赖 | T、t、tau；不读取 SOBT | T、S、tau；t 只用于统一换原点，结果对 t 不变 |
| 运营含义 | 剩余 predecessor 到达时间超过一个 turnaround-duration reference 的幅度 | predecessor 到达后留出 tau 时长，与排班 off-block 窗口的短缺 |
| PRE | x>0 时为 [x−tau]+；时间推移可使 A 下降，即使同一 T/S 不变 | x>0 时为 [x+tau−c]+；反映排班关系 |
| TURN | T≤t 时恒为 0（tau≥0） | 仍可能 >0；需要已观测 T 的历史时间，不可把 x 截断为 0 |
| 与 D_OB | 不直接依赖 D_OB | 不直接依赖 D_OB；在同一 tau 下符合 AOBT≥max(S,T+tau) 时才有 D_OB≥B 的模型可行性关系 |
| 现行局部动作下 | T、S、tau 不变，因此 A 不随 u 变 | 若采用用户给出的 B，T、S、tau 也不随 u 变；不能擅自改成相对 AOBT(u) 的第三种指标 |

两者不是单位换算：它们测量不同对象，不能以“数学可计算”自动决议。历史最早已检查代码采用 A，早期稿件另有 `[R_IB+tau−(S−t)]+`。后者仅在 PRE 未截断时等于 B；在 TURN 不应自动视为 B。

例（相对 t 分钟）：x=20、c=60、tau=41 时，A=0、B=1；x=−10、c=30、tau=41 时，A=0、B=1。此处是数学反例，不是实际实验观测。

## 2. 当前代码和真正的冲突位置

1. `model/M1/contracts.py:M1V2Scenario` 保存绝对 T 与 decision_time，`model/M1/semantics.py:derived_r_ib_minutes` 正确生成非负 R_IB。M1 sampler 明确保留过去已观测的绝对 T。
2. `validation/v2_phase5/common.py:state_set_from_m1_scenarios` 把 R_IB 写入字段名 `StateScenario.t_ib_minutes`。
3. `model/M2/consequence_service.py:native_consequence_vector` 读该字段计算 A。两个 duration 相减的单位本身是 minutes；争议主要在运营语义，不是简单“timestamp 减 duration”程序错误。
4. `model/M3/transition.py:off_block_boundary` 将该字段作为 T_IB，与 node-relative SOBT 组合。对 TURN，非负 R_IB 无法表达历史 T−t。
5. `shared_science.py` 缓存 StateScenario 和 node-relative SOBT，没有原始 M1 的 `t_ib_a00_utc`。保留 raw M1/PRE 的缓存可用于恢复；仅有此 compact payload 不足以确定过去到达时间。

## 3. 与 continuity 分开裁决的 Stage-II 时间问题

当前实现 H_A=[c+D_OB−max(c,max(0,x)+ell)]+；按同原点绝对事件解释的 H_signed=[c+D_OB−max(c,x+ell)]+，ell=41 nominal。

PRE（x≥0）相同；TURN（x<0）有 H_A≤H_signed。若 c≥ell，两者必相同；否则可能缩小 headroom，但并非每个节点都变。例 x=−10、c=30、D_OB=20、ell=41 时，两种 headroom 分别为 9、19 分钟。此例只证明可能影响，不证明全年频率。

已读 Development pilot 的两个 TURN 节点 c=48/72 均不受 nominal 41 的截断影响。需要未来获准时在合法全年 PRE metadata/场景上量化潜在受影响节点；本次没有运行全年检查或更改转移。

**建议提交两个独立选择：**

- Continuity：若论文意图是剩余到达时间超参考代理，可明确批准 A 的名称/解释；若论文意图是相对 SOBT 的排班压力，可另立版本批准 B 与新的 F_continuity Train 尺度。当前不推荐仅为兼容旧结果而优先 A。
- Stage-II：建议确认 boundary 中 T_IB 是否必须是真实事件的有符号节点相对时间。若确认，则应在科学版本下保留/恢复该坐标，并仅重算受影响动作与后果；不能把这一更改藏在 A/B 修正中。

保持最新用户决定：上述定义继续待决，不要求现在选择，不以报告生成作为批准。

## 4. 条件性影响：避免夸大重算范围

若只将 F_continuity 从 A 换成用户给出的 B，且概率、支持、headroom、其余六项尺度、动作网格和权重均不变，则对同一节点/表示/目标：

`J_new(u)=J_old(u)+b_i,R`，其中 b_i,R 与 u 无关。

因此同一节点的 u_star、action margin、V、Joint-reference action regret 可条件性保持。严格加权 T_IB 边际相同时，HJ/HM 的这一新增基线项也相同。**这不是无条件复用证明**：B 所需时间缺失会改变支持，E1 后果排序/C2/shortlist 会改变，年度 CU 和来源身份要更新；若同时修复 TURN headroom，则目标/动作亦可能改变。必须先逐项核验条件，不能强行让结果相等。

E1 的 P^D primitive 分数可保留（tail/input 身份不变时）；P^C、F 域、Top-K、attention、Coverage 与 bootstrap 要重估。E2 的 C1 身份可在支持不变时保留；shortlist/C2 重新构造。E3 保留每结构独立 Joint evaluator，不能删除负/等价结果。E4 重汇总合法年度结果；不直接沿用旧绝对 CU。

## 5. 最小重算原则

优先顺序：合法 raw M1 absolute scenarios/PRE 时间 → 恢复上下文 → 只重估受影响 native 成分与年度 F 尺度 → 重新聚合/Top-K/统计 → 必要的 Stage-II 曲线。其他六项 native 值仅在其输入/动作/支持改变时重算。

无须因 F_continuity 单项变更重训现有合法年度 M1。旧 2017 的 2019 tail 另属状态身份问题，需按已批准年度 tail 重新生成相关状态，不应与 continuity 混淆。只有上游状态、checkpoint 或实际总体无效时，才提出更上游计算需求。
