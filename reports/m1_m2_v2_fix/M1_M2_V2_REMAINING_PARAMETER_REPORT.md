# M1-M2 V2 Remaining Parameter Report

Date: 2026-08-06

```text
M2_V2_PARAMETER_FREEZE_STATUS = NOT_YET_DONE
M2_V2_FORMAL_RECONSTRUCTION_STATUS = NOT_YET_RUN
SYNTHETIC_FIXTURE_PARAMETERS_PROMOTED = NO
```

| subitem | rule_type | breakpoints | slopes | context_multiplier | v_gj | status | source | next_action |
|---|---|---|---|---|---|---|---|---|
| F_TURN | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | gamma/min/max NOT_CONFIGURED | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule, multiplier, value |
| F_WAIT | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | gamma/min/max NOT_CONFIGURED | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule, multiplier, value |
| F_PROPAGATION | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | not selected | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule and value |
| P_DELAY | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | not selected | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule and value |
| P_CONNECTION | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | gamma/min/max NOT_CONFIGURED | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule, multiplier, value |
| P_CARE | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | not selected | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze threshold, rule, value |
| R_GROUND | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | gamma/min/max NOT_CONFIGURED | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule, multiplier, value |
| R_TAXI | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | gamma/min/max NOT_CONFIGURED | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze rule, multiplier, value |
| R_SCARCITY | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | not selected | NOT_CONFIGURED | REQUIRES_DEVELOPMENT_FREEZE | `scientific.yaml` | freeze wait/taxi trigger policy and value |

Additional pending parameters:

| parameter group | status | next action |
|---|---|---|
| conditional activation thresholds | REQUIRES_DEVELOPMENT_FREEZE | define evidence-backed thresholds |
| learned-correction `rho_g` | REQUIRES_DEVELOPMENT_FREEZE | freeze only with labeled support |
| learned-correction `epsilon` | REQUIRES_DEVELOPMENT_FREEZE | freeze only with labeled support |
| learned correction enabled | false | remain disabled in current formal path |
| currency F/P/R rates | explicitly configured at 1.0 | retain explicit mapping or approve a new mapping version |

Synthetic tests use explicit fixture parameters with:

```text
test_only = true
source = SYNTHETIC_FIXTURE
```

Those values are not read by the formal configuration and are not evidence of scientific freeze.
