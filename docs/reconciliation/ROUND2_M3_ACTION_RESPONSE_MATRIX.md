# Round 2 M3 Action-Response Matrix

The source of truth is `registries/m3_v2_action_response_design.json`. “Scenario” below means `SCENARIO_ASSUMPTION` from frozen `PURE_SCENARIO` parameters with no formal-support upgrade. Only A00 is executable in V2.

| Action | Family | Affected `C_k` components | Response mechanism | Support | V2 execution |
|---|---|---|---|---|---|
| A00 | null | none | identity | supported operational rule | enabled |
| A11 | timing/passenger coordination | P_itinerary, F_execution, P_time | sequence modification; passenger protection | scenario | gated |
| A13 | flight execution | F_propagation, R_operating | direct reduction | scenario | gated |
| A21 | timing | F_continuity, F_propagation, F_execution, P_time | sequence modification | scenario | gated |
| A22 | capacity coordination | F_execution, F_propagation, R_operating | sequence modification | scenario | gated |
| A23 | capacity coordination | F_execution, F_propagation, R_operating | sequence modification | scenario | gated |
| A31 | passenger recovery | P_itinerary, P_service, R_operating | passenger protection; resource substitution | scenario | gated |
| A32 | passenger recovery | P_itinerary, P_time, R_operating | passenger protection; resource substitution | scenario | gated |
| A33 | passenger service | P_service, R_operating | passenger protection | scenario | gated |
| A41 | ground recovery | F_execution, F_continuity, R_operating | resource substitution | scenario | gated |
| A42 | ground recovery | F_continuity, F_execution, R_operating | resource substitution | scenario | gated |
| A43 | ground recovery | F_execution, F_continuity, R_operating | resource substitution | scenario | gated |
| A51 | aircraft recovery | F_continuity, F_propagation, F_execution, R_operating | resource substitution | scenario | gated |
| A52 | aircraft recovery | F_propagation, F_continuity, R_operating | resource substitution | scenario | gated |
| A53 | aircraft recovery | F_continuity, F_execution, F_propagation, R_operating | resource substitution | scenario | gated |
| A54 | aircraft recovery | F_continuity, F_propagation, F_execution, R_operating | resource substitution | scenario | gated |
| A55 | aircraft recovery | F_continuity, F_propagation, R_operating | resource substitution | scenario | gated |
| A61 | crew recovery | F_execution, F_propagation, R_operating | resource substitution | scenario | gated |
| A62 | crew recovery | F_execution, F_propagation, R_operating | resource substitution | scenario | gated |
| A63 | crew recovery | F_execution, F_propagation, R_operating, P_time | resource substitution; sequence modification | scenario | gated |
| A64 | crew recovery | F_execution, F_propagation, R_operating, P_time | resource substitution; sequence modification | scenario | gated |
| A71 | extreme local network | F_propagation, F_continuity, P_time, P_itinerary, P_service, R_operating | sequence modification; passenger protection | scenario | gated |
| A72 | extreme local network | F_propagation, F_continuity, P_time, P_itinerary, P_service, R_operating | sequence modification; passenger protection | scenario | gated |

The affected-component lists are the union of the current structural registry's mitigation and induced mappings. They are design targets, not estimated treatment effects. Where M2 abstains, M3 V2 also abstains. No row establishes feasibility at a particular decision node; that is decided independently by `ActionEligibility`.
