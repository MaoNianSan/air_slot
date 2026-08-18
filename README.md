# Air Slot

Air Slot is an evidence-aware airline-recovery research implementation. The scientific chain is:

```text
RAW -> PRE -> M1 -> M2 -> M4 -> Formal Decision Artifact -> evaluation / Exp1-4
                    ^
                    M3 (independent atomic action/response library)
```

PRE answers what may be known at decision time. M1 models unresolved operational state. M2 maps
that state to the fixed seven-component consequence ontology. M3 represents atomic recovery
actions and response provenance; it is not a sequential learner after M2. M4 is the only formal
action-comparison and ranking layer.

Data2 (BTS 2019 and its frozen references) is the principal empirical environment. Data1
(OpenSky/METAR/Eurostat sources) is the cross-evidence-environment portability family. Raw schema differences stop at
the PRE adapter/registry boundary. `model/` owns scientific contracts, `exp/` owns evaluation-only
contrasts, `validation/` owns bounded checks, `configs/` separates scientific/evaluation/runtime
settings, and `registries/` owns source and action definitions.

The V5 experiment layer uses one cross-experiment contract, named RNG streams, immutable formal
artifacts, controlled Exp1-Exp4 evaluation, and read-only publication generation. Engineering
presence does not imply real-data paper readiness. See
`docs/EXPERIMENT_V5_IMPLEMENTATION_AUDIT.md` and the generated status manifests before any larger run.

Use the current Python 3.11 interpreter directly:

```text
python -m pip install -r requirements.txt
python -m validation.cli all --fixtures-only
pytest -q
python -m exp.cli smoke-all --output artifacts/diagnostics/v5_smoke
python -m exp.cli status --output .
```

Formal experiment modes are `smoke`, `development`, `paper_full`, and `numerical_stress`. `FAST`
is an M1 computational path, not an experiment mode. `paper_full` requires explicit approval and a
fully passing cross-contract gate. The bounded smoke is non-paper evidence; formal Exp1-Exp4 Final
Test, paper promotion, and numerical-stress execution have not run. The Development-scope LLM audit (Exp3.7 V2, state-conditioned operational reasonableness explanation) completed on the frozen scenario artifact; the Final Test remains untouched. Hidden-size selection
is Development-frozen at `H=32` / `W=30 minutes` (decisions `D2_H_STAR` / `D3_SIGNED_M1_H_W_REFREEZE`); no Final Test selection was used.
