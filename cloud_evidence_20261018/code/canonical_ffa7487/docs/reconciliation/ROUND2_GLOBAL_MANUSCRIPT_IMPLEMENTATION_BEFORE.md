# Round 2 Global Manuscript–Implementation Audit: Before

Audit baseline:

- repository HEAD: `74c07239c212bd9be67c481855a1bc8e5c2629eb`
- manuscript: `Airline_Recovery_under_Delayed_Information__Residual_Risk_Control (34).pdf`
- manuscript scope inspected: physical PDF pages 1–21, covering Sections 1–4 and the start of Section 5
- execution boundary: impact analysis only; no manuscript, TeX, model, registry, or experiment modification

The current manuscript is the authority for what the paper says. Current typed contracts, registries, scientific configuration, and tests are the authority for what the implementation supports. Engineering completeness is not treated as scientific evidence.

## Overall finding

`PARTIALLY_ALIGNED`, with `MANUSCRIPT_OVERCLAIMS` concentrated in Section 4.

The manuscript already presents a coherent conceptual chain from evolving information to state-dependent decision comparison. It does not yet describe the current PRE → M1 → M2 → M3 → M4 interfaces with sufficient precision. Section 4 materially overstates the support and freeze status of passenger consequences, non-A00 action responses, and monetary evaluation.

## Section-level audit

| Section | A. Manuscript claim | B. Current implementation | C. Status |
|---|---|---|---|
| 1 Introduction | Cross-stage retention and state dependence are needed because identical observed delays can imply different recovery needs; the work contributes an interface-consistent decision chain. | PRE constructs admissible decision-time information; M1 produces state-conditioned uncertainty; M2 represents consequences; M3 represents action response; M4 maps post-response CU to system-dependent monetary risk. | `PARTIALLY_ALIGNED` |
| 2 Related Literature | Prediction, integrated optimization, information sharing, state representation, and action evaluation have evolved around individual functions; the missing issue is consistency across stages. | The implementation operationalizes that gap through typed ownership and lineage boundaries, including abstention when support is missing. | `PARTIALLY_ALIGNED` |
| 3 Methodology | Formal chain `z -> q -> C^{0,CU} -> C^{a,CU} -> L^{a,m}` with scenario-preserving response and residual-risk comparison. | The chain is directionally correct, but the state should be `chi`, M3 notation conflicts with the implementation, and several support gates are not represented. | `PARTIALLY_ALIGNED` |
| 4 Empirical specification | Data and parameters instantiate all seven consequences, 22 non-null action responses, RMB valuation, and residual-risk evaluation under frozen specifications. | Only five M2 components have current numeric/reference/proxy paths; `P_itinerary` and `P_service` abstain. Only A00 is executable in M3 V2. Production monetary mapping is disabled and all seven M4 mappings abstain. | `MANUSCRIPT_OVERCLAIMS` |

## Implemented chain and current authority boundary

| Layer | Implemented responsibility | Manuscript treatment | Audit result |
|---|---|---|---|
| PRE / information | typed admissibility, cutoff legality, history/current/static separation, lineage; Data2 weather replay lag is 5 minutes; factual replay availability remains unresolved | Section 3 describes information history and Section 4 describes replay, but does not expose PRE as a formal contract and implies realized facts can always update the state | `MISSING_EXPLANATION` |
| M1 / state | `chi = concat(GRU(history), projection(r_fast), projection(c_static))`; primitive chain `T_IB_A00 -> D_OB -> D_TX`; `R_IB` and `D_TO` derived; scenarios and weights preserved | conditions the joint model on `h` and calls the recurrent model “causal GRU” | `MANUSCRIPT_TOO_NARROW` |
| M2 / consequence | seven-component ontology; native quantities and CU are separate; five current numeric/reference/proxy paths; two explicit abstentions; no money | presents seven components as fully instantiated and all CU references as frozen | `MANUSCRIPT_OVERCLAIMS` |
| M3 / action | 23 structural templates; `I(a)` is eligibility, `P(a)` is response; A00 identity executable; 22 non-A00 responses are scenario assumptions and V2 execution is disabled | uses `P(a)` for structural feasibility, `I(a)` for instantiability, and presents a universal frozen Bernoulli–Beta response for all non-A00 actions | `MANUSCRIPT_OVERCLAIMS` |
| M4 / risk | consumes `C^{a,CU}`; typed monetary mapping and weighted mean/VaR/CVaR are engineered; `lambda=0.25` and `alpha=0.90` are frozen; production monetary mapping is disabled | presents a frozen RMB mapping and formal RMB residual-risk evaluation as available | `MANUSCRIPT_OVERCLAIMS` |

## Global defects visible in the PDF

- The Abstract heading is present but the abstract is empty.
- Multiple literature citations render as literal `?` on PDF pages 2–4.
- No Figure 1, `Figure`, or `Fig.` object appears in the PDF; the framework is therefore not visually stated.
- The manuscript uses “causal GRU” where the implementation establishes temporal directionality, not a causal treatment effect.
- Section 4 repeatedly uses “frozen” without distinguishing version-frozen scenario assumptions, engineering configuration, and scientifically supported parameters.

## Blocking manuscript changes before experiment planning

1. Replace the implied `h`-only state with the full `chi` interface and condition M1 on it.
2. Preserve native consequence, CU, and money as separate owned layers.
3. Correct M2 passenger support: `P_time` is a proxy; `P_itinerary` and `P_service` currently abstain.
4. Correct the M3 notation and disclose that only A00 is executable under V2; scenario freezing does not create empirical support.
5. Remove the claim that a production RMB mapping is frozen or active.
6. Add an actual framework figure showing dependencies and support/abstention propagation.
7. Reconcile experiment questions with the contributions, especially Exp3.

No model redesign is required by this audit. Scientific gates remain to be resolved before the manuscript can claim full empirical execution.
