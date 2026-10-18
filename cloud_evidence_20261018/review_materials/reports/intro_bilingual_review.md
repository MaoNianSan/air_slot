# Introduction 逐句对照（原文 EN ⇄ 中文 ZH）

> 说明：以下按原文句子拆分，逐句对照。关键框架术语（如 disruption、recovery、operating realization、support）在首次出现时附英文原词，便于你核对语义是否忠实。引用键 `\citep{...}` 与公式保持原样。

---

### 第 1 段

**EN:** Airline disruption recovery is a rolling decision problem in which recovery choices must be repeatedly updated as operational information evolves.

**中:** 航空公司扰动（disruption）恢复是一个滚动决策问题，其中恢复方案必须随着运行信息的演化而被反复更新。

**EN:** Unlike static optimization problems, recovery decisions are made under interconnected operational processes involving aircraft continuity, turnaround operations, airport conditions, passenger exposure, and downstream execution opportunities \citep{hassanAirlineDisruptionManagement2021,evlerIntegrationTurnaround2022}.

**中:** 与静态优化问题不同，恢复决策是在相互关联的运行过程中做出的，这些过程涉及飞机连续性、过站（周转）运行、机场状况、旅客受影响程度以及下游执行机会 \citep{hassanAirlineDisruptionManagement2021,evlerIntegrationTurnaround2022}。

**EN:** Therefore, the same observed delay may correspond to different recovery requirements, and a recovery decision cannot be formed from the latest delay observation alone.

**中:** 因此，同一观测到的延误可能对应不同的恢复需求，而恢复决策并不能仅由最新的延误观测单独形成。

**EN:** It depends on how evolving operational information is transformed into a decision-relevant state and how the dependencies represented by that state are preserved throughout subsequent recovery decisions.

**中:** 它取决于不断演化的运行信息如何被转化为与决策相关的状态，以及该状态所代表的依赖关系如何在后续的恢复决策中得到保持。

---

### 第 2 段

**EN:** Existing research has established strong foundations for dynamic and uncertainty-aware airline recovery.

**中:** 现有研究已为动态且具备不确定性感知能力的航空公司恢复奠定了坚实基础。

**EN:** Rolling-horizon methods update recovery plans as new disruption information becomes available \citep{vinkDynamicAircraftRecovery2020}.

**中:** 滚动时域（rolling-horizon）方法在新的扰动信息可用时更新恢复计划 \citep{vinkDynamicAircraftRecovery2020}。

**EN:** Stochastic formulations represent uncertain disruption evolution and information revelation processes \citep{zhaoTwoStageAircraftRecovery2023}.

**中:** 随机规划建模刻画了不确定的扰动演化与信息揭示过程 \citep{zhaoTwoStageAircraftRecovery2023}。

**EN:** Predictive information has also been incorporated into downstream airline planning and recovery decisions \citep{leeDynamicDisruptionManagement2020,biroliniDayAheadAircraftRouting2023}.

**中:** 预测性信息也已被纳入下游的航空公司计划与恢复决策中 \citep{leeDynamicDisruptionManagement2020,biroliniDayAheadAircraftRouting2023}。

**EN:** In addition, industrial decision-support systems integrate heterogeneous operational data with large-scale recovery optimization methods \citep{daviesDecisionSupportSchedule2026}.

**中:** 此外，工业级决策支持系统将异构运行数据与大规模恢复优化方法相整合 \citep{daviesDecisionSupportSchedule2026}。

**EN:** These studies have substantially improved recovery decisions by refining individual decision components, enhancing information quality, and expanding the scope of recovery optimization.

**中:** 这些研究通过细化单个决策组件、提升信息质量并扩展恢复优化的范围，显著改进了恢复决策。

---

### 第 3 段

**EN:** However, improving individual decision components and enlarging the optimization scope does not necessarily ensure that information remains consistent across the entire recovery process.

**中:** 然而，改进单个决策组件与扩大优化范围，并不一定能够保证信息在整个恢复过程中保持一致。

**EN:** Different stages of a rolling recovery methodology may rely on different types of information: historical operational information may be required to form the current operating state, whereas current operational information may remain directly relevant when recovery actions are instantiated or compared.

**中:** 滚动恢复方法的不同阶段可能依赖不同类型的信息：形成当前运行状态可能需要历史运行信息，而当恢复动作被实例化或进行比较时，当前运行信息可能仍然直接相关。

**EN:** Although existing studies have considered information integration and system-level recovery, how information generated at different stages should be transformed, retained, and coordinated throughout the recovery chain remains insufficiently formalized.

**中:** 尽管现有研究已考虑信息整合与系统级恢复，但不同阶段所产生的信息应如何在整个恢复链中被转化、保留与协调，仍然缺乏充分的规范化。

---

### 第 4 段

**EN:** This issue is particularly important because airline recovery is characterized by sequential and dependent operational processes.

**中:** 这一问题尤为重要，因为航空公司恢复的特点在于其具有顺序性与依赖性的运行过程。

**EN:** A disruption affecting an upstream flight may alter downstream departure conditions, aircraft availability, turnaround opportunities, and passenger consequences.

**中:** 影响上游航班的扰动可能改变下游的离港条件、飞机可用性、过站机会以及旅客后果。

**EN:** Consequently, the operating state used for recovery decisions is not a direct observation but a representation constructed from evolving information.

**中:** 因此，用于恢复决策的运行状态并非直接观测，而是从不断演化的信息中构建出来的一种表示。

**EN:** If different stages independently reconstruct their inputs according to local objectives, decision-relevant information may be omitted and previously established state dependencies may be weakened.

**中:** 如果不同阶段依据局部目标独立地重建其输入，决策相关信息可能会被遗漏，而先前已建立的状态依赖关系可能会被削弱。

**EN:** The resulting recovery evaluations may then correspond to different operational realizations rather than alternative decisions for the same recovery situation.

**中:** 由此产生的恢复评估可能对应的是不同的运行实现（operational realization），而非同一恢复情形下的不同决策。

---

### 第 5 段

**EN:** This study addresses two questions.

**中:** 本研究解决两个问题。

**EN:** First, which decision-relevant information and state dependencies should be retained when evolving operational information is converted into a recovery state?

**中:** 第一，当不断演化的运行信息被转化为恢复状态时，应当保留哪些决策相关信息与状态依赖关系？

**EN:** Second, how should the retained information, the resulting state, and the available recovery actions be combined to generate a consistent recovery decision?

**中:** 第二，保留下来的信息、由此产生的状态与可用的恢复动作应当如何组合，以生成一致的恢复决策？

**EN:** We represent this process through two linked mappings:

**中:** 我们通过两个相互关联的映射来表示这一过程：

**EN (公式):** `\mathcal E_t \longrightarrow \mathcal S_t, \qquad (\mathcal E_t,\mathcal S_t,\mathcal A_t) \longrightarrow \mathcal D_t,`

**中 (公式含义):** 其中 $\mathcal E_t$ 表示决策时刻 $t$ 可用的信息，$\mathcal S_t$ 表示由该信息形成的运行状态，$\mathcal A_t$ 表示可用的恢复动作集合，$\mathcal D_t$ 表示由此产生的恢复比较。

**EN:** The first mapping describes how evolving information forms a decision-relevant state, while the second describes how the state, remaining decision-relevant information, and available actions jointly determine recovery decisions.

**中:** 第一个映射描述了不断演化的信息如何形成与决策相关的状态，而第二个映射描述了状态、剩余的决策相关信息与可用动作如何共同决定恢复决策。

---

### 第 6 段

**EN:** The methodology treats the interfaces between these transformations as part of the recovery decision model.

**中:** 该方法将这些转换之间的接口视为恢复决策模型的一部分。

**EN:** Specifically, information entering the decision process must satisfy decision-time availability requirements; the identity of the unresolved operating realization must remain traceable as information is transformed across stages; recovery actions must be compared under a common consequence representation; and the support associated with operational information or decisions must remain explicit during downstream evaluation.

**中:** 具体而言，进入决策过程的信息必须满足决策时刻的可用性要求；未解决的运行的实现（operating realization）的身份必须在信息跨阶段转化时保持可追踪；恢复动作必须在共同的后果表示下进行比较；而与运行信息或决策相关的支撑（support）在下游评估中必须保持显式。

**EN:** These requirements allow heterogeneous information sources, state representations, and recovery actions to be integrated within a consistent decision chain.

**中:** 这些要求使得异构信息源、状态表示与恢复动作能够在一条一致的决策链中被整合。

---

### 第 7 段（贡献）

**EN:** The contributions of this paper are threefold:

**中:** 本文的贡献有三点：

**EN:** We formulate a cross-stage decision chain for rolling airline recovery that explicitly represents how operational information is transformed into recovery states and how states, information, and available actions jointly determine recovery decisions.

**中:** 我们构建了一个面向滚动航空公司恢复的跨阶段决策链，明确刻画了运行信息如何被转化为恢复状态，以及状态、信息与可用动作如何共同决定恢复决策。

**EN:** We introduce an interface-consistency perspective for airline recovery. The proposed formulation specifies requirements for decision-time information availability, state-dependence preservation, common consequence representation, and explicit support tracking across recovery stages.

**中:** 我们提出了一种面向航空公司恢复的接口一致性（interface-consistency）视角。所提出的建模框架明确了以下要求：决策时刻信息可用性、状态依赖保持、共同后果表示，以及跨恢复阶段的显式支撑（support）追踪。

**EN:** We operationalize the proposed decision chain using an airline recovery methodology and evaluate how different information-sharing and state-dependence designs affect recovery-state construction, consequence evaluation, and final recovery decisions.

**中:** 我们利用一种航空公司恢复方法将所提出的决策链落地实现，并评估不同的信息共享与状态依赖设计如何影响恢复状态的构建、后果评估以及最终的恢复决策。

---

### 第 8 段

**EN:** The remainder of the paper reviews the related literature, formalizes the proposed decision chain, describes its empirical implementation, and evaluates its methodological and operational performance.

**中:** 本文的其余部分回顾了相关文献，形式化了所提出的决策链，描述了其经验性（实证）实现，并评估了其在方法论与运行层面的性能。

---

### 译者注（供你核对语义的几个关键术语）

- **disruption**：译为"扰动"，是航空恢复领域的标准译法；也可保留英文。
- **recovery**：译为"恢复"（指 disruption recovery，扰动恢复）。
- **operating / operational realization**：译为"运行实现"，指某一具体运行状态的实际落地/实现；这是本文框架中的专有概念，建议在定稿时与全文统一。
- **support**：译为"支撑（support）"，此处指与信息或决策相关联的支撑集/支撑范围，在下游评估中需保持显式。
- **instantiated**（第 3 段）：译为"实例化"，指恢复动作在具体情境下被具体落实。
- **operational performance**（末段）：译为"运行层面的性能"，与"methodological performance（方法论性能）"相对。
