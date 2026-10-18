# Round 2 Section 4 Implementation Alignment

Scope: manuscript Section 4, PDF pages 12–21.

Overall status: `MANUSCRIPT_OVERCLAIMS`.

Section 4 has the correct intended workflow, but it describes several designed or gated interfaces as fully frozen empirical specifications. The rewrite must present one connected workflow, not five independent module descriptions.

## Required workflow explanation

| Workflow step | Current implementation | Manuscript alignment |
|---|---|---|
| 1. Data and admissibility | PRE publishes typed history/current/static blocks under decision-time cutoffs and lineage. Data2 weather availability is observation time + 5 minutes, max age 60 minutes. Data2 factual replay availability is unresolved. | Data sources and weather lag align; general factual replay is overstated. |
| 2. Feature/state construction | State-aware M1 uses `chi=[GRU(full admissible prefix), r_fast, c_static]`; the fast comparator uses `[r_fast,c_static]`. | GRU H=32 aligns; the full `chi` formula is not explicit enough. “Causal GRU” must not be read as causal-effect estimation. |
| 3. Training/calibration | Chronological Train/Calibration/Development/Final Test dates align with config. Calibration policy is typed, but no fitted V2 calibration artifact exists and positive-quantile calibration is not applied. Final Test access remains zero. | Split dates align; claims that all required specifications are frozen before final evaluation are too broad. |
| 4. Scenario generation | M1 generates 1,000 weighted ancestral scenarios over `T_IB_A00 -> D_OB -> D_TX`, with `D_TO` derived. | Scenario count and dependency idea align; public/derived identities and positive-tail gate need clearer treatment. |
| 5. Consequence construction | M2 constructs a seven-member typed vector, but only five components have current numeric/reference/proxy paths. | Full passenger itinerary/service construction and all-seven frozen normalization are overstated. |
| 6. Action response | The structural library has 23 templates. A00 is executable identity; 22 non-A00 V2 mechanisms remain scenario assumptions and gated. | Action inventory aligns; frozen numerical non-A00 response specification does not. |
| 7. Valuation and evaluation | M4 can validate typed monetary mappings and calculate weighted residual-risk metrics. The production mapping registry is empty/disabled. | A frozen RMB interface and authoritative RMB comparison are not supported. |

## Claim-by-claim implementation audit

| Section 4 claim | Actual status | Alignment |
|---|---|---|
| BTS On-Time, DB1B, T-100, NOAA ISD, and static references supply the empirical construction | These sources are represented in the current data/PRE contracts, subject to role and cutoff restrictions. | `ALIGNED` |
| Weather is replayed with a 5-minute delay and maximum age 60 minutes | Frozen for Data2. | `ALIGNED` |
| Realized operational events update the state as available facts | Archive event times do not identify message availability; formal Data2 factual replay is disabled pending a human decision. | `MANUSCRIPT_OVERCLAIMS` |
| A one-layer GRU with H=32 summarizes admissible history | Aligned as the recurrent subpath; full state also uses `r_fast` and `c_static`. | `PARTIALLY_ALIGNED` |
| `P_itinerary` and `P_service` are constructed through frozen literature mappings | No qualifying itinerary-recovery evidence or frozen scoped service rule exists; both abstain. | `MANUSCRIPT_OVERCLAIMS` |
| Every native component has a frozen positive CU reference | V2 CU scales are pending and the all-seven formal aggregate is unresolved. | `MANUSCRIPT_OVERCLAIMS` |
| The study has frozen component-specific RMB coefficients | Production monetary mapping is disabled; all seven component rows abstain. | `MANUSCRIPT_OVERCLAIMS` |
| The 22 non-null templates use a frozen Bernoulli–Beta response model | Legacy parameters are version-frozen pure-scenario assumptions, not empirically supported V2 responses; V2 execution is disabled. | `MANUSCRIPT_OVERCLAIMS` |
| A universal scalar response with induced-consequence coefficient maps every action | V2 requires typed component-wise mechanisms and forbids anonymous `gamma`/`omega` parameters. | `MANUSCRIPT_OVERCLAIMS` |
| Residual-risk policy uses `0.75 E[L] + 0.25 CVaR_0.90(L)` | `lambda` and `alpha` values are frozen and the weighted metric is implemented, but evaluation abstains without mapping and adequate tail support. | `PARTIALLY_ALIGNED` |
| Development freezes passenger mappings, action responses, and policy parameters before final evaluation | Passenger mappings, non-A00 V2 responses, and production monetary mapping are not scientifically frozen; Final Test remains unused. | `MANUSCRIPT_OVERCLAIMS` |

## Required implementation-text corrections

- Replace “frozen” with the exact state: configured, version-frozen scenario assumption, development-frozen, scientifically supported, or unresolved.
- State that database coverage does not imply observation of individual itineraries, service interventions, internal airline costs, or action-specific outcomes.
- Preserve scenario IDs and weights through consequence, response, and valuation.
- State that unsupported included components propagate abstention.
- Separate numerical scenario evaluation from authoritative recommendation.
- Treat A00 as no additional framework action from the current decision time, not as proof of no prior operational intervention.

## Publication-quality defects

- Table 5 represents passenger literature mappings as frozen when they are not.
- Table 7 represents passenger, response, and RMB specifications as complete when they are gated.
- Grammar defects include “the datasets” where a singular subject is intended and at least one duplicated “the.”
- No framework figure is present to connect the workflow described in prose.

No data, feature, training, scenario, or evaluation process was executed during this audit.
