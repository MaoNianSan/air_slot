# Round 2 Section 3 Methodology Alignment

Scope: manuscript Section 3, PDF pages 6–12. This is the highest-priority reconciliation area.

## Chain-level assessment

The manuscript's conceptual sequence

`operating information -> uncertain operating outcomes -> baseline consequence -> action-conditioned consequence -> monetary residual risk`

is correct. The current implementation gives this sequence stricter ownership:

`PRE(E_<=t) -> M1(chi, z_s) -> M2(q_s, C^{0,CU}_s) -> M3(I(a), P(a), C^{a,CU}_s) -> M4(L^{a,m}_s, J^m(a))`.

Overall Section 3 status: `PARTIALLY_ALIGNED`.

## 3.1 Information and state

| Manuscript | Implementation | Status | Required conceptual correction |
|---|---|---|---|
| `h_t = H(E_<=t)` is the operating-state representation. | PRE separates admissible history, current fast information, and static references. M1 uses `chi_t = concat(GRU(h_history), projection(r_fast), projection(c_static))`. | `MANUSCRIPT_TOO_NARROW` | Use `h_t` as the recurrent history subrepresentation and `chi_t` as the full state supplied to M1 and downstream lineage. |
| Realized information may update the state as facts. | Data2 archive lacks actual message-arrival timestamps; formal factual replay remains disabled while availability is unresolved. Weather alone has a frozen 5-minute replay lag. | `MANUSCRIPT_OVERCLAIMS` | State the availability-time rule and abstention boundary; event time is not automatically production availability time. |

## 3.2 M1 state-conditioned uncertainty

The primitive dependency is aligned in substance but too narrowly conditioned in notation. The implementation contract is:

`p(T_IB_A00, D_OB, D_TX | chi)`

`= p(T_IB_A00 | chi) p(D_OB | T_IB_A00, chi) p(D_TX | T_IB_A00, D_OB, chi)`.

`R_IB=max(0,T_IB_A00-t)` and scenario-wise `D_TO=D_OB+D_TX` are derived, not independent prediction heads. The manuscript should explain that ancestral scenarios retain identity and weight through M2–M4. The current `S=1000`, hidden size 32, forecast horizons `[0,15,60]`, and delay thresholds `[15,30,60]` are configuration-aligned. The positive-tail policy remains unresolved, so risk statements requiring unsupported upper-tail quantiles must abstain.

Status: `PARTIALLY_ALIGNED`.

## 3.3 M2 consequence representation

The manuscript correctly distinguishes native quantity `q`, CU consequence, and monetary loss in its general equations. Section 4 later collapses this distinction by presenting unsupported mappings as frozen.

Current ownership is:

- native `q_k(s)`: component-specific operational unit;
- `C_k^{0,CU}(s)`: M2 cross-component normalized representation, not money;
- `L_k^{a,m}(s)`: M4 system-specific monetary interpretation after action response.

The seven-component ontology is aligned as an ontology only. Numeric support is not complete: `P_time` is a route passenger-exposure proxy, while `P_itinerary` and `P_service` remain present but `ABSTAIN`. An all-seven scalar CU aggregate is unresolved; unsupported components cannot be dropped, zero-filled, or renormalized away.

Status: `PARTIALLY_ALIGNED` at the abstract method level and `MANUSCRIPT_OVERCLAIMS` where full support is implied.

## 3.4 M3 action response

The baseline/action distinction is correct:

- `C^{0,CU}(s)` is M2-owned initial consequence before an additional framework action;
- `C^{a,CU}(s)` is M3-owned consequence after the response mechanism;
- `C^{A00,CU}(s)=C^{0,CU}(s)` is the exact decision-time identity.

Two material conflicts require correction:

1. The manuscript uses `P(a)` for structural feasibility and `I(a)` for instantiability. The V2 implementation reserves `I(a)` for decision-node eligibility and `P(a)` for the response mechanism plus evidence/provenance.
2. The manuscript presents a universal Bernoulli–Beta response for all 22 non-A00 actions. V2 uses typed mechanisms (`DIRECT_REDUCTION`, `RESOURCE_SUBSTITUTION`, `SEQUENCE_MODIFICATION`, and `PASSENGER_SERVICE_PROTECTION`); non-A00 component-wise execution is disabled, and their legacy parameters are reproducible `PURE_SCENARIO` assumptions with `formal_support_upgrade=false`.

M3 represents response. It does not optimize, rank, select, or estimate causal treatment effects.

Status: `MANUSCRIPT_OVERCLAIMS`.

## 3.5 M4 monetary mapping and residual risk

The correct ownership is `C^{a,CU}(s) -> L^{a,m}(s) -> J^m(a)`. CU is independent of monetary system `m`; money and the resulting residual-risk ranking are system-dependent. M4 must not reconstruct action response or map `C^{0,CU}` for a non-A00 action.

The weighted expectation/VaR/CVaR machinery is implemented, and `lambda=0.25` and `alpha=0.90` are frozen in the scientific foundation. However:

- `production_mapping_enabled=false`;
- every component in the production monetary registry is `ABSTAIN`;
- the positive-tail policy is unresolved;
- therefore no authoritative RMB ranking is currently available.

Status: formula/interface `ALIGNED`; claimed empirical RMB instantiation `MANUSCRIPT_OVERCLAIMS`.

## Required Section 3 change order for the next phase

1. Introduce PRE and `chi` before the joint M1 distribution.
2. State the conditional M1 graph and derived identities.
3. Define seven native quantities and their support states separately from CU.
4. Correct `I(a)`/`P(a)` and replace the universal response formula with typed, provenance-qualified mechanisms.
5. Map only post-response CU into an explicitly named monetary system.
6. State ranking lanes and abstention conditions before making any decision claim.

No equation or TeX source was modified.
