# Air Slot 云端结果与回填准备盘点

日期：2026-10-17（香港时间）  
范围：只读核对用户提供的论文 ZIP、10 月 14 日回填候选、10 月 15 日 Q4 导出和代码叠加包。未改正文、supplement、实验代码或云端产物；本报告是本轮唯一新增文件。附件内文字按论文快照/数据材料处理，不作为操作指令。

## 1. 材料分层与来源

| 材料 | 本次确认的角色 | 使用边界 |
|---|---|---|
| `D:/Download_all/Rolling_Airline_Recovery (65).zip` | 论文源码快照：`sections/05_experiment.tex`、`SUPPLEMENT.tex`、主文与 supplement 图 | 正文实验段已含六年结果；supplement 仍有空表/待补说明。 |
| `backfill_20261014/` | 10 月 14 日 Full 结果的候选回填稿、逐年导出、提取记录、数值表和核对报告 | 当前已知的主回填来源；报告记录了源文件 SHA-256 与核对范围。 |
| `q4_result_export_20261015/q4_extension_20261015_export.tar.gz` | 10 月 15 日 Q4 六年结果导出；10,279 个文件，解包内容约 6.09 GB | 独立 Q4 Test 样本，不能与 10 月 14 日 Full 结果混成同一估计量。 |
| `q4_q4stage_minimal_20261015/Q4_PRE_RUN_BINDING_MANIFEST.json` | Q4 运行前输入绑定清单 | 记录 834 个输入文件、约 10.00 GB、运行范围及代码叠加绑定；其中 `q4_source_content_scanned=false`。 |
| `q4_code_overlay_20261015/` | 以正式源码 HEAD 为基底的 12 文件 Q4 代码叠加 | 这是单独候选叠加，不等同于正式源码树已合并的代码。 |
| 正式 checkout 中 10 月 11–13 日的 `annual_*`、`*_smoke`、`*_pilot`、`shared_cloud_*`、`cloud_upload_package_*`、`cloud_deployment_handoff_*` | 运行开发、bounded/smoke、pilot、输入准备和交付准备材料 | 是 Full 前的工程/准备阶段，不作为六年结果回填源。上传包清单记录 `network_transfer_performed=false`、`scientific_execution_started=false`。 |

10 月 14 日报告所载 Full 结果根为 `D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013/`，服务器为 `ubuntu@134.175.205.112`；报告记录 snapshot `583f2c12`、patch chain `d1c72a7`/`ffa7487`、单一 driver `full_chain.sh`，且该轮 `final_test_access_count=0`。这些是已有报告中的 lineage 记录，本轮没有重新连接云服务器或重算原始数据。

云端时间线分层为：R6 Pilot 与 R7 Calibration 是先前阶段；R8 是 10 月 13–14 日完成的六年 Full Development；10 月 15 日 Q4 则是更晚、单独的 Test 窗口。Full snapshot README 记录 R8 的 10,536 个文件 SHA-256 校验全部通过、R6/R7 为分立归档；并说明 snapshot 本身“未生成论文表、未做科学分析”。本地 `backfill_20261014/` 才是随后生成的论文数值提取/回填候选。旧 `cloud_deployment_handoff_20261013/` 的 `TEST/FINAL-TEST` gate 是那个交付时点的历史状态说明，不覆盖之后归档的执行清单；正式回填以具体运行 manifest、split 和 access count 判定。

Full snapshot 也包含 `artifacts/paper_results_v2_final_test/` 等较早版本遗留产物，README 将它们与 `full_20261013` 分开列为 legacy files。本轮未将其并入 S34 当前结果；若要复用，需另做版本、split 与 manuscript lineage 对照。

## 2. 10 月 14 日 Full 结果：正文的主要回填已经存在

### 2.1 六年支持量

以下数值来自 `backfill_20261014/numbers.md` 和逐年提取记录；`K=ceil(0.10N)`。Stage-II eligible 与 annual HJ cohort 是不同分母。

| 年份 | PRE N | TURN N | PRE K | TURN K | Stage-II eligible | HJ cohort | E3 paired rows |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017 | 1,310 | 3,899 | 131 | 390 | 5,209 | 521 | 4,168 |
| 2018 | 1,345 | 3,873 | 135 | 388 | 5,218 | 523 | 4,184 |
| 2019 | 1,252 | 3,888 | 126 | 389 | 5,140 | 515 | 4,120 |
| 2020 | 675 | 4,053 | 68 | 406 | 4,728 | 474 | 3,792 |
| 2021 | 1,297 | 3,930 | 130 | 393 | 5,227 | 523 | 4,184 |
| 2022 | 1,422 | 3,884 | 143 | 389 | 5,306 | 532 | 4,256 |

### 2.2 正文已回填的结果范围

- **E1 screening：** Delay 相对 Consequence shortlist 的 `L^att` 为 PRE 0.101–0.184、TURN 0.107–0.181；增加 passenger exposure 可回收部分损失，downstream exposure 与 Delay 的差在各年 stage 比较中不超过 0.003。
- **E2 信息表示：** HM–HJ 改变 1.3–3.8% shortlist positions，`L^att=0.0006–0.0026`，但 Stage-II `L^rec=0.085–0.125`；HP–HJ 改变 84–89%，`L^att=0.4134–0.5291`、`L^rec=0.8963–0.9814`。Point-minus-Marginal 是另一个配对 common-support 对比，不能当成 HP–HJ 的算术分解。
- **E3 objectives：** HM–HJ exact-target agreement 约 0.547–0.772；Passenger emphasis 的 agreement 最低，Resource emphasis activation 最低（0.631–0.835）。
- **E4 ladder：** 六年结果均到达 N-grid 上界；报告允许的解释是“在已测网格内未找到稳定边界”，不支持“4096 已足够”。

10 月 14 日报告还记录：18/18 任务 PASS；引用数值检查 68/68 通过；六年 canonical candidates 的 full-support 条件满足率为 100%；E2 reference recoverable value 与 E3 Balanced/HJ 汇总一致；HJ cohort 大小与 Stage-I shortlist capacity 一致。这里复述的是已归档核对结论，并未在本轮重跑 checker。

### 2.3 必须保留的结果边界

1. `E2_E3_SUMMARY.e2.stage1_rows` 有标签错误：虽然写作 `HISTORY_MARGINAL_EXACT`，实际 shortlist 是 legacy Delay 对 Consequence。不可把这些行报告为 HM–HJ Stage-I；使用 `information_value.CROSS_STATE_DEPENDENCE` 的配对 common-support 结果。错误行只保留作追溯。
2. `E3_MECHANISM_DIAGNOSTICS` 在 fully-supported reference cohort 上全部是 `UNCHANGED`，不能充当 threshold × headroom ablation，也没有 component-level action-response ledger。
3. 全 eligible population `C_1` 上的 Coverage@K 与 priority–recoverability association、matched-capacity temporal attribution、within-chain rolling epochs `C_3`、逐节点 exclusion ledger 仍未完成。不得把空值补成 0，也不得从 HJ shortlist 推到全 eligible population。
4. `L^rec`、CU 和 recoverable value 是模型定义下的相对/归一化量，不等同于真实航空公司成本节约或货币损失。

## 3. 用户附件与现有候选稿的关系

- 附件 `main.tex` 与本地回填候选中的 `main.tex` 字节一致。
- 附件 `sections/05_experiment.tex` 有 112 行、没有 pending marker；与 `backfill_20261014/paper/sections/05_experiment.tex` 的差异只有两处图路径。附件 `figure5.1.pdf`、`figure5.2.pdf`、`figure5.3.pdf` 的 SHA-256 分别与本地回填候选的 `figure_s5_1_q_boundary.pdf`、`figure_s5_2_information_layers_v2.pdf`、`figure_s5_3_objectives.pdf` 完全一致。因此正文结果文字和对应图内容已经对齐；差别是打包命名。
- 附件 `SUPPLEMENT.tex` 仍保留空的六年 support ledger 和 E1–E4 “will contain”段落。本地 `backfill_20261014/paper/SUPPLEMENT.tex` 已有填入的 support ledger、E1 年度表与 q-grid、E2 paired support/detail、E3 objective 表、E4 ladder 表及审计/限制段落。故主要待回填工作在 supplement；不需要把同一组 Full 数值重复写进正文。

建议从现有 Oct 14 candidate 迁移 supplement 内容时保留它的明确范围：E1 的 q-grid 表是 2019 illustrative profile，完整年度网格留在归档输出；Coverage@K、机制消融等继续标为 pending。不要把本地 candidate 的未完成项写成零或“无效应”。

回填前还要对齐 Supplement 内部关于 HM 的两组表述：前文称 weighted-marginal coupling 的最终算法、权重、容差与支持处理“pending audit”；后文却称六年 Full 使用 exact discrete product coupling、逐候选 `PASS_EXACT_MARGINAL`。后文同时标明 physical feasibility `NOT_ASSERTED`。应以六年 Full 的逐候选 audit、实际输出 manifest 和源代码身份作为唯一裁决依据，再删改过时的 pending 句或收窄解释；不得把数学 product coupling 写成可部署、物理可行的运行预测。

补充核对：本轮直接读取了 Full snapshot 中 2017–2022 六个 `EXACT_MARGINAL_AUDIT.json`。合计 45,788 条逐节点记录全部为 `PASS_EXACT_MARGINAL`，每条 `support_mass=1.0`；同时 45,788 条均标注 `NOT_ASSERTED_PRODUCT_COUPLING`。因此“待审计”是 Supplement 内残留的旧文字；统计意义上的 exact weighted marginals 已有逐节点审计支撑，物理可行性仍未建立。原始 audit 路径由 `CLOUD_BACKFILL_MANIFEST.json` 按年登记并给出 SHA-256。

## 4. 10 月 15 日 Q4 结果：新窗口、新样本、已访问 Test

代码 `q4_cohort.py` 的规则是：每年 10–12 月 service-date、按既有 containment/split 规则属于 `test` 的 episode 中，使用固定 seed 的 SHA-256 rank 选 4,096 个；9 月只作为 rotation context。下表的年度 eligible 数是 cohort manifest 记载值，E1/E2/E3/E4 使用的是每年选出的 4,096 个 episode。

| 年份 | Q4 eligible | 选中 episode | E1 PRE N | E1 TURN N | HJ cohort | E2/E3 节点 | Q4 Test access |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017 | 1,040,108 | 4,096 | 1,246 | 3,927 | 518 | 7,623 | 36,864 |
| 2018 | 1,335,516 | 4,096 | 1,386 | 3,905 | 530 | 7,672 | 36,864 |
| 2019 | 1,405,143 | 4,096 | 1,307 | 3,879 | 519 | 7,540 | 36,864 |
| 2020 | 735,863 | 4,096 | 914 | 4,043 | 497 | 8,064 | 36,864 |
| 2021 | 1,196,773 | 4,096 | 1,352 | 3,919 | 528 | 7,456 | 36,864 |
| 2022 | 1,201,193 | 4,096 | 1,457 | 3,887 | 535 | 7,519 | 36,864 |

六年合计：eligible 6,914,596；被读取的 Q4 原始行 9,486,449；选中 episode 24,576；各年清单记录的模块 Test access 合计 221,184（E1 4,096 + E2/E3 两遍各 4,096 + E4 24,576/年）。这些访问数来自清单，不是本轮新访问。

Q4 E1 在 q=0.10 的年度范围：

| Stage | Delay `L^att` | Delay+Passenger | Delay+Downstream |
|---|---:|---:|---:|
| PRE | 0.1139–0.1841 | 0.0571–0.1474 | 0.1074–0.1841 |
| TURN | 0.1070–0.1724 | 0.0644–0.1378 | 0.1055–0.1735 |

Q4 E2 的 HM–HJ `L^att` 为 0.0003–0.0034、Stage-I reassigned share 0.0101–0.0467、`A0` 0.5944–0.7649、`L^rec` 0.0685–0.1202；HP–HJ 对应 `L^att` 0.4100–0.5286、reassigned share 0.8189–0.8785、`A0` 0.1212–0.2659、`L^rec` 0.8971–0.9813。Current–History 跨年差异较大；2020 的 `L^att=0.5039`、`A0=0.0885`、`L^rec=0.9998`。这些是 Q4 Test 子样本统计，不能覆盖/并入 Oct 14 Full 年度估计。

### Q4 回填前的闭合条件

- 分年 `Q4_YEAR_MANIFEST` 与分年 E1/E2/E3/E4 manifest 标为 `TEST_COMPLETE`；但导出根 `Q4_MULTIYEAR_MANIFEST.json` 仍是 `E4_REPAIR_REQUIRED`，六年 `year_status` 仍写 `ENGINEERING_INCOMPLETE`。归档中有修复前失败记录和后续分年 E4 成功清单，尚缺一个状态一致的最终多年份根清单。
- 根清单记录 pre-run binding SHA-256 不一致：记录值 `04cb8c3a…`，观察值 `9c0277cc…`，并称 E4 repair 单独绑定。需要在回填前完成来源/状态对账。
- Q4 E2/E3 的 exact-marginal 标签同时显式写着 `physical_feasibility=NOT_ASSERTED_PRODUCT_COUPLING`；2018、2021 各有 2 个 support abstain。可报告“该算法下的结果”，不能仅凭标签写成物理可行的 dependence-only 效应；ABSTAIN 必须保留。
- Q4 E3 mechanism diagnostic 仍在 full-support reference cohort 上，诊断行的 `threshold_ablation_status=UNCHANGED`，不能填补旧报告中的 threshold × headroom 缺口。
- 六年 E4 单年清单记录 Test complete，但 evaluator decision 均为 `N_GRID_UPPER_BOUND_REACHED`，每年另有 10–19 个 `failed_instances`（合计 78，包含 `activation_rate`、`kendall_tau_b@PRE_IB` 等指标键）。E4 只能写“运行到上界，稳定边界未在本网格内确定”；需保留失败指标记录，不能写“4096 充分”。

**回填判断：** Q4 可以作为独立的 Q4 Test 窗口补充分析候选，需标清 cohort、split、实际访问记录与上述闭合项；目前不替换正文既有 Full 结果，不并池计算六年范围，也不声称为未触碰的 held-out 数据。

## 5. 代码版本与 lineage

- 正式源码 checkout：`D:/research/air_slot/code/explore`；本轮只读看到 branch `v2/paper-primary`、HEAD `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`（2026-10-13），ahead 17。工作树有大量未跟踪云端包、实验产物与图文件；本轮未清理、暂存或改变它们。
- `Q4_OVERLAY_IDENTITY.json` 记录叠加基底为同一 `ffa74876…`，创建于 2026-10-15；运行前 binding 列出 12 个叠加文件并给出 SHA-256 与 source bundle hash `1553fd99…`。主要新增入口是 `exp/jatm_s34/q4_cohort.py`、`q4_bridge.py`、`q4_year_run.py`、`q4_run.py`，另有 E1/E2/E3/E4、稳定性指标和 Section 5 Development runner 的变化。
- 这些 overlay 文件与正式 checkout 的对应源文件不同；四个 Q4 专用模块/契约测试在正式 checkout 中不存在。因此可将“HEAD + 明确 overlay”作为 Q4 运行代码身份，不应称为已经并入正式 checkout 的最新主线版本。
- Q4 cohort 选择和 runner 在 overlay 中明确指定 `split=test`，并记录 `final_test_access_count`；这与 Oct 14 Full 报告的 `final_test_access_count=0` 不是同一数据权限状态。

## 6. 回填执行顺序建议

1. **正文：** 以附件 `sections/05_experiment.tex` 为准。Oct 14 主文结果文字已回填，图内容 hash 对齐；正文不再重复插入同一 Full 数值。下一轮需校准 RQ—E1/E2/E3 与“E4”命名，并确认 Q4 是否纳入；若纳入，必须独立标明 Q4 Test 窗口、分母与 split。
2. **Supplement：** 以 `backfill_20261014/paper/SUPPLEMENT.tex` 及 `tables/` 中已有年度 support/E1/E2/E3/M5-b 表体作为迁移基准。附件现有 Supplement 的表仍空，但本地候选已填入数值；重点是迁移、核数和清理相互矛盾的旧 pending 段落，不是从零补造 E4 表。
3. **保持显式未完成：** Coverage@K 全 eligible、priority–recoverability 全 eligible、部分支持 cohort 的 threshold × headroom、component action response、matched-capacity temporal attribution、within-chain `C_3`、逐节点 exclusion ledger，以及 M5-b 未通过的 cohort-size stability criteria。
4. **若纳入 Q4：** 先对齐根 manifest 与分年 manifest、解释 pre-run hash discrepancy、冻结 Q4 overlay 的源身份；只用单独的 Test-window 表/图，不与 Oct 14 Development/full-result统计池合并。不要再访问或重跑该 Test cohort。

## 7. 本轮直接查阅的关键文件

- `backfill_20261014/BACKFILL_REPORT.md`
- `backfill_20261014/numbers.md`
- `backfill_20261014/data_backfill/CLOUD_BACKFILL_MANIFEST.json`
- `backfill_20261014/extracted/e1_six_year.json`、`e2_six_year.json`、`e3_six_year.json`、`e4_six_year.json`、`derived_and_checks.json`
- `D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013/e2e3/{2017..2022}/EXACT_MARGINAL_AUDIT.json`
- `q4_q4stage_minimal_20261015/Q4_PRE_RUN_BINDING_MANIFEST.json`
- `q4_code_overlay_20261015/Q4_OVERLAY_IDENTITY.json`
- `q4_result_export_20261015/q4_extension_20261015_export.tar.gz`（流式读取清单与汇总 JSON，未解包覆盖现有文件）

## 8. 面向 JATM 与航空运行决策领域的审稿定位

### 8.1 期刊契合度与论文应占的位置

JATM 自述聚焦航空运输业的经济、管理与政策问题，覆盖航空公司、机场和空管等行业部门，并强调连接研究与实践的分析。因此本稿与 JATM 的契合点是航空公司运行控制中心如何分配有限审查注意力、如何把运行信息映射到后续恢复决策，而不是概率表示本身的新颖性。[JATM 官方期刊介绍](https://shop.elsevier.com/journals/journal-of-air-transport-management/0969-6997)

JATM 相关论文常把方法放进可识别的运行任务中评估：例如，延误管理研究使用航空公司案例和滚动时域优化处理后续航班优先决策；多智能体研究评估决策支持方式在运行控制中的效果；ATFM 研究则呈现航班与旅客视角下的效率—公平取舍。[航空延误管理与优先决策案例](https://www.sciencedirect.com/science/article/pii/S0969699716302514)、[航空 disruption decision support 的多智能体评估](https://www.sciencedirect.com/science/article/pii/S0969699717303794)、[航班与旅客效率—公平权衡](https://www.sciencedirect.com/science/article/pii/S0969699719303011)。这些例子支持把稿件写成“航空运行决策中的信息表示与决策充分性评估”，但不支持把目前的模型指标说成已实现的航空公司收益或部署效果。

领域邻近工作还包括以运行可解性为目标的动态 aircraft-recovery decision-support 框架，以及将高价值旅客、服务水平和成本纳入是否等待转机旅客的 outbound-delay 支持工具。[动态 aircraft recovery 的运行决策支持框架](https://www.sciencedirect.com/science/article/pii/S0305054820300095)、[考虑高价值旅客的延误决策支持工具](https://doi.org/10.1007/s12544-015-0189-x)。从当前稿件的实验对象看，最清晰的差异化方向是比较信息表示对“筛查选择”和“局部恢复目标”的影响，而不是宣称求解器更快、优于实际 OCC 决策或已形成可部署工具。这里是基于有限的期刊/领域样本所作的定位判断，不等同于完整 novelty search。

**定位判断：按 research questions 组织的实证研究，JATM 适配度良好。** 论文的优势应落在航空运行中哪些问题被提出、实验如何回答、答案如何改变我们对有限审查容量和局部恢复机会的理解。模型不是卖点：它是把筛查/恢复决策、consequence 与目标选择操作化并形成可比口径的研究工具。贡献段、摘要和讨论都应以研究问题及其经验答案为主；模型细节用于说明测量定义、识别边界和可复核性，不应写成新算法或理论模型贡献。实际收益仍未被当前模型内指标验证。

### 8.2 四个审稿维度

| 维度 | 目前最强的证据与可讲主张 | 主要审稿风险 | 回填/叙述动作 |
|---|---|---|---|
| **1. 反直觉 insight** | 最有力的主线是“筛查相近不等于恢复目标相近”：HM–HJ 只重排 1.3–3.8% 的 Stage-I shortlist、`L^att=0.0006–0.0026`，但 Stage-II `A_0=0.581–0.730`、`L^rec=0.0853–0.1247`。Point 相对 Joint 的两层偏差均大得多。E1 还显示乘客暴露能改善限额筛查，而 downstream 暴露在此模型中几乎不改变 Delay 的筛查结果。 | 把“联合信息通常更好”写成泛化原则；把两个阶段不同分母的损失直接比较；把模型内比较写成真实航空公司收益。 | 将 headline 写为决策层依赖的表示充分性：相同的边际信息可能足以稳定 review shortlist，却不足以稳定局部恢复目标。用“在本 consequence model / 支持 cohort 下”限定。E1 的乘客/下游结果作为第二发现，不抢主线。 |
| **2. 理论强度** | 论文有把经验比较说清楚所需的形式定义：决策等价与参考损失分开；筛查边界和 Stage-II 最优间隙给出稳定性的充分条件；可加 consequence、相同加权边际、固定可行集和分布无关 effort 项给出 marginal sufficiency 的条件。 | 这些主要是标准充分条件和机制恒等式，不是新的一般优化定理。缺少 cutoff margin、choice gap 的直接经验检验；E3 mechanism 诊断全部 `UNCHANGED`。但模型/理论并非本研究卖点，因此风险主要在于写得太像理论贡献，或用它支撑没有测到的机制解释。 | 将模型作为研究测量工具：主文只保留读者理解 RQ 所需的决策定义；较长推导和边界条件放 supplement。不要声称 novel theorem / novel model。HM–HJ 明确称为数学 product-coupling 对照；exact marginal audit 已通过，但 physical feasibility 为 `NOT_ASSERTED`。缺少的 threshold/headroom 结果只在作者坚持提出机制性 RQ 或因果机制主张时才需要补；否则收窄机制解释即可。 |
| **3. 审稿人认可的工作量** | E1–E3 覆盖六个年度 Development 窗口、PRE/TURN 筛查、配对信息比较和四类预设 objective；另有独立 M5-b cohort-size battery。归档记载 18/18 cloud task 完成。它们的价值是回答不同航空运行决策问题并报告边界条件。 | 任务数量不是贡献；六个年度窗口不是六次随机化/独立复现。M5-b 在 2048 对 4096 的比较触及上界且有指标失败；Coverage@K 全 eligible、matched-capacity temporal control、within-chain rolling epoch、逐节点排除 ledger未闭合。机制消融的缺失不应自动被升级为核心缺口，除非论文把机制本身作为 RQ/主张。 | 按 RQ 说明每个结果为何必要、对应哪个答案、年度与样本覆盖什么异质性；不要用运行量或模型复杂度代替学术贡献。写成六个年度评估窗口；episode-cluster CI 是年内不确定性，跨年 min–max 是观察到的范围。把 M5-b 明确作为未确认稳定边界的敏感性诊断。Supplement 承担逐年支持、配对口径、CI、失败项和排除状态。 |
| **4. Experiment 呈现** | 目前材料能回答三个相连问题：Delay 是否足以支持有限容量筛查；表示压缩是否对筛查与局部恢复产生相同影响；objective 与年度/阶段条件怎样改变上述结果。Figure 5.1、5.2、5.3 分别承载 E1、E2、E3；supplement 有年度明细。 | 若按模型组件或 E1–E4 编号平铺，读者看不到研究问题与答案；正文年度 min–max 过多会淹没主结论；objective 图没有区间；E4 上界不能作为稳定性证据；目前没有经审计的个案可直观演示主发现。 | 让每个结果小节标题或首句直接回应一个 RQ。以 Figure 5.2 作为主结果图，并列两层决策差异；Figure 5.1 回答筛查问题；Figure 5.3 回答目标权重异质性。没有可审计 case 就不要编造。年度行、支持数、CI、ABSTAIN/缺失状态和 E4 诊断放 supplement。 |

### 8.3 建议采用的结果叙事

1. **RQ1：有限审查容量下，Delay 能否代表 consequence priority？哪些 exposure 带来增量？** E1 回答：Delay 有稳定的 shortlist consequence loss；Passenger exposure 收回一部分损失，Downstream 在当前比较中几乎不改变 Delay 排序；review budget 越紧，差距越明显。
2. **RQ2：信息表示对筛查和局部恢复的影响是否相同？** E2 回答：HM 相对 HJ 基本保留 shortlist，却不能完全保留 Stage-II target；HP 对两层的改变都大得多。主 insight 是“决策层决定表示是否足够”，而不是模型复杂度或表示新颖性。
3. **RQ3：上述关系如何随管理目标与运行年度/阶段改变？** E3 显示 Passenger emphasis 下 HM–HJ agreement 最低，Resource emphasis 下 activation 最低；E1–E3 年度/阶段分层结果描述异质性。M5-b 是单独的 cohort-size 诊断，六年均未在预注册比较网格内达到稳定边界，因此不能说“4096 充分”。
4. **再解释含义和边界：** AOCC 的审查排序与局部恢复目标是不同问题，不能共用单一“信息价值”结论。exact marginals 的统计构造通过 Full audit，但物理可行性未断言；Stage-I / Stage-II loss 不同量纲；`L^rec` 不是真实成本节省。模型只支撑经验比较，不应成为摘要或贡献陈述的主语。

### 8.4 本轮回填的优先闭合项

**P0（回填前必修，数据审计已闭合）：** 删除/改写 Supplement 中过时的 “final coupling algorithm ... pending audit” 句。Full snapshot 六年逐节点 audit 已核实 45,788/45,788 条 `PASS_EXACT_MARGINAL`、`support_mass=1.0`；其 identity note 说明是 exact discrete product coupling。补充材料要引用该 Full 输出及 manifest lineage，并把 comparator 定义为 mathematical product-coupling ablation。所有 dependence 结论继续限定在这一模型消融，因为 45,788/45,788 条都标注 `physical_feasibility=NOT_ASSERTED_PRODUCT_COUPLING`；不能称作物理可行运行状态或真实独立场景。

**P1（贡献定位）：** 将摘要、引言贡献段、实验标题与讨论改成 RQ→证据→答案→管理含义的顺序。把模型和理论明确降为 operationalization / measurement scaffold，不再把“统一模型框架”列作贡献。建议三个核心子问题映射 E1、E2、E3；年度/阶段异质性作为跨 E1–E3 的分层证据，M5-b 单列为敏感性诊断，不用同一个“E4”同时指代两者。

**P2（机制解释可选）：** component audit 目前支持 Passenger component score 有差异、Flight/Resource component score 不变；不能据此称 threshold 为 target 改变的唯一原因。若机制不是核心 RQ，不必让缺失的 threshold × headroom ablation 阻断核心结果回填，直接把阈值/恢复 headroom 写成可能解释并保留边界；若仍要主张已识别机制，才需相应输出与识别设计。

**P3（实验与图文映射）：** 用一段主线解释 Figure 5.2，把正文数字压到支持 RQ 答案所需的程度；完整年度 estimates、paired sample size、cluster CI、`ABSTAIN`/无支持状态放 supplement。保持 Stage-I / Stage-II 各自的 reference、分母和 support cohort。

**P4（限定外推）：** 2017–2022 是六个年度评估窗口，含 2020 极端运行期；结果支持窗口间异质性描述，但不能自动推广为跨航空公司、常规运营或实际 AOCC 部署收益。若纳入 Oct 15 Q4，先完成第 4 节所列根 manifest / source binding 对账，并作为单独 Test-window 扩展呈现。

**综合审稿判断：** 这是一篇以研究问题为主线的 JATM 实证研究，主贡献在于回答有限审查、信息表示与局部恢复决策如何相互作用，以及这些经验关系怎样随目标和运行条件变化。模型是支撑比较的研究工具，不是优势或贡献本身。数据与执行工作量充足；回填优先解决 coupling 解释边界、RQ—实验映射和结论外推，机制缺项按实际主张决定是否需要，不因理论包装而自动扩张工作量。未完成项继续显式标 pending / not established。

## 9. Full 云端代码执行机制与身份对账

### 9.1 这次 Full 实际调用了什么

原始 `full_chain.sh` 顺序调用 `full_e4.py`、`full_e2e3.py`、`full_e1.py`，逐年执行六个 Development 窗口。E1、E2/E3 都调用 `run_bounded_annual`，每年 `n=4096`、`chunk_size=64`、`bootstrap_replicates=2000`；E2/E3 对 HJ shortlist union 再进行第二遍。E4 调用 `exp.jatm_s34.e4_run.run`，其底层是 `data2/scripts/consequence_stability_battery.py` 的 M5-b cohort-size FIT/EVAL battery。它不是 `exp.jatm_s34.e4_shared_aggregate.py` 的年度异质性/rolling 分析。

### 9.2 E1–E3 的问题、操作化和输出

| 研究问题 | 代码机制 | 主要观察量 | 输出可支持的结论 |
|---|---|---|---|
| **RQ1：固定审查容量下，Delay 排序保留多少 consequence priority；乘客或下游暴露是否增加筛查信息？** | 年度 Development episode 经有界桥接构造成 canonical PRE/TURN 节点；对比 $P^D$、$P^D\times$乘客暴露、$P^D\times$下游暴露与 consequence 排序。固定 cohort、$q$ 网格和 M3 tie-break；$K=\lceil qN\rceil$。 | shortlist replacement、$L^{att}$、保留的 reference consequence；$q=0.05,0.10,0.20,0.30$；episode-cluster bootstrap。 | 在当前六个年度窗口和 consequence 度量下，Delay-only 有正的 consequence-screening loss；Passenger 暴露在紧容量下可收回一部分，Downstream 乘数在此数据/构造中大多不改排序。不是实际 AOCC 收益估计。 |
| **RQ2：信息压缩对筛查和局部恢复是否同样充分？** | 先流式评分全部 canonical 节点；Stage-I 以 HJ 的 $q=0.10$ shortlist 作参考。Stage-II cohort 是该 shortlist union 与完整概率支持的交集，再对相同 reference cohort 比较 Current+Joint/HJ、HP/HJ、HM/HJ。HP 是 weighted point/medoid；HM 是保留各 primitive weighted marginal 的 exact discrete product coupling；HJ 保留 joint scenarios。 | Stage-I shortlist displacement、$L^{att}$；Stage-II exact target agreement $A_0$、$A_5$、activation、$L^{rec}$。Stage-I 与 Stage-II 分别用自己的 reference/cohort，不能把两层 loss 当同一尺度。 | 最强反直觉结果：HM–HJ 的筛查 shortlist 几乎相同，但 Stage-II target agreement 只有约 0.58–0.73，且有正的 reference recovery loss；HP–HJ 两层都差得更多。说明同一表示的“足够性”依赖它支持的决策层。它是模型内/支持 cohort 结论，不是依赖的物理因果效应。 |
| **RQ3：表示差异随管理目标和年度/阶段如何变化？** | 固定 HJ reference cohort；对 Balanced、Flight、Passenger、Resource 四种预设 CU weights 分别精确枚举 HM 与 HJ Stage-II 动作。E3 提供 objective × year 结果；PRE/TURN 的直接分层主要来自 E1。年度不是随机化重复。 | objective-specific agreement、$|\Delta u^*|$、activation、zero-recoverable-value share；E1 的 stage-specific 与各模块的 annual summaries。 | Passenger 权重下 HM/HJ agreement 六年均最低；Resource 下 activation 最低。异质性以现有按年或按阶段输出描述，不推断缺失的跨阶段/within-chain 对比，也不称为独立因果实验或疫情效应。 |

**支撑实现，而非论文算法贡献：** M3 Stage-I 用固定 top-$K$ 规则；Stage-II 在有限 5 分钟动作网格上 exact enumeration，lower-$u$ tie-break；M4 用共同 reference objective 评估 comparator。解释性结果应围绕 RQ、比较对象、固定条件、决策指标和支持范围写。模型与定理提供测量口径/比较语言；不以模型新颖性、求解器优势或部署能力作为贡献。

### 9.3 “E4”名称必须与云端任务名分开

正文 Section 5 候选将 E4 称为年度及 PRE/TURN 异质性；这种描述可以从 E1–E3 的年度/阶段化输出形成，但 Full 云端 `full_e4.py` 实际运行的是 M5-b cohort-size stability battery。正式代码里的 `e4_shared_aggregate.py` 才读取独立 annual shared-run 收据、汇总 chart rows 并计算 within-chain rolling；当前查阅的 Full 结果目录没有其 `E4_YEAR_MATRIX.json` / `SECTION5_CHART_SOURCE.json` 成品，也没有六年 shared-run receipts。因此：

- 论文可以保留由 E1–E3 年度/阶段结果支持的描述性异质性，但应写明这是分层综合，不声称存在已完成的独立 rolling/E4 shared run；不得回填未生成的三阶段汇总、阈值/ headroom 分层或 within-chain trajectory。
- M5-b 另列为样本量/模型队列敏感性诊断。协议的候选稳定性比较是 $N=128$–$2048$ 对照 $4096$ reference；若任一绑定指标在 $2048$ 对 $4096$ 时 FAIL，结果为 `N_GRID_UPPER_BOUND_REACHED`，4096 不自动等于充分。Full 六年均触及此状态；各年 evaluation failure 为 11、11、11、11、12、11，另有 2020 的 9 个 fit-side failures。不能把 M5-b PASS/完成运行写成稳定性通过。

### 9.4 云端源代码身份

Full 预检的 `git_head=583f2c12` 是云快照的 Git 基线标记；同一 PRECHECK 记录了 patch chain `8cc7a1b7…` 与 `1d3ba5d3…`，以及两份最终修订源码 SHA。`PATCH_RECORD_2_20261013.json` 明示该 worktree 是“snapshot 583 + patch 8cc（d1c72a7）+ patch 1d3（ffa7487）”，且第二补丁在 Full 执行开始前生效。两个变更只触及 M2 年度输入/构造上下文（训练尺度事件字段、2019 construction identity），没有修改 E1–E4 的比较算法。故结果 lineage 应引用**基线快照加两补丁**；summary 中的 `git_head=583` 单独不足以表示运行态，当前 `ffa7487` 也不能取代云端 PRECHECK/patch 记录。Q4 的 `ffa7487 + 12-file overlay` 是另一个独立运行身份。

## 10. Output-to-paper 映射和建议回填顺序

### 10.1 正文：RQ 是主干，实验标签是回答工具

1. **先在设计段固定三个子问题。** RQ1 对应有限审查与 exposure 增量（E1）；RQ2 对应 temporal/probabilistic representation 在筛查与局部恢复两层的充分性（E2）；RQ3 对应 objective preference，并以年度/PRE–TURN 分层展示异质性（E3 + E1–E3 分层结果）。不再把 M5-b 称为论文 E4，也不把“有四个模块”当成贡献。
2. **结果首段用研究发现而不是算法。** E1 的 $q_0=0.10$：Delay 在 12 个 year-stage 对比均有正 loss；Passenger 将 loss 降低约 6–45%（PRE）、20–38%（TURN）；Downstream 与 Delay 的绝对 loss 差不超过 0.003。写成这组结果下的增量筛查信息，不写成全行业普遍规律。
3. **把 E2 放在核心 insight 位置。** HM–HJ 的 shortlist reassignment 1.3–3.8%、$L^{att}=0.0006$–0.0026；但 $A_0=0.581$–0.730、$L^{rec}=0.0853$–0.1247。Point compression 对两层的扰动明显更大。清楚说明两个 decision layer 分母及参考不同，并把 product coupling 限定为数学消融。
4. **E3 回答目标依赖，不宣称识别机制。** 保留 Passenger agreement 最低、Resource activation/zero-$V$ 比例的结果；median $|\Delta u^*|=0$ 但 changed cases 的均值更大，说明分布有质量堆在零。阈值 × headroom ablation 仍未识别，不从现有 diagnostic 推断唯一机制。
5. **理论只做解释框架。** 正文给读者足够理解 RQ 的 decision-objective/指标定义；充分稳定条件及推导放 Supplement。没有直接估计 cutoff margin/最优动作 gap 前，不把充分条件写成 empirically confirmed mechanism 或新定理贡献。

### 10.2 Supplement：完整记录结果、口径、缺项和复核身份

- 保留按年 support matrix、E1 q-grid/年度 CI、E2 paired support 与两层分母、E3 年度×objective 明细；逐表标 output 文件、cohort、reference、统计单位和 bootstrap 口径。
- 完成 exact-marginal audit 文字对账：把“算法仍 pending audit”改成 Full 六年 45,788/45,788 support audit PASS；同时保留 `NOT_ASSERTED_PRODUCT_COUPLING`，不把统计边际保持等同于物理可行 joint state。
- 单独保留 M5-b cohort-size 表及各年失败数/状态，说明 4096 是 reference 且边界未确定；与 Q4 的 E4 状态分开，不合并失败数。
- 删改已被填表取代的旧承诺，例如“E4 will report…/before final submission supply six-year E1–E4 tables”等；改写为已经有输出的年度描述与仍未完成的 rolling/coverage/threshold-headroom 内容。保留真正的 `PENDING`、`NOT_RUN`、`ABSTAIN`。
- 补上 Full 源身份链（snapshot + patch hashes）、每个输出 manifest/summary 的 run identity；把 Test Q4 单列，根 manifest/source binding reconciliation 完成前不进入主分析。

**建议执行次序：** 先校正文内 RQ/E4 命名和结论措辞；再清理 Supplement 里“已填结果仍称待填”的冲突段落；最后逐个表格对照原始 JSON/manifest 与图表数字、脚注和引用。当前阶段完成了机制与 output 审计及回填蓝图，未改 `main.tex`、正文 `.tex` 或 `SUPPLEMENT.tex`，也未运行实验或测试。

## 11. Section 5 逐节回填蓝图（本阶段不改论文 TeX）

### 11.1 主文建议顺序

Section 5 应回答三个经验研究问题；E1–E3 是回答问题的比较设计，模型与求解规则是测量和操作化工具。

1. **RQ1：有限审查容量下，Delay priority 保留多少 consequence-based screening value？** 保留现有 q=0.10 结果和 Figure 5.1；段落先给 Delay 的正 loss，再给 Passenger exposure 的部分补偿及 Downstream 的近零增量，最后用 q-grid 说明容量放宽后差距收窄。把结论限定在六个年度窗口、当前 consequence 构造与 review boundary，不写成真实 AOCC 收益或行业普遍规律。
2. **RQ2：表示压缩对 screening 与 local-recovery targeting 是否同样充分？** 这是 Section 5 的核心发现，应紧接 RQ1。用一段交代 HJ reference cohort，随后报告 HM--HJ 与 HP--HJ 的 paired contrast、Figure 5.2 和 Stage-I/Stage-II 各自的分母与支持范围。突出反直觉次序：HM 几乎不改 shortlist，却明显改变局部恢复目标；HP 在两层都产生更大变化。HP--HM 的 paired increment 保持为独立配对估计，不从两行 HJ contrast 相减，也不称作可加损失分解。
3. **RQ3：HM--HJ 的恢复决策差异是否依赖管理目标，并在年度/阶段输出中呈现怎样的变化？** 用 Figure 5.3 说明四类 objective 下的 agreement/activation；再用一两句汇总 E1–E3 已有的年度及 PRE/TURN 分层范围。说明年度是六个评估窗口，不是随机化重复。将“median target shift 为零、changed cases 的 shift 更大”作为分布形态描述，不包装为新机制。
4. **末段列明稳健性与解释边界。** M5-b 用全网格上界未达到稳定边界，应单列为 cohort-size sensitivity diagnostic，而非论文的“E4 heterogeneity experiment”。Section 5 可用一句话报六年均为 `N_GRID_UPPER_BOUND_REACHED`；网格、失败指标和年度状态留 Supplement。若版面紧张，主文移入 limitations，但不能将其改写为样本量充分性证据。

### 11.2 现有 Section 5 的具体处置

- 开头的“four related questions”和“E4 describes annual and PRE/TURN heterogeneity”改为三个 RQ；把年度/PRE–TURN 异质性说明为 E1–E3 的分层结果，把 M5-b 标成独立敏感性检查。删除暗示已完成独立 rolling E4 的措辞。
- HJ reference-cohort 的六年恢复机会表可移至 Supplement；正文保留一条 cohort 定义和 82--92% positive-target / 中位数范围作为 Stage-II 解释背景即可。这样不会让描述性基线表抢占 RQ2 的 paired information contrast。
- Component audit 当前可作为构造内的描述性证据，但主文的“provides a model-specific explanation”容易被读成已识别机制。若保留，应改成“component accounting is consistent with the stated nonseparable threshold term”；并同时说明 weighted-marginal coupling 是精确保边际的数学比较、未断言 product coupling 物理可行，也没有完成 threshold-by-headroom ablation。若 Section 5 需要进一步收紧，这一段优先移到 Supplement。
- Secondary Current--History 对比只保留为附属结果，明确它是 implemented-configuration contrast，不能单独识别“历史信息的因果效应”；核心三问不依赖它。
- Figure 5.1/5.2/5.3 分别只承担 RQ1/RQ2/RQ3；正文保留跨年范围和关键区间，逐年点估计、support、paired N、cluster bootstrap CI 放 Supplement。Figure 5.3 没有区间估计，应继续明确其为描述性年度比较。

### 11.3 Supplement 回填与清理映射

| Supplement 位置/材料 | 回填动作 | 解释边界 |
|---|---|---|
| Annual support ledger、E1 年表与 q-grid | 迁移候选表，并逐行核对六年 summary、cohort 与 CI | 按 episode cluster bootstrap；不能把年度范围称为 CI |
| E2 paired-support/detail | 保留 CJ/HJ、HP/HJ、HM/HJ 口径；区分 Stage-I reference 与 Stage-II HJ shortlist-union cohort | 两层 loss 分母不同，`A_0` 与 `L^{rec}` 只在 Stage-II 解释 |
| Exact weighted-marginal audit | 用 Full 六年 45,788/45,788 `PASS_EXACT_MARGINAL` 和 support mass 1.0 更新 pending 文字；同时保留 `NOT_ASSERTED_PRODUCT_COUPLING` | 只证明加权 primitive marginals 精确保持，不证明物理可行性或阈值机制 |
| E3 objective table / component audit | 列出 objective × year 的 agreement、activation、zero-value 与 target-shift 统计；component audit 明确标为 model-conditional accounting | 四种目标共用 HJ reference cohort；不得升级为阈值×headroom 已识别机制 |
| 现有“E4 operating period, stage, and rolling heterogeneity”段 | 改名为 E1--E3 annual/stage stratified results；仅写已有分层输出；未生成的 shared rolling、coverage、headroom 仍明确 pending/not run | 不把 Full 的 M5-b `full_e4.py` 误当 shared rolling analysis |
| M5-b cohort-size stability table | 保留六年上界状态、evaluation failure counts 及 2020 fit-side failures；与 Q4 overlay 的 E4 分开 | `4096` 是 evaluation reference，稳定边界未确定 |
| Reconciliation status / reporting fields | 删除“最终提交前补齐六年 E1--E4 表格”等已过期承诺；换成尚未闭合的 coverage、matched-capacity attribution、threshold-headroom ablation、within-chain rolling 与来源身份核对 | 保留真实 `PENDING`、`NOT_RUN`、`ABSTAIN`，不得填零或推测 |

### 11.4 本阶段结论与下一步

结果量已经足以搭出一条简洁的 RQ 叙事：容量受限筛查中的 exposure 增量；信息表示在筛查和恢复两层的不同充分性；管理目标对局部恢复差异的调节。最强的反直觉点是“筛查近似等价并不意味着恢复动作等价”，而不是模型架构或新求解器。下一步适合先按 11.1--11.2 重排并改写正文 Section 5，再按 11.3 清理 Supplement 的过期承诺和 audit 状态；进入 TeX 修改时以 `backfill_20261014/paper` 为候选副本，原始附件保持不变。

## 12. Figure/Table 呈现方案与视觉审计

### 12.1 主文图表：修订为“三图四表”候选方案

上一版“三图一表”把主文压得过于图形化。现按证据链保留三张图、安排四张功能不同的表：一张交代评估容量和分母，三张分别提供 E1、E2、E3 的数字锚点。这样呈现的是研究问题覆盖面和可复核结果，不是用表格数量替代学术贡献。

| 位置 | 建议内容 | 证据职责与呈现形式 |
|---|---|---|
| **Table 5.1 — 六年评估范围与决策容量** | 从 Supplement support ledger 提炼 | 六行年度数据：PRE/TURN 候选数与 $q_0=0.10$ 名义审查位、Stage-II 全支持 eligible 数、HJ 参考队列数。帮助读者区分筛查总体、局部恢复 eligible 总体和配对参考队列。该表交代经管决策规模，不替代结果表。 |
| **Table 5.2 — E1 名义审查比例下的筛查结果** | 从 Supplement E1 六年年度表形成六行摘要 | 按 PRE/TURN × 三个优先级列示六年等权年均 shortlist 替换比例和 $L^{att}$，括号同时列年度 min--max。年度范围不是 CI；以 Figure 5.1 的年内 bootstrap 区间呈现不确定性。 |
| **Figure 5.1 — E1** | 保留上排年度 $L^{att}$ 比较；下排改画增量差 | 上排为 PRE/TURN 六年的优先级 $L^{att}$ 点估计与 episode-cluster 95% CI。下排画 $\Delta L^{att}=L^{att}_{Delay}-L^{att}_{Delay+Passenger}$ 对 review share $q$；正值表示增加 Passenger 暴露降低损失，零线表示无增量，负值表示 Passenger 排序的点估计略高。阴影是年度 min--max，不是 CI。这比并排画两条接近的原始损失线更直接呈现“乘客信息收益取决于审查容量”。 |
| **Table 5.3 — E2 跨决策层直接对比** | 保留 HM--HJ、HP--HJ 汇总表 | 并列 Stage-I 替换率/$L^{att}$ 与 Stage-II $A_0$/$L^{rec}$ 的六年范围；说明两个阶段使用不同参考量和支持队列，范围不是置信区间。HP--HM 配对增量仍在正文文字/补充明细中单列。 |
| **Figure 5.2 — E2 核心图** | 当前 1×3 改为 2×2，仅画 direct HM--HJ、HP--HJ | 四 panel 为 (a) Stage-I 替换率、(b) Stage-I $L^{att}$、(c) Stage-II $A_0$、(d) Stage-II $L^{rec}$，逐年展示；$L^{att}$/$L^{rec}$ 使用已保存的 95% cluster-bootstrap CI。替换率与 $A_0$ 没有区间字段，明确只画点估计。此图呈现反直觉的“筛查近似保留、恢复目标并未同等保留”。 |
| **Table 5.4 — E3 目标权重下的决策画像** | 从 Supplement E3 的 24 行年度表形成四行摘要 | 每个 objective 报 exact target agreement、HJ 激活比例、非条件平均目标变化和条件平均变化；单元格采用六个年度等权均值，并列跨年 min--max。激活与零价值比例互为补数，正文不重复两者；Median $|\Delta u^*|=0$ 在 24 个组合中的共同结果写入表注。描述性摘要不作总体推断或显著性检验，Figure 5.3 继续显示年度×目标结构。 |
| **Figure 5.3 — E3** | 保留现有 2-panel objective × year heatmap | 左 panel 为 exact target agreement，右 panel 为目标改变对象中的平均绝对变化（分钟）；保留逐格数值标签和分立 colorbar。图注明确无置信区间、属描述性结果。 |
| **HJ recoverable-value profile** | 移至 Supplement；先核对量纲来源 | 当前六年表报告年度 CU 中位数、P90 和合计，但 Section 4 将主分析设为 year-local、跨年绝对 CU 解读留给 fixed-common track。若无法证明该表使用同一 frozen fixed-common 尺度，主文不得用这些数值作跨年高低比较；正恢复目标比例已由 E3 Balanced 行提供。 |
| **M5-b** | 主文一句话，完整表仅置 Supplement | 六年均为 `N_GRID_UPPER_BOUND_REACHED`；这是未确认稳定边界的样本量敏感性检查，不计作核心结果表，不把 4,096 写成充分样本证据。 |

该配置是四张主文表（其中三张为核心结果表）加三张结果图。E1 表给年均结果与年度范围、图呈现年内不确定性及审查容量交互；E2/E3 表给摘要、图给年度结构。完整年度 CI、support ledger、E2 配对样本明细、E3 全年表和 M5-b 失败项仍放 Supplement。没有审计支持的案例图不增加。

### 12.2 当前图的视觉检查与必须修改项

- 三张候选图均为单页矢量 PDF；颜色和 marker 有双重编码，Figure 5.3 用逐格数值降低对颜色辨认的依赖；三个 caption 的第一句均陈述主要发现。Figure 5.1 的 0--0.20 loss 轴诚实覆盖数据；Figure 5.2 的比例、agreement 与 loss 轴均明确标范围；Figure 5.3 的两个 colorbar 分开。
- **字体是共同的主要版面缺陷。** 三份 PDF 当前嵌入 Type 3 字体；Figure 5.2 源脚本设定 tick/label 为 6.8--7.5 pt，低于最终论文缩放后的 8 pt 目标。重导三图时用可嵌入的 TrueType/Type 42 字体，并按最终栏宽校准字号、线宽和 legend；不要仅靠放大 PDF 画布。
- **当前 Figure 5.2 的组成不够干净。** 它没有画已有的 Stage-I $L^{att}$ 及 CI，却把 HP--HM paired increment 与对 HJ 的 direct contrasts 叠在同一 $L^{rec}$ panel。paired increment 有独立支持样本，不宜与两条 direct contrasts 共用一个主图面板。该增量保留正文一句和 Supplement paired-detail 表，不进入主图。
- Figure 5.1 采用上排年度不确定性、下排增量曲线与零线；明确区分“年内 CI”和“跨年 min--max 阴影”。Figure 5.3 保留 heatmap，因为横轴为六个离散年度、纵轴为四类 objective，连线会暗示不存在的连续变化。
- Supplement 的 S5--S11 支持数、年度指标、配对对比、objective 表和 M5-b 状态均适合表格呈现；当前页面能完整容纳，避免再为同一年度结果制作重复图。S6 的年度 E1 表和 S9 的 paired detail 使用较小字号；最终版应以实际缩放阅读检查，优先调整列间距/拆分表格，不用整体缩小字体。

### 12.3 Supplement 表格编排

1. **保留并按证据链排序：** annual support ledger；E1 的 $q_0$ 年度对比和完整 review-budget grid；E2 的参考队列/activation 分母、paired detail 与 exact-marginal audit；E3 objective × year 表；M5-b 六年 ladder 状态表。HJ recovery profile 移入 E2 区域，紧跟 reference-cohort/support 表。
2. **补全 E1 review-budget 证据。** 当前印刷表只列 2019 例子，正文图展示的是六年均值与跨年范围。保留 2019 表时明确标成 illustrative；完整六年 q-grid 作为精简 supplementary table 或可机读 CSV 提供，避免正文图无法追溯到年度序列。
3. **重做或删除过时的 reporting-contract 表。** 当前 Table S12 把 E4 定义成 regime/rolling heterogeneity，并把未完成的 full-population Coverage@K、threshold ablation 写成模块应提供的内容。优先改为“RQ/输出/状态”短表（reported / pending / not run），不再按四个实验模块许诺尚无输出的材料。
4. **Sensitivity 参数表与结果表分开。** 当前 Table S13 同时列 nominal、planned values 和 operator contracts；若保留，移到 protocol 部分并增加 executed status，明确哪些只是计划/未运行。未执行的 $U_{max}$、effort slope 或 threshold ablation 不得排版成已经完成的实验结果。
5. **保留状态表胜过趋势图。** M5-b 六年全为同一上界状态，附失败计数即可；不画暗示稳定性随 N 收敛的曲线，除非曲线逐指标给出真实输出且明确失败条件。

### 12.4 编译与视觉复核状态

当前 `paper/main.pdf` 时间为 2026-10-14 19:24；它仍显示 `05_experiment.pre_revision_20261014.tex` 的旧结果结构。现用 `sections/05_experiment.tex` 时间为 22:08，因此该 PDF **不是现用主文源文件的版面证明**。`SUPPLEMENT.pdf` 反映的是当前 Supplement 文字，但也包含已填表仍称待补的旧承诺。完成回填后需要从候选 `main.tex` 与 `SUPPLEMENT.tex` 重新编译并逐页检查；本轮只完成本地 PDF 图形/表格视觉审计，没有编译或修改论文 TeX。

### 12.5 数据模式与“是否好看”的审稿判断

- **E1 有清楚且有边界的结果模式。** 在 $q_0=0.10$ 下，Delay+Passenger 的 $L^{att}$ 点估计在 12/12 个年度—阶段单元中低于 Delay；Delay+Downstream 与 Delay 的年度差均不超过 0.003。审查预算增大时，Passenger 的增量快速收窄：$L^{att}_{Delay}-L^{att}_{Delay+Passenger}$ 的六年等权年均值在 PRE 从 $0.0563$（$q=0.05$）降至 $0.0095$（$q=0.20$），在 $q=0.30$ 变为 $-0.0051$；TURN 对应为 $0.0526$、$0.0128$ 和 $-0.0037$。高容量端是小幅点估计反转：PRE 只有 3/6 年仍为正，TURN 六个年度点估计均略为负，年际范围重叠，不能写成“Passenger 排序有害”。适合讲成“Passenger 信息的排序价值集中于紧审查容量，扩容后优势消失”，这是较有经管含义的情境依赖发现。
- **E2 是最强、最整齐的主结果。** HM--HJ 六年 Stage-I 名单只替换 1.3--3.8%，而 Stage-II exact-target agreement 仍为 0.581--0.730；HP--HJ 在两层都明显更远。这组反差跨年稳定且跨决策层，图表能直观呈现。不过 Stage-II 是 HJ shortlist 参考队列，不是全 eligible population；HM 是经审计的数学 product-coupling 对照，physical feasibility 未被断言。
- **E3 有稳定的目标排序，也有更弱的推断支撑。** Passenger emphasis 的 agreement 六年均最低；Resource emphasis 的 HJ activation 六年均最低。所有 24 个年度—目标单元的中位目标变化为零，但条件均值仍有 6.7--12.7 分钟；这是分布形状和目标差异的描述性证据，没有 CI，不宜写成显著的因果/机制效应。
- **HJ recovery profile 不适合作为跨年“价值上升/下降”故事。** 目前候选表的年度 CU 中位数、P90 和合计看上去跨度很大，但主文说明主比较使用 year-local 标尺，只有 fixed-common track 才支持跨年绝对 CU 解读。先追清表格的 scale lineage；若仍是 year-local，就保留在 Supplement 并明确每年量纲不同，不把 40--85 CU 等总量排序成跨年机会差异。
- **目前视觉质量整体可用，Figure 5.1 的容量交互需要加强。** 当前三张预览中，Figure 5.1 最容易读出 q=.10 的方向一致性，但下排两条原始损失线在 $q=0.30$ 重合附近不够醒目；改画增量并加零线能让真正的边界模式一眼可见。Figure 5.2 现版为 1×3，遗漏已有 Stage-I $L^{att}$、并混入独立支持样本的 HP--HM 增量；按 2×2 direct contrasts 重构后，数值分离会更直观。Figure 5.3 热图结构清楚，但保留逐格数值与足够字体是关键。当前 Supplemental annual E1 与 E2 细表在单页中偏密；正文摘要表不应再压成同样的小字。

