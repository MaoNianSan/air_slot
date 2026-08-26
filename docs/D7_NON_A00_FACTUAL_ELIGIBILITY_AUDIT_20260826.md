# D7 — Non-A00 factual-eligibility audit

## Status

- decision id: `D7_NON_A00_FACTUAL_ELIGIBILITY_AUDIT_20260826`
- date: `2026-08-26`
- scope: read-only audit of the existing Development-cohort action-risk inputs
  and registered source contracts after A00 Baseline Gate V2.
- conclusion: `BLOCKED_BY_MISSING_DECISION_TIME_ACTION_FACTS_AND_SUPPORTED_RESPONSE_EVIDENCE`.
- result class: `HUMAN_DECISION_REQUIRED`; this is neither a model failure nor
  a reason to lower A00's value.

## Inputs and reproducibility boundary

- action-risk input:
  `artifacts/paper_results_v1/exp3/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet`
  (`sha256:661dd71603ef61c51a6e0da9453f2df573de81084edf9a41bce96ff845298ec5`).
- action definitions: `registries/action_templates.yaml`.
- decision-state/source contracts: `data2/DATA_USAGE.md`,
  `registries/source_adapter_registry.yaml`, and `model/M3/README.md`.
- no Final Test split was read; no model inference or retraining was run; no
  frozen V1 artifact, registry, configuration, or TeX file was changed.

## Observed gate result

The input covers 1,769 decision nodes.  For every one of the 22 non-A00
actions at every node:

- `eligibility_state = UNKNOWN`;
- `response_support = SCENARIO_ASSUMPTION`;
- no non-A00 action satisfies the V2 operational gate
  (`TRUE` eligibility, `SUPPORTED` response, finite objective).

Therefore all 5,307 node-band records (1,769 nodes x three valuation bands)
correctly emit `ABSTAIN_NO_FACTUALLY_ELIGIBLE_NON_A00`.  The 5,295 groups with
finite conditional ranks remain diagnostic only; they are not recommendations.

## Missing decision-time facts

The registered decision state contains predecessor motion, current weather,
aircraft identity, carrier and route context, schedule/taxi/turnaround
references, and airport/passenger/segment references.  It contains none of
the action facts required to establish non-A00 eligibility:

| Action family | Missing decision-time facts | Affected actions |
| --- | --- | --- |
| Network and authority | slot opportunity, priority window, cancellation/network authority | A22, A23, A71, A72 |
| Aircraft | compatibility, replacement/reposition/standby aircraft, cross-fleet compatibility, rotation option | A51-A55 |
| Crew | replacement/reserve crew, crew duty and reposition feasibility | A61-A64 |
| Ground | gate, stand, and ground-resource availability | A32, A41-A43 |
| Passenger | connection, itinerary, and exposure facts | A11, A31-A33 |
| Flight execution | executable range and decision-time successor schedule | A13, A21 |

The Data2 contract supplies post-hoc flight events plus aggregate passenger
references, not decision-time resource, authority, or passenger-itinerary
inventories.  An observed tail identity or published schedule is not a lawful
substitute for availability, authority, qualification, or a passenger-specific
connection fact.  Back-filling these conditions from post-hoc outcomes would
violate the stated information-time rule.

## Response-evidence finding

All non-A00 records are also marked `SCENARIO_ASSUMPTION`.  Thus factual
eligibility alone would not make the current conditional objective an
operational recommendation: action-specific response evidence must be
registered and supported independently.

## Required next decision

Choose one of the following paths; do not blend them.

1. **Close operational recommendation claims (recommended with current data).**
   Keep V2 abstentions, retain conditional rankings only as sensitivity
   diagnostics, and revise any manuscript/result language to state that no
   non-A00 operational recommendation is evidenced.
2. **Open a new data-and-contract tranche.**  Obtain versioned decision-time
   feeds for the relevant resource/authority/passenger facts, define legal
   availability cutoffs and action-level provenance, upgrade response support
   with independently registered evidence, then evaluate in a new independent
   protocol.  Do not reuse this Development-cohort conditional ranking as
   proof of operational performance.

Until path 2 is complete, A00 must remain a counterfactual baseline and the
system must retain typed abstention.
