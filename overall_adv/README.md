# overall_adv

`overall_adv` retains the overall policy-comparison implementation. It consumes
published `overall_run` artifacts only and never reads raw data or reconstructs
PRE or M1 inputs.

Execution remains blocked until M1 publishes the new joint-sample contract and
the downstream migration gate is explicitly satisfied. No historical M1
fallback or compatibility conversion is permitted.
