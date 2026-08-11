# overall_adv

`overall_adv` retains the overall policy-comparison implementation. It consumes
published `overall_run` artifacts only and never reads raw data or reconstructs
PRE or M1 inputs.

The M1-to-M2 V2 joint-sample contract is implemented, but formal M1 has not run.
Execution remains blocked at the downstream migration gate
(`M2_CONTRACT_MISMATCH`) until formal M1 publishes a bundle and the gate is
explicitly satisfied. No historical M1 fallback or compatibility conversion is
permitted.
