# part_adv

`part_adv` retains component-level analysis code. It consumes published
`overall_run` artifacts only and does not train M1 or reconstruct PRE inputs.

The M1-to-M2 V2 joint-sample contract is implemented, but formal M1 has not run.
Execution remains blocked at the downstream migration gate
(`M2_CONTRACT_MISMATCH`) until formal M1 publishes a bundle and the downstream
migration status is explicitly accepted. Retired movement-sample inputs are not
converted or reused.
