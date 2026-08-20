# Exp3 Readiness

Scientific contract: test how retained information should evolve in rolling decisions.

## Required variants

| Requirement | Current capability | Status |
| --- | --- | --- |
| `ONE_SHOT` | no experiment variant or frozen anchor-node rule exists | `BLOCKED` |
| `ROLLING` | PRE can build an immutable five-minute decision-node grid; M1 consumes causal prefixes | `PARTIAL` |
| `SYNC` | availability/cutoff machinery can express synchronized evidence | `PARTIAL` |
| `LAG_5` | general replay-lag support and a `[0,5,10]` sensitivity config exist | `PARTIAL` |
| `LAG_10` | general declared-lag machinery exists | `PARTIAL` |
| paired decision loop | no Exp3 runner executes these variants through the typed chain | `BLOCKED` |

The current `exp/exp3` scientific question is unrelated: it evaluates evidence/coverage/induced-consequence ablations and an auxiliary LLM audit. Its runner, config, metrics, and Development outputs must not be relabelled as rolling-information evidence.

## Reusable interfaces

- `model/PRE/episode/node_builder.py::build_rolling_decision_nodes` creates the frozen five-minute node sequence without rewriting earlier nodes.
- `PREState.decision_node` records decision time, information cutoff, roll interval, node index, legal record IDs, config hash, and registry hash.
- `model/PRE/factual/replay.py` publishes realized facts only when typed availability clears the information cutoff.
- `ProductionPRERequest.factual_replay_declared_lag_minutes` can carry an explicit declared lag for a supported replay policy.
- `model/M1/history.py` validates causal, single-episode state histories.

These are model capabilities, not an implemented experiment. The existing frozen five-minute Data2 weather lag must not be silently reinterpreted as the Exp3 information-retention lag. Weather-source availability, factual operational replay, and experimental decision-loop lag are distinct contracts.

## Missing decisions/contracts to encode before execution

- the exact `ONE_SHOT` anchor node and cohort inclusion rule;
- whether SYNC/LAG variants shift all eligible updates or only the declared cross-stage reused information;
- support behavior when a delayed update falls outside the episode or after the final decision node;
- whether evaluation compares every rolling node or an episode-level policy summary;
- paired seed/scenario reuse across one-shot and rolling variants.

These are protocol fields to freeze, not parameter-tuning opportunities during implementation.

## Tests required

- node sequences are identical across variants except for the declared information-availability rule;
- lagged variants never expose a record before `availability_time <= information_cutoff`;
- no outcome used only as `TRAIN_LABEL` or `EVAL_OUTCOME` enters inference;
- earlier rolling nodes are immutable after later evidence arrives;
- one-shot and rolling variants share cohort, model, scenario, M2/M3/M4, and metric identities;
- SYNC/LAG_5/LAG_10 are distinguished from the frozen weather replay lag;
- final results record node-level and episode-level denominators and abstentions.

`EXP3_STATUS = REWRITE_REQUIRED`

