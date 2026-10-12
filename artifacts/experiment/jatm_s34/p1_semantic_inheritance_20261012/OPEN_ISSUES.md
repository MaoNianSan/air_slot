# P1 未决事项（定向，不重做P0）

| ID | 类型/状态 | 当前证据 | 解除条件 |
| --- | --- | --- | --- |
| S1 | 科学待决：F_continuity | A是现行算法；B是SOBT相关运营短缺；稿件62自标时间公式待核对 | 用户选定或提出第三公式、解释/适用阶段/Train尺度的新版本，并批准受影响重估；此阶段维持`SCIENTIFIC_DEFINITION_PENDING` |
| S2 | 科学待决：Stage-II TURN时间坐标 | M1原始绝对T保留，M3却读取截断R_IB；只在部分c<41情况下可能改headroom | 科学确认T_IB应为signed节点相对坐标还是现行remaining代理；在合法样本上核对影响后，按获批版本重算受影响动作 |
| S3 | 稿件解释修正：nominal来源 | S4:123称41来自历史Q20，代码已写明共同回溯性政策而非各年度Train拟合 | 论文明确历史来源与年度Train sensitivity的分离，不把41称为2017/2018各自拟合参数 |
| S4 | 科学/物理支持 | Exact product可保持加权边际，但尚未完整输出无效运营组合质量比例 | 定义需检验的事件顺序/可行条件并统计；不要悄悄筛除不合法组合后仍称相同精确边际 |
| S5 | 科学归因 | CJ与HJ的已实现predictor规格可比较；稿件提到capacity-matched control | 提供已批准/核验控制结果，或缩限论文因果归因；不得将CJ-HJ直接称纯history effect |
| E1 | 工程待完成 | 四筛查视角/paired CI/Coverage接口及定向2ep对账存在 | F/tail/CU科学身份批准后在完整合法年度上输出全q×objective×track效果、分母、CI和源图数据 |
| E2/E3 | 工程待完成 | 当前小样本 exact、四算子与one-factor policy数值对账存在；旧Phase-5全年不属新年度 | 科学坐标决议后用本年M1/tail/CU全量执行，分键C2/C1/C3、完整Joint reference/action-response，保留负结果 |
| E4 | 工程/科学边界 | 当前可汇总年度、PRE/TURN、C3首末变化；天气/机场无批准group，within-chain uncertainty缺compact字段 | 只在定义与合法数据支持明确后增补；六年各自通过receipt才可形成完整汇总 |
| I1 | 年度输入缺失 | `independent_review_p0_20261012/ANNUAL_GAPS_CURRENT.json`所列21项本次仍全部缺失 | 合法年度模型/Train tail来源核验或另行获准准备；不重训、不跨年借用 |
| I2 | 云端环境未实测 | Linux/CUDA均NOT_RUN；本轮未连接腾讯云 | 二次科学/工程验收及相应授权后benchmark；此阶段不上传 |
| I3 | C07 receipt待阶段实施 | 需先冻结P1输出schema与科学身份 | P1独立验收后按已备案单独实施，不在本轮修改恢复代码 |
| I4 | 估时缺口 | 现有真实2ep与1node运行工作量差异大 | 已批准科学定义/年度输入具备后，用代表性合法节点carrier分布与吞吐量测算；不线性外推 |

保持 `SIX_YEAR_EXECUTION_BLOCKED`。本轮不自动补齐任何科学定义或年度输入；也不删除所谓“旧年份输出”。
