# M3 boundary

M3 loads the exact frozen 23-template registry and instantiates episode candidates from PRE facts
and declared episode parameters only. Known FALSE preconditions remove a candidate; UNKNOWN is
retained. Registry loading rejects unknown consequence coordinates, response models, provenance,
coverage, IDs, or action families. Missing required parameters are retained as UNKNOWN and never
guessed.
