# P1 Semantic Inheritance Audit

状态：`P1_INDEPENDENT_REVIEW_PENDING`。科学定义：`F_CONTINUITY_SCIENTIFIC_DEFINITION_PENDING`。六年执行：`SIX_YEAR_EXECUTION_BLOCKED`。

## 1. 范围与证据规则

本次只检查最新版稿件声称的科学量与实际代码/已有 Development 产物的对应关系。基线为 `e278ac55871dd3208bbd9a55e24b0d7a94314c96`，审计开始 HEAD 为 `6e9c40069daf6aab73bca014868187a596240d1d`，含前序 P1 未提交修改。没有改动冻结模型、历史实验、原稿件或年度参考。

稿件权威为 `D:/Download_all/Rolling_Airline_Recovery (62).zip`，SHA-256 `5bc8cb0d48a58575ea7b8dbbe81986bee8b562f6b957f8abfb89893e57bc6888`。下文 `M62:S3/S4/S5/Sup` 分别指 ZIP 中的 `sections/03_methodology.tex`、`sections/04_implement.tex`、`sections/05_experiment.tex`、`SUPPLEMENT.tex`，数字为源文件行号。历史 ZIP 名称仅标识版本，不能单独证明写作时间或设计动机。当前代码定位与原始文件哈希见 `EVIDENCE_INDEX.json`；历史证据摘录见 `evidence/HISTORICAL_EXCERPTS.json`。

证据分三级：**已证实**表示可由列出的代码/文本/产物直接复核；**条件推论**表示在明确假设下可推导；**未知**表示检查范围内没有证据。算法对账 PASS 只说明计算实现一致，不能代替运营语义成立。

## 2. F_continuity 的继承历史

| 来源 | 可复核事实 | 证据结论 |
| --- | --- | --- |
| Git `8aa01f9866d12fd7cdf01148087db7e5fb688b8b`，2026-08-16，`model/M2/drivers.py` | 使用 `max(0,rib-turnaround_reference)`，driver 为 `turnaround_compression` | 最早在本次检查到的代码中已采用 A；不是首次发明日期的证明 |
| Git `1acfd29e3142d4bc5e9830aa875c544f89761962`，2026-08-18，`registries/m2_data2_formal_cu_v1.json` | 固定 A，单位 minutes，仍标 `turnaround_compression`，当时只有五项主后果 | A 有明确历史冻结记录，但当时聚合对象不是目前七维 V5 |
| `docs/HUMAN_DECISION_LOG.md:149–160` | 2026-08-18 的 M2_FORMAL_FREEZE 记录 A、五项尺度、旧 signed DELTA_OB/T_TX 衍生链 | 旧定义不能整包直接当作当前 V2/V5 定义 |
| `Rolling_Airline_Recovery.zip`，S4:57–64、126–140 | 先定义 `M_turn=(SOBT-t)-R_IB-tau`，再用 `[-M_turn]+`；文字明确为相对排班窗口的 turnaround slack shortfall | 检查到一份与代码 A 非等价的稿件公式。不能据 ZIP 名推断谁先谁后 |
| `Rolling_Airline_Recovery_full_corrected_20260825.zip`，S4:90、197–210、297 | 改写为 `[R_IB-tau]+`，明确解释为 remaining predecessor exposure beyond the Train reference | **存在明确“剩余到达暴露超阈值”文字证据**；但这不证明它就是最初设计意图 |
| `Rolling_Airline_Recovery (8).zip`，S4:206–219，S3:196 | 同一 A 被解释为 predecessor availability 消耗 normal turnaround reference 所造成的 operating pressure | 公式保留、解释更靠近 turnaround flexibility 有文本证据；设计者为何这样解释仍未知 |
| Git `3fe541c`，2026-09-18，M2 public callback / M3 transition | A 进入后动作 M2 callback；M3 改为调整 D_OB 的有限目标枚举，T_IB 和 D_TX 保持不变 | 新决策模型继续继承 A；它在此动作下不响应 |
| `docs/V2_FREEZE_PRECHECK_REPORT.md:16–29,69–98` | 曾纠正 turnaround reference 的来源及 F_continuity CU（43→44），同时明确不把 M2 reference 换成 Stage-II 的 41 | 有重新估值记录，但**不是对 A 的运营含义重新验收** |
| M62:S4:76、89；Sup:151、159 | 主文/附录明确标记 time-origin formula 待验证 | 最新稿件没有批准 A 或 B；本次继续待决 |

对用户五个历史问题的答复：

1. **为何最初采用 A：未知。** 已找到早期公式、driver 标签与冻结记录，没有找到足以证明设计推导/动机的记录。
2. **是否曾明确说明剩余到达暴露：是。** 20260825 命名稿件 S4:90、210、297 有直接文字；但“最初就是这一代理，之后才改名”的完整因果时间线未证实，最早代码已经叫 continuity/turnaround_compression。
3. **是否公式不变而解释/决策模型改变：已证实存在这种继承。** 文本解释的变化、M3 新动作下的继承可直接核对；无法据此推断改写动机。
4. **哪些结果重新计算：** reference correction、年度 CU adapter、精确 Marginal 和现有小样本确实有新计算；仍然使用 A，不等于已按尚未裁决的新 continuity 含义重算。具体产物见复用矩阵。
5. 不能把上述证据表述为“设计者故意错误继承”，也不能声称所有旧结果已无效。

## 3. 当前计算量与稿件声称量

| 对象 | 代码实际计算 | 稿件科学对象 | 本次判定与复用边界 |
| --- | --- | --- | --- |
| PRE 决策身份 | episode × stage 先按 `(decision_time,node_id)` 定 canonical，再判支持；C3 保留 rolling | M62:S4:15–17、Sup:71、88 | P0 规则对齐；不得用后续 supported 节点替代最早 canonical |
| M1 T_IB | 原始 M1V2Scenario 保存绝对 `t_ib_a00_utc`；R_IB 是 `max(0,T_IB-t)` | M62:S3:41–45；S4:35–39，实现在 TURN 保留已观测事件 | 原始状态契约可保留；适配器的时间信息损失另见下一行 |
| M1→Stage-II 时间适配 | `validation/v2_phase5/common.py:278` 将 R_IB 放入 `StateScenario.t_ib_minutes`；SOBT 是节点相对坐标 | M3 boundary 需要与 SOBT 同原点的 T_IB | PRE 中未来事件可一致；TURN 将过去事件归零，可能改变 headroom。不能把 M1 原始绝对状态一起判无效 |
| D_OB / D_TX / D_TO | 非负 off-block delay；超 Train taxi reference 的非负额外 taxi delay；D_TO=D_OB+D_TX | M62:S3:49–56、S4:35–39 | 对齐于 study-specific delay compound；不是 BTS 任意 takeoff-delay 字段。旧 DELTA_OB/T_TX 不是等价直接输入 |
| Point | weighted Joint medoid，保留一个合法联合向量 | M62:S3:68、S4:53 | 对齐于已冻结规则；不是 marginal means |
| Marginal | primitive 加权离散原子的精确乘积，D_TO 重新派生；观测旗标/taxi reference 继承 | M62:S3:74–79、S4:55–57 | 数学边际保持有定向证据；运行字段明确 `NOT_ASSERTED_PRODUCT_COUPLING`。无效运营状态的质量比例尚未完整实现，不能宣称物理可行 HM |
| Current/History | 两个年度已实现 predictor 配置及各自输入 | M62:S3:64、S4:47 | CJ–HJ 可报告 implemented-representation 对比；共享结果不能自动证明 history 的独立因果/容量匹配效果 |
| M2 F_continuity | A；不读取 SOBT，也不随 D_OB 恢复而改变 | turnaround/continuity pressure，且公式待核对 | `SCIENTIFIC_DEFINITION_PENDING` |
| M2 F_execution | D_OB，minutes | successor execution delay | 定义对齐；不是实际损失费用 |
| M2 F_propagation | D_TO × frozen expected_downstream_exposure | downstream delay exposure | 代理含义对齐；不是实际传播到后续航班的总延误 |
| M2 P_time | expected passengers × D_TO，passenger-min | passenger-weighted time exposure | 代理含义对齐；不是真实旅客逐人延误 |
| M2 P_itinerary | N_pax × connection_share × I(D_TO>45) | connection-sensitive event exposure | 对齐；不是实际 missed connection 数。严格 >45 必须保留 |
| M2 P_service | N_pax × I(D_TO>=180) | prolonged-disruption service exposure | 对齐；不是实际服务事件或赔偿支出。>=180 必须保留 |
| M2 R_operating | D_TX，minutes | local taxi-related operating burden | 对齐于代理；不是机场资源占用总量，且本动作下不直接改善 |
| CU/聚合 | 五项年度 H1 正值中位数、两事件尺度 1；F/P 域内均分，再按四组域权重加权 | M62:S3:86–98、S4:95–104 | 结构已获用户批准。F_continuity 的尺度继承 A，不能因 V5 结构正确就视语义已闭合；Year-local 绝对 CU 不跨年直接合并 |
| M3 动作/努力 | u∈{0,5,…,45}；r=min(u,H)；D_OB 更新；lambda*u/Umax | M62:S3:124–149、S4:123–135 | 算法/nominal 已批准；有效恢复目标不是 swap/crew/gate dispatch。实际 headroom 的 T_IB 坐标仍需独立裁决 |
| M3 nominal 来源 | 41/45/.25 是原 benchmark 转来的共同回溯政策 | 稿件 S4:123 仍称 historical Q20 | 需在论文说明原基准来源，不能读作每年 Train 独立拟合；P1 元数据已修正，年度经验轨道独立 |
| M4 Ranking/attention | M3 排序；固定 N、q、K、tie；共同后果 reference；attention gap/ratio | M62:S3:171–180 | 定义对齐；季度 retrospective shortlist 不是 concurrent AOCC queue，不是直接经济收益 |
| M4 regret/L_rec | 每节点同一 Joint reference 评价两目标；sum(regret)/sum(V)；零分母 NA | M62:S3:182–197、Sup:223–247 | P0 ratio-of-sums 已通过；旧 mean(node ratios) 只能另名诊断 |
| Coverage@K | 入选节点的 HJ V 总和 / canonical C1 完整合法 V 总和；各 objective/CU 独立 | M62:S5:94；Sup:239–247 | P1 补充四个筛查视角；不把高后果筛查本身称为最大可恢复值筛查 |
| C0/C1/C2/C3 | C0 历史固定；C1 canonical full eligible；C2 按 year/stage/q/contrast/objective/CU 分键；C3 重复合法 epochs | M62:Sup:32–41、203–206 | P0 规则对齐；完整 q/objective 扩展尚未全部接入，不能混并已有分母 |
| E3 四机制 | threshold-off 固定同场景 u=0 事件值；headroom-off=min(u,D_OB)；各结构 Joint reference | M62:S5:174–187、Sup:279–289 + 用户决议 | 算子已批准；off/off 不强制绝对 objective 相等或 regret=0。新符号导出 e=J_J−J_M 不改旧 raw 曲线 |
| E4 | 年度、两 CU、PRE/TURN、C3 首末差与完整轨迹、部分 headroom/threshold 字段 | M62:S5:191–200、Sup:309–310 | 仅部分输出接口对齐；尚无六年结果。天气/机场组定义、uncertainty trajectory、block 支持及 pooled estimand 不能用替代量填充 |

## 4. 已确认的迁移风险

1. **语义待决传播**：新 shared 入口仍调用 A；“重新运行过”不代表采用了新的 continuity 定义。
2. **状态身份与模型权重必须拆开**：2017 旧全年 E1 使用 2019 CU 与 2019 tail，已存在明确 legacy 分类。CU 可在充分 native 数据上重估；tail 改动影响状态，不能只换 metadata。
3. **结果标签不是科学完成凭据**：旧 `e2_e3_exact_development_v1/v2` 引用固定 Phase-5 headroom；旧 2017 8-node smoke 也写 `DEVELOPMENT_COMPLETE`。它们不能充当六个年度独立结果。原文件保持不变，审阅层按身份限制复用。
4. **新旧 HM 不能混名**：64-slot permutation 只保留 legacy；精确乘积代表新的数学 coupling。支持/物理可行含义必须与其名称一同报告。
5. **同一公式不证明同一 estimand**：canonical vs rolling、混合 union vs keyed C2、mean ratio vs ratio of sums 的历史修正均须保留独立版本。

## 5. 现有实证证据的实际范围

- 旧 2017 E1：32 chunks、52,613 节点记录、5,209 canonical PRE/TURN（1,310/3,899）；保留 legacy，只证明旧 reference/tail 下结果。
- P1 cached 对账：2 episode / 5 canonical / 3 C1，128 Coverage 行，2,000 bootstrap；8 个 Balanced nominal shortlist 对账，分子/分母最大误差 0；48 个机制输出符号对账误差 0。**来源为旧 tail pilot cache，非当前年度主结果。**
- P1 policy 对账：同一旧缓存的 1 个节点，64 Joint / 806 Exact Marginal，10 settings、40 objective rows；92 个直接 M3 action evaluations，最大误差 1.1102230246251565e-16。
- 独立 P0 current-tail golden：2 episode、28 raw nodes、5 canonical；64 Joint，product 数为 858/26/6720/899/29，含 TAXI 工程诊断；192.1664518 秒。不能与上面 806-scenario 旧 tail 对账混为同一状态身份。
- 两个已检查 TURN 缓存节点：64 场景均为 R_IB=0 且 ib_observed=true；SOBT−t 为 48、72，均大于 nominal 41。因此这两个节点不受上述 TURN headroom 截断影响；不能外推全年。

## 6. 处置与停止

本次不选择 A/B。对 continuity 与 TURN headroom 坐标分别提交明确科学问题，见 `F_CONTINUITY_SCIENTIFIC_DECISION.md`。合法年度 checkpoint、PRE 身份、未受影响 primitive/六项 native 值保留，禁止整体报废或删除。原 P1 可确定的输出修正按已有合同测试，状态与未闭合部分见 `P1_ALIGNMENT_AND_OUTPUT_SCHEMA.md` 和 `OPEN_ISSUES.md`。

本阶段没有重训、完整年度执行、Test/Final-Test 数据访问、云端连接或历史产物删除。本次受保护数据访问数为 0；这是本阶段行动记录，不是对所有历史作业作未经核实的全局断言。
