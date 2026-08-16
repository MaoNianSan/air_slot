# Registry Boundary

Registry files define source usage, scientific variables, dataset capabilities, source priority,
and atomic action templates. `model/PRE/feature_registry/loader.py` validates identities,
dependencies, downstream roles, and the published manifest hash. Action-template loading validates
candidate IDs, response provenance, coverage, and consequence coordinates.

Registry entries may be frozen or development-frozen. A registry manifest hash is evidence of
registry consistency, not by itself evidence of a paper experiment or formal model readiness.
