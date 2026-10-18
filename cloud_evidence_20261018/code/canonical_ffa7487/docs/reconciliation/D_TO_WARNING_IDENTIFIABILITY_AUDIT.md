# D_TO Warning Identifiability Audit

- audit date: `2026-08-17`
- scope: Development-only D3 prerequisites
- warning threshold search performed: `FALSE`
- Final Test access count: `0`

## Current contracts

Current M1 training labels are:

\[
R_{OB}=\max(0, AOBT-CRSDep), \qquad T_{TX}=TaxiOut.
\]

The current event-time contract defines total takeoff delay relative to a
train-frozen taxi reference as:

\[
D_{TO}=\max(0, \Delta_{OB}+T_{TX}-T_{TX}^{ref}),
\quad \Delta_{OB}=AOBT-CRSDep.
\]

`model/M1/target_builder.py` produces the clipped nonnegative `R_OB` label.
`model/M1/semantics.py` correctly distinguishes the event-time identity
`T_TO=T_OB+T_TX` from a delay-component identity. `AlignedScenario.d_to_minutes`
can derive `D_TO` only when signed event/reference fields are populated, but
the current M1 sampling path does not populate those fields from the three
ordered output heads.

## Identifiability result

```text
D_TO_TAIL_IDENTIFIABILITY = NOT_IDENTIFIED_FROM_CURRENT_M1_OUTPUTS
```

Proof by counterexample, using `T_TX=50` and `T_TX_ref=15` minutes:

| Signed departure offset | Current output `(R_OB, T_TX)` | Exact `D_TO` | `D_TO > 30` |
| ---: | --- | ---: | --- |
| `Delta_OB=-1` | `(0, 50)` | `34` | true |
| `Delta_OB=-10` | `(0, 50)` | `25` | false |

Both worlds produce the same current M1 outputs but different warning-event
truth. Therefore neither exact `D_TO` nor `P(D_TO>30)` is a function of the
current `(R_OB,T_TX)` outputs.

The expression `max(0, R_OB + T_TX - T_TX_ref)` is consequently a constructed
proxy. It is not exact total takeoff delay when the signed off-block offset is
negative.

## Scientific options

### Option A: Signed off-block residual

Definition:

\[
\widehat{\Delta}_{OB}=AOBT-CRSDep,
\qquad D_{TO}=\max(0,\widehat{\Delta}_{OB}+T_{TX}-T_{TX}^{ref}).
\]

- Data support: Data2 has scheduled departure, actual departure, official taxi-out, and a train-frozen direct taxi reference.
- Model change: replace or add a signed residual distribution; current nonnegative target bins cannot represent it.
- H/W reopening: `YES`. The target distribution and joint training objective change.
- Claim strength: exact relative to the declared event/reference contract.
- Advantages: preserves event-time arithmetic and remains useful beyond Exp1 warning.
- Risks: requires new signed support/bin/loss/calibration contracts and retraining.

### Option B: Direct D_TO head

Definition:

\[
D_{TO}=\max(0, WheelsOff-(CRSDep+T_{TX}^{ref})).
\]

- Data support: Data2 has realized wheels-off and the inputs required to fit the train-frozen reference.
- Model change: add a direct formal head and alter the shared objective.
- H/W reopening: `YES`.
- Claim strength: direct exact warning target relative to the declared reference.
- Advantages: warning probability is directly available.
- Risks: largest M1 contract change; introduces a fourth target and changes the selected model family.

### Option C: Constructed warning proxy

Possible definition, only after explicit approval:

\[
D_{TO}^{proxy}=\max(0,R_{OB}+T_{TX}-T_{TX}^{ref}).
\]

- Data/model support: usable with current W30 checkpoints after a joint scenario-combination and reference-lookup contract is frozen.
- Model change: no output-head retraining; Exp1 probability construction still requires a formal joint-scenario rule.
- H/W reopening: `NO` for the existing clipped targets.
- Claim strength: proxy only; it cannot be named exact `D_TO`.
- Advantages: preserves current checkpoints and frozen H/W selections.
- Risks: false warning-event classification for early departures; weaker scientific claim.

### Option D: Event-time enrichment

Use the existing optional signed `t_ob_utc`, `scheduled_ob_utc`, `t_to_utc`, and
taxi-reference scenario fields.

- At post-off-block nodes, observed signed event time could support exact realized arithmetic.
- At pre-off-block nodes, the current model still lacks a signed predicted `T_OB`; event-time enrichment alone does not identify early-warning `D_TO`.
- H/W reopening: `CONDITIONAL`; exact pre-off-block warning reduces to Option A or B and therefore requires reopening.

## Recommendation

```text
CODEX_RECOMMENDATION = OPTION_A_SIGNED_OFF_BLOCK_RESIDUAL
```

Option A is the smallest change that restores the lost event-time information
and keeps the scientific quantity reusable. This recommendation explicitly
accepts that H/W must be reopened. It is not an approval.

## Current W30 checkpoint reuse

```text
CURRENT_W30_CHECKPOINT_REUSABLE_FOR_WARNING = CONDITIONAL
```

- Exact Option A or B: `NO`.
- Proxy Option C: `YES`, after a proxy name, joint scenario rule, taxi-reference lookup, calibration handling, and final artifact rule are approved.
- Event-time Option D: `NO` for pre-off-block exact warning unless signed predictive information is added.

## Checkpoint artifact options if Option C is approved

| Option | Definition | Post-hoc risk |
| --- | --- | --- |
| first principal seed | freeze seed `20260813`, checkpoint `sha256:64f3de9ff5822e82573d6895786701e0db614ee69c09c166a8c3c36c33a01e62` | the final-artifact rule was not pre-registered, but it does not exploit observed seed performance |
| equal-weight three-seed ensemble | combine seeds `20260813`, `20260814`, `20260815` equally | ensemble was not the registered role of seeds; it is a new post-hoc model definition and needs aggregation/calibration validation |
| another rule | must be declared without selecting the best Development seed | risk depends on whether the rule uses observed Development outcomes |

Do not select seed `20260814` because it has the lowest observed Development
NLL. That is post-hoc seed selection.

Conditional recommendation if and only if Option C is approved:

```text
WARNING_MODEL_ARTIFACT_RECOMMENDATION = FIRST_PRINCIPAL_SEED_20260813
```

This creates less new model definition than an unregistered ensemble. It is not
operative for the recommended exact Option A path.
