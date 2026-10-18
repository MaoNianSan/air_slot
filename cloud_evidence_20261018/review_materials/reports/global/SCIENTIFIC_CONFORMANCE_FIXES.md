# Scientific Conformance Fixes

Date: 2026-08-12  
Scope: obvious local implementation errors only; no scientific redesign or architecture change

| ID | Mismatch found | Correction | Verification |
|---|---|---|---|
| FIX-001 | Replay lag could be applied once in canonical availability and again by subtracting lag from selection cutoff | Selector now enforces canonical `availability_time <= cutoff` directly; principal lag is frozen at 0 and sensitivity is `[0,5,10]` | Double-lag negative test |
| FIX-002 | PRE CLI had no principal replay default while bounded smoke used 5 | CLI principal default is now 0; 5 remains explicitly diagnostic in real smoke | Config/CLI tests and audit |
| FIX-003 | M2 silently defaulted required buffer/exposure/threshold/reference context to zero or 15 | Required context now raises `M2_CONTEXT_PARAMETER_MISSING`; unsupported quantities remain null/ABSTAIN | M2 negative test |
| FIX-004 | M4 Bernoulli response silently defaulted absent probability and intensity to 0.5 | Missing action-response parameters now raise `ACTION_RESPONSE_PARAMETERS_NOT_FROZEN` | M4 negative test |
| FIX-005 | M4 added induced consequence even when the action opportunity was closed | Induced consequence is now zero when opportunity is closed, matching manuscript Eq. 47 | Closed-opportunity test |
| FIX-006 | M1 sampler could sample an ABSTAIN target and did not validate observed-event contraction by operational stage | Sampler preserves unsupported target as null and requires observed IB/OB as stages advance | M1 contraction/ABSTAIN test |
| FIX-007 | Scientific config omitted parameters that the current specification explicitly freezes | Added principal lag, roll, horizons, thresholds, H=8, H=16 sensitivity, five-minute bins, S=1000, lambda=.25, alpha=.90 | Configuration contract test |
| FIX-008 | METAR source identity differed between adapter registry (`metar`) and data-usage rule (`iem_metar`); Eurostat JSON-stat was labelled CSV | Unified METAR to `iem_metar`; added explicit `json_stat` adapter format | Registry and real bounded reader tests |
| FIX-009 | Paper promotion did not enforce data2 main/data1 appendix roles | Promotion now validates fixed dataset-role mapping and rejects data1 main-text promotion | Promotion negative test |
| FIX-010 | Ordinary experiment runner silently converted missing metrics to numeric zero and treated any unknown dataset as appendix | Missing metric and unknown dataset now raise typed errors | Complete regression |
| FIX-011 | Bootstrap default was 1000 although the frozen evaluation contract specifies 2000 | Default changed to 2000 | Experiment tests |
| FIX-012 | Foundation validation and root/experiment README still claimed M1-M4 and experiment code were absent | Stale status text was corrected without claiming scientific readiness | Validation regression and source audit |
| FIX-013 | Interval-bin selection included bins touching only at an interval boundary | Marginalization now uses positive overlap; zero-width fallback remains explicit | M1 loss regression |
| FIX-014 | Old smoke/runtime files could be mistaken for current scientific evidence | Removed stale runtime, bounded canonical-smoke, experiment-smoke/report-smoke, audit scratch, and manuscript-render artifacts; preserved source, reports, READMEs, and the deterministic formal foundation fixture | Post-delete path audit |

## Deliberately not fixed in this audit

The following require substantive implementation and are reported rather than patched: true M1 ancestral conditional sampling; production PRE completeness; real training/calibration; M2 valuation freeze; episode-specific M3 parameterization; Bernoulli-Beta intensity draws; typed M4 PRE support input; complete E1-E4 protocols; canonical paper provenance; shared runtime CLI and production manifests.

No model redesign, framework edit, directory move, LLM call, full experiment, or large-data run occurred.
