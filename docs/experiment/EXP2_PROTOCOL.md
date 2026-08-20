# Exp2 Information-Sufficiency Protocol

## Scientific question

How much information structure is required for downstream recovery decision evaluation?

The experiment compares representations, not models. M1 produces one frozen joint scenario artifact. Exp2 applies controlled representation degradation without retraining M1. No variant is a model candidate or a claim of superiority.

## Frozen comparisons

### Exp2A: scenario information structure

Reference: `EXP2A_JOINT`.

| Variant | Retained | Removed |
| --- | --- | --- |
| `EXP2A_JOINT` | Scenario identity, weights, and joint samples | Nothing |
| `EXP2A_MARGINAL` | Each weighted `D_OB`, `D_TX`, and `D_TO` marginal plus field-level source lineage | Cross-variable within-scenario association |
| `EXP2A_COLLAPSED` | Weighted expected consequence state and all source lineage | Distribution and scenario-specific variation |

The same frozen M1 artifact hash, M1 artifact version, model/calibration identity, scenario cohort, and seed are used for all three.

### Exp2B: consequence resolution

Reference: `EXP2B_COMPONENT`.

| Variant | Representation |
| --- | --- |
| `EXP2B_COMPONENT` | Seven M2-emitted consequence components |
| `EXP2B_CHANNEL` | Flight, Passenger, and Resource aggregates |
| `EXP2B_SCALAR` | One all-component aggregate |

Aggregation uses only values already emitted by M2. An unsupported required component makes its aggregate unavailable. The protocol does not recompute M2, infer missing values, normalize CU, treat null as zero, or interpret CU as money.

## Fixed-factor contract

For every comparison, the following remain fixed:

- dataset and cohort;
- random seed;
- M1 model, calibration, and frozen scenario artifact;
- M2 frozen consequence artifact;
- M3 candidate action set and response registry;
- M4 monetary mapping and risk policy;
- evaluation definitions and reference representation.

Any difference outside the declared representation factor invalidates the comparison.

## Execution sequence

```text
frozen M1 + frozen M2
        |
        v
Exp2 representation adapter
        |
        v
same M3 action-response interface
        |
        v
same M4 residual-risk interface
        |
        v
paired common evaluator -> common result schema
```

The protocol validates current typed M3 and M4 envelopes at each boundary. It rejects action-set changes, response-rule changes, monetary-mapping changes, risk-policy changes, and M4 bypass.

## Metrics

State level records a frozen uncertainty metric only when both observations and its protocol are available. At present `STATE_CRPS` is recorded as `NOT_RUN`; no substitute proxy is created.

Decision level records top-action disagreement and pairwise ranking change from supported M4 residual-risk values. Risk level records residual-risk difference and CVaR difference using M4 outputs; the common V1 schema classifies these as decision-level observations because it currently exposes `STATE`, `DECISION`, and `SYSTEM` levels only.

All numeric differences use `variant - reference`. Missing, abstained, or non-ranked M4 values do not become zeros. Support and ranking authority remain in metric metadata.

## Support and stopping rules

An Exp2 result is `SUPPORTED` only if the four downstream comparison metrics are authoritative and supported under one frozen M4 mapping and policy. Conditional M4 values produce `PARTIAL`; unavailable metrics produce `BLOCKED`, with the individual metrics marked `NOT_RUN`.

Current scientific execution stops before results because:

- current V2 M3 supports only the A00 identity path, not a frozen multi-action response comparison;
- a production M4 monetary mapping is not frozen;
- the required M4 risk-policy decisions are not frozen;
- no frozen state-uncertainty observation protocol was supplied.

These are scientific input gates, not permission to alter `model/`, PRE, M1, M2, M3, or M4.

## Explicit exclusions

This protocol does not authorize:

- Exp1, Exp3, or Exp4 implementation;
- M1 retraining or separate models per representation;
- M2 recomputation or manual consequence construction;
- action-set, response-registry, monetary-mapping, or risk-policy modification;
- raw-CU ranking or bypassing M4;
- parameter tuning or best-variant selection;
- Final Test, `paper_full`, scientific conclusions, or paper-result generation.

## Future gated run

After the M3/M4 scientific artifacts are frozen, implement a concrete `Exp2DownstreamInterface`, supply the same object to an `Exp2RunContext`, and execute each registered variant through `Exp2Runner.execute`. Before any run, record the dataset/cohort, seed, source artifact versions and hashes, M3 response-registry identity, M4 mapping hash, and risk-policy hash. Run authorization remains a separate human gate.
