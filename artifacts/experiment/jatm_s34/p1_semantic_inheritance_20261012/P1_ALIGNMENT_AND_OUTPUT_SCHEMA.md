# P1 稿件—输出接口对账与 C07 前置 schema

状态：`P1_INDEPENDENT_REVIEW_PENDING`；运行状态：`SIX_YEAR_EXECUTION_BLOCKED`。主稿为 `Rolling_Airline_Recovery (62).zip`；路径、SHA-256 及源文件行号见 `SEMANTIC_INHERITANCE_AUDIT.md`。P1输出代码提交为 `6b5c85e0ee6b7e2a4fa4bac1770766251f73919f`；本次只对这些代码与真实小样本证据做定向核验，没有生成六年正式数值。

## 1. 已确定口径、实际接口和局限

| 模块/稿件锚点 | 主比较与科学单位 | 当前执行/导出入口 | 输出、统计与未闭合处 |
| --- | --- | --- | --- |
| E1；S5 `fig:q_boundary`、`fig:stage2_recoverability` | 年×PRE/TURN×q×objective×CU track，四视角：Delay、Delay×pax、Delay×downstream、Consequence；共同Stage-I候选/同K；Coverage分母为对应C1完整HJ V | `shared_science.materialize/export_e1_table`→`e1_shared_evaluation.run`；`shared_actions.run_actions`→`shared_statistics.e1_recovery_coverage` | Top-K、overlap、replacement、retained CU、attention gap/loss、paired Delay 增量；新增 Coverage@K、paired增量、2000次episode bootstrap、缺失原因；真实2ep/5canonical验收。全年度/所有年份未运行。Passenger与Downstream仍独立，未合成第五视角 |
| E2；S5 `tab:information_decision_summary` | CJ/HJ、HP/HJ、HM/HJ；Stage-I paired候选与Stage-II C1/C2/C3分别记录；HJ Joint为同目标 reference | `shared_populations.population_views`→`shared_actions.run_actions`→`shared_statistics.summarize_actions/recovery_loss_summary` | activation、target agreement、±5min、regret、ratio-of-sums L_rec、V与分母、episode CI；P0 的 keyed C2 不跨E1/E2合并。CJ-HJ仅能解读为现有两predictor规格，容量匹配控制尚无新版六年证据 |
| E3；S5 `fig:objective_dependence`、`fig:threshold_headroom` | Balanced/Flight/Passenger/Resource；同一合法HJ/HM paired cohort、各目标独立Joint reference；四个threshold×headroom结构 | `shared_actions.calculate_node`→`model.M3.stage2.objective_by_grid`；`mechanisms.compare`；`policy_sensitivity.evaluate_policy_sensitivity` | Joint/Marginal曲线、最优u、margin、e=J_J−J_M、action-relative差、regret、原生响应；Nominal 41/45/.25、34/47、25/75、lambda .10/.25/.50/1及fixed-slope range单因素；未展开未获批准笛卡尔积。旧 `fixed_target_difference` 保留J_M−J_J方向另名 |
| E4；S5 §5.6、Sup:309–310 | 六个独立年度、Year-local主轨/FIXED_COMMON辅助轨；年度、PRE/TURN、C3 rolling | `e4_shared_aggregate.inspect_annual_result/rolling_analysis/aggregate` | fail-closed年度输入、两轨图表source、C3首末变化与trajectory；年度结果尚无六年正式集，weather/airport grouping无批准定义，within-chain uncertainty compact字段缺失，calendar/airport-day block需有效支持。不能据简单年度表/ M5-b 宣称完成 |

共同接口：`shared_run.run` 绑定 `shared/CACHE_MANIFEST.json`、`SHARED_ANNUAL_MANIFEST.json`、`EVALUATION_COMPLETE.json`；只有来源/算法/输出哈希匹配时可恢复。`e4_shared_aggregate.inspect_annual_result` 对FAILED、PILOT、receipt mismatch、不完整Year-local/FIXED_COMMON或缺输出拒绝六年完成。Test/Final-Test访问未发生。

## 2. 参数网格身份

- 主分析：q=.10；lambda=.25、turnaround lower bound=41 min、Umax=45 min、动作{0,5,…,45}；nominal 41为原基准转来的共同回溯性政策参数，不是每个年度Train拟合值。
- Stage-I q敏感性：.05/.10/.20/.30，各年PRE/TURN分开K=ceil(qN)，所有对照同一合法候选集。
- Stage-II单因素：lambda=.10/.25/.50/1；turnaround=34/41/47；Umax=25/45/75。Umax变化同时改变努力斜率；`UMAX_*_FIXED_SLOPE`保持lambda/Umax名义斜率作为独立的range-only诊断。
- Year-adaptive Train经验参数是单列 sensitivity，不替代 nominal。四种机制结构是E3 dependence diagnostic，不与政策网格合成未要求的大笛卡尔积。
- M2 tau是Train机场turnaround reference；Stage-II ell=41是不同科学对象。Year-local CU的F尺度仍因F定义待决。

## 3. 冻结前的输出 schema 与依赖

本表用于后续 C07 阶段 receipt 设计；本轮**不修改 C07 恢复代码/schema**。完整 schema 必须与本节共同冻结，后续receipt才能避免旧数据冒充新科学身份。

| 层 | 必须保存的身份/原子字段 | 依赖 |
| --- | --- | --- |
| annual shared Stage-I | year、partition、Train checkpoint及年度tail哈希、PRE决策时间及原始T_IB可追溯指针、canonical rule/flag、stage、episode/node ID、HJ/CJ/HP/HM exact算法身份、native七维、两CU contract、支持/ABSTAIN、四筛查分数、曝光来源 | 合法年度Train/Calibration/Development、PRE、M1、M2、当前算法哈希；不能只缓存F/P/R aggregate |
| annual Stage-II action | node×representation×CU×policy×objective×mechanism，完整动作grid/每u Joint/Marginal目标、u_star、V、原生七维u响应、headroom/observed flags、physical-support标记、Joint evaluator/曲线、C1/C2/C3标记 | shared状态、M2 reference、M3 transition/Stage-II、M4；若时间坐标待决不盖章科学完成 |
| E1 | year/stage/q/view/objective/CU，N/K/候选ID与支持理由、Top-K名单、reference retained值、absolute/relative attention gap、Coverage@K分子/分母/NA、paired Delta-vs-Delay与2000CI | Stage-I compact + C1 Joint V；同一bootstrap episode occurrence在全部views中配对 |
| E2 | year/stage/q/contrast/objective/CU、C1/C2 keyed ID、CJ/HJ/HP/HM、activation、exact/±5、absolute regret、sum(Delta)/sum(V)、paired support/NA/2000CI | Stage-I & Stage-II原子曲线；不得以node mean ratio充当L_rec |
| E3 | year/stage/objective/CU/coupling/mechanism/policy，weighted marginal校验、u-grid曲线、e=J_J−J_M、relative e、margin、Joint reference regret、四机制response ledger、support分母 | 精确HM与同一节点的HJ；每结构使用自己的Joint evaluator |
| E4 | 六年分别的Year-local/FIXED_COMMON源哈希、PRE/TURN、三个regime标签、C3 epoch顺序/episode cluster、负结果与缺失、图表source、年度status | 仅聚合已通过源身份/receipt的完整Development输出；尚不合并不同Year-local绝对CU |

C07 receipt 需要绑定的算法文件：`shared_science.py`、`e1_shared_evaluation.py`、`shared_actions.py`、`shared_statistics.py`、`shared_populations.py`、`scientific_tracks.py`、`mechanisms.py`、`policy_sensitivity.py`、`exact_stream.py`、`annual_cu.py`、M1–M4调用接口。当前 `shared_run.evaluation_identity` 已把 `policy_sensitivity.py` 纳入代码哈希，定向测试验证变更会失效旧receipt。**F或TURN时间定义若更新，必须新增科学版本而非仅覆写旧receipt。**

## 4. 数值证据与尚未达到的验收

定向测试 `tests/contract/test_jatm_p1_closure.py` 与 `test_jatm_p0_acceptance.py`：26 PASS，4.74秒。P1 cached对账：2episode/5canonical/3C1、128 Coverage行、2,000次bootstrap；E1分子分母误差0，E3 sign误差0。P1 policy对账：1节点，64Joint/806Exact，92个M3目标值误差≤1.11e−16。来源hash见 `EVIDENCE_INDEX.json`；它们验证当前数值实现，**没有验证F的运营解释，也没有验证全年统计效果或CUDA**。

原2017 bounded V2的32行点估计、chunk、bootstrap保留；其CU/tail身份为legacy，不升格为Year-local论文主结果。2019 sealed及全部历史结果保持原位。每个年度的有效实证、负结果、支持分母与CI仍待合法完整Development执行。
