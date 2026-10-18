# 历史结果与中间产物复用矩阵

本表是新版论文的复用边界，不修改源产物的原始标签。分类依据定义、输入、总体、尺度与代码身份；“对齐”不等于已经完成全年实证。

| 对象/证据位置 | 分类 | 允许复用的部分 | 禁止直接沿用/解除条件 |
| --- | --- | --- | --- |
| 合法 PRE 年度 episode/node/canonical 元数据；`canonical_preselection.py`、P0 cohorts | SCIENTIFICALLY_ALIGNED | 年份、时间分区、事件可用性、先身份后 support 的 canonical 规则 | 必须保留原哈希；不以 supported later node 替换 canonical；旧 128ep PRE manifest 不是全年完整性证明 |
| `YEAR_2017/M1_*`、`YEAR_2018/M1_*` 合法 N4096 checkpoint | SCIENTIFICALLY_ALIGNED | 已验证年度模型权重/normalization/calibration，继续只用本年度 | 不重训；tail/推断身份另核验；不得借给缺模型年份 |
| `YEAR_2017/TAIL_REFERENCE_V1/MANIFEST.json` | SCIENTIFICALLY_ALIGNED | 已批准本年 N4096 Train active-positive D_OB/D_TX tail | 其余年份缺失不自动从本年填补 |
| 合法年度 tail 对应的原始 M1V2Scenario | SCIENTIFICALLY_ALIGNED | 绝对 T_IB、primitive 场景、权重、observed flags、taxi ref，按源身份复用 | 这不批准尚未闭合的 M2/M3 时间解释 |
| 仅保留非负 R_IB 的 StateScenario / `shared/states/*.json` | SCIENTIFIC_DEFINITION_PENDING | PRE 有效未来事件及 D_OB/D_TX/权重仍可用 | TURN 有符号过去 T 无法单凭 R_IB=0 恢复；需 raw M1 或合法 PRE 事件连接后核对 |
| 年度 passenger/downstream/connection/taxi references | SCIENTIFICALLY_ALIGNED | 原 reference-period、来源与可用时间下的冻结 proxy references | 不能解释成实际 passenger、misconnection、传播或资源结果；不得跨年替代 |
| A 计算的 F_continuity native 及其 Train median | SCIENTIFIC_DEFINITION_PENDING | 保留为 A 的计算证据 | 不进入新版论文已闭合主结果；A/B 决议及 time-origin 校验后确定是否重新估值 |
| 其余六项 native consequence，源状态/tail/reference 有效 | SCIENTIFICALLY_ALIGNED | 对应组件的明确代理定义及原值 | 动作、状态或支持变化时仅重算受影响部分；不能一概断言全年数据充分 |
| 五年度尺度+两事件=1 的 `annual_cu.py` 结构 | SCIENTIFICALLY_ALIGNED | V5 结构与 Year-local/FIXED_COMMON 独立身份 | F_continuity 分量仍待决；“结构通过”不能解除这一科学门槛 |
| 原七项正值中位数 source scale 文件被直接当作 V5 | REVALUATION_REQUIRED | 五项 Train 连续尺度来源、支持数与哈希 | 事件项必须按已批准 adapter 取 1；不要修改源文件或2019 registry |
| 已冻结 2017-H1 FIXED_COMMON | SCIENTIFIC_DEFINITION_PENDING | 已冻结来源及非 F_continuity 分量可保留；独立辅助轨 | 若修改 F 定义，需要单独版本与科学身份确认，不能悄悄覆盖旧公共 reference |
| `annual_2017_bounded_v2_20261012/E1`（32 chunks，52,613 records，5,209 canonical） | LEGACY_ONLY | 已完成旧 CU/tail 的数值、排序、bootstrap、工程证据和 node metadata | 已记录 `LEGACY_2019_CU_REFERENCE`；不能仅改标签升级 Year-local |
| 上述旧 E1 chunk 的 state-dependent 分数，拟迁入当前年度 tail 主结果 | RECOMPUTATION_REQUIRED | 合法原 checkpoint、PRE 身份、曝光 reference | 2019 tail→年度 tail 影响场景，旧 compact 无法保证精确修补；仅必要节点重新生成状态，不重训 |
| `annual_2017_shared_validation_20261012/E1_PAIRED` | LEGACY_ONLY | 配对 bootstrap 算法/旧32点估计对账 | 统计正确不修复旧 tail/CU 身份 |
| `e2_e3_exact_development_v1/v2` | LEGACY_ONLY | 固定 Phase-5 Development 输入下的既有结果与 exact 实现证据 | `input_contract.primary_headroom` 为 Phase-5 路径；不是六年独立模型证据，旧机制诊断不能替代现四算子 |
| `annual_2017_smoke_r7` 的 8 节点 E2/E3 | LEGACY_ONLY | 小样本工程可执行证据 | 源文件虽标 DEVELOPMENT_COMPLETE，也不能当全年结果 |
| 历史 `HISTORY_MARGINAL` 64-slot permutation | LEGACY_ONLY | 历史 sealed 科学对象和兼容复现 | 不可称严格保持加权边际；从合法 Joint 构造 `HISTORY_MARGINAL_EXACT`，不覆盖历史 |
| 新 ExactWeightedMarginalDistribution + exact_stream | SCIENTIFICALLY_ALIGNED | 精确乘积数学定义、权重、D_TO 派生与有界枚举 | 仅 dependence diagnostic coupling；完整 physical invalid mass 统计未闭合；状态时间身份另核对 |
| 旧 C1=all epochs、混合 E1/E2 C2、mean normalized loss 的汇总 | REVALUATION_REQUIRED | 足够逐节点分数/曲线及 node identity | 用 P0 canonical C1、keyed C2、ratio-of-sums 重建统计；若缺 rolling/canonical states，再补受影响计算 |
| P0 e278ac5 的总体与 ratio-of-sums 算法 | SCIENTIFICALLY_ALIGNED | 已独立通过的 C1/C2/C3、paired numerator/denominator、失败门禁 | 不等于所有旧产物具备新版总体；不重复推翻 P0 |
| 旧 E3 `fixed_target_difference=J_M−J_J` 曲线 | REVALUATION_REQUIRED | 原 J 曲线、最优动作、原始差值 | 导出 e=J_J−J_M 并记录旧字段方向；无需为反号重跑 M1/M2/M3 |
| `shared_cloud_integration_20261012` 2-episode cache | LEGACY_ONLY | 缓存/恢复、P1统计变换及实现等价验证 | manifest 未绑定年度 tail；不冒充当前年度 tail 主证据；新统计也只是此缓存身份上的 probe |
| `independent_review_p0_20261012/current_tail_golden` | SCIENTIFICALLY_ALIGNED | 本年 tail 下2episode/5canonical的数值等价证据 | 只验现行 A 和现行 transition 的实现；不是 continuity 语义验收或全年结果 |
| `tmp/p1_cached_acceptance_probe.json` / `tmp/p1_policy_cached_acceptance_probe.json` | SCIENTIFICALLY_ALIGNED | 明示旧tail缓存来源的 P1输出算法验收证据 | 2ep/1node，禁止升级为年度新tail科学估计；证据字段不倒填成新运行 |
| nominal 41/45/.25 与各结构 Joint reference 的动作曲线 | SCIENTIFIC_DEFINITION_PENDING | 网格、努力项、算子定义及已验证枚举方法 | TURN signed-time问题可能影响部分曲线；完整支持确认前不得宣称论文级物理可行 |
| 旧模板动作/mitigation 百分比 M3 结果 | LEGACY_ONLY | 原模板科学对象与历史证据 | 不是当前有限 local-target recovery estimand，不移植为新 regret/行动效果 |
| 原 2019 sealed/C0 | LEGACY_ONLY | 原论文/原协议内的历史 benchmark；本次未打开其 protected 数据/结果 | 不变更、不删除、不重算，也不默认升级为新版六年证据 |
| M5-b N128 / cohort-size battery | LEGACY_ONLY | 工程链可执行或相应样本稳定性目的的既有证据 | 不能替代 JATM E4 决策价值复制；不重新执行 |
| 当前 E4 输出接口/旧年度拼接 | REVALUATION_REQUIRED | 合法年度原子结果、metadata、轨迹 | 只有完整合法年度结果才可聚合；pooled 权重、天气/机场/uncertainty 不补造 |

## 复用决策顺序

1. 先验证年份/分区/模型/tail/reference/scenario/总体身份，再判断数值可复用程度。
2. 只有尺度改变且保留七维 native 和共同支持时，可重新估值；仅有 F/P/R aggregate 不能恢复七个不同尺度分量。
3. 只有统计定义改变且保留充分逐节点数据时，重做统计；不重复 PRE/M1。
4. 只有状态身份改变才重建相关状态；不要因后果语义问题重训 M1。
5. 语义未决时保存原证据并标 pending，不自行选择让旧结果最方便复用的定义。
