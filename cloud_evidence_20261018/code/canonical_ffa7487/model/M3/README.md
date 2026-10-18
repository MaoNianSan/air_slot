# M3 Downstream Action-Space Interface

## CURRENT PUBLIC CONTRACT

M3 is the downstream interface defined by Section 3.6. It receives a
decision-time node, the baseline M2-compatible scenarios, consequence context,
and an explicit resource context. It exposes `candidate_actions`,
`transition_state`, and `evaluate_post_action`.

`A00` is always available as the identity continuation of the baseline state:
no additional recovery action is supplied by this framework. It is not a
claim that an airline, airport, crew, or ground operator stops normal work.

Without an airline-specific provider, only the A00 identity state can be
materialized. The default non-A00 candidate set is `NOT_MATERIALIZED`; M3
does not load the historical action templates as a complete feasible action
space and does not rank or recommend actions.

`M2PostActionConsequenceAdapter` delegates post-action consequence evaluation
to `M2Service.map_scenarios` and preserves the supplied M2 context and
lineage. It does not estimate an action effect.

## LEGACY / APPENDIX-ONLY IMPLEMENTATION

The historical 23-action registry, response models, numerical readiness
checks, and action-conditioned envelopes remain in their original modules.
The former service is available only as:

```python
from model.M3.legacy_service import M3Service
```

## NOT PART OF CURRENT EMPIRICAL MAINLINE

The current empirical path stops at PRE -> M1 -> M2 -> M4 priority and
screening. M3 is an extensible downstream contract and is not an executed
action optimizer, causal action-effect model, or operational selector.
