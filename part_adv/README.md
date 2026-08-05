# part_adv

`part_adv` retains component-level analysis code. It consumes published
`overall_run` artifacts only and does not train M1 or reconstruct PRE inputs.

Execution remains blocked until the new M1 sample contract and downstream
migration status are explicitly accepted. Retired movement-sample inputs are
not converted or reused.
