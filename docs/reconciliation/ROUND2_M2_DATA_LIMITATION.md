# Round 2 M2 Data Limitation

## Modeled consequences

M2 V2 models flight continuity, off-block execution, node-specific propagation, aggregate passenger time exposure, and excess taxi operating exposure. These are conditional on each M1 scenario and preserve scenario weights and reference lineage.

`P_time` is a route-level passenger-exposure proxy. The existing frozen reference is retained unchanged; this tranche does not add, rebuild, or reinterpret DB1B data.

## Unavailable consequences

- `P_itinerary`: no frozen evidence identifying itinerary disruption and recovery outcomes; null/`ABSTAIN`.
- `P_service`: no frozen carrier-specific service or compensation rule within an approved scope; null/`ABSTAIN`.
- passenger compensation payments: unavailable.
- crew disruption and crew cost: unavailable.
- gate-resource usage and cost: unavailable.
- airline internal financial cost: unavailable.

Unavailable means not modeled. It does not mean zero consequence.

## Reference limitations

`E_down(node)` uses the frozen resolver hierarchy without claiming equal evidence quality:

1. decision-visible same-aircraft scheduled successor chain (`HIGH` confidence);
2. same-route frozen reference if one is later approved (`MEDIUM` confidence);
3. airport reference fallback (`LOW` confidence);
4. global reference fallback (`LOW` confidence).

Every resolved value records resolver level, source, reference ID/version, confidence, and a deterministic lineage hash. The same input/reference version reproduces the same lineage hash; changing reference version changes that hash.

## Future extensions requiring authority

Future support may be added only after an explicit evidence and freeze decision for itinerary recovery, service policy, or same-route propagation. Literature proxies would require a citation/reference ID, parameter version, applicability scope, and explicit proxy classification. No such proxy is activated here.

M2 CU scale parameters also remain human-gated. Until they are frozen, code-ready native quantities do not imply a formal all-seven CU aggregate or paper-ready evidence.
