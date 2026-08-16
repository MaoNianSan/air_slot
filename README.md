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

Data1 (OpenSky/METAR/Eurostat sources) is the primary scenario family; Data2 (BTS 2019 and its
references) is an operational benchmark and portability family. Raw schema differences stop at
the PRE adapter/registry boundary. `model/` owns scientific contracts, `exp/` owns evaluation-only
contrasts, `validation/` owns bounded checks, `configs/` separates scientific/evaluation/runtime
settings, and `registries/` owns source and action definitions.

The current tree contains reconciled PRE-M4 interfaces, compatibility facades, experiment
readiness scaffolding, and explanation reports. Engineering presence does not imply real-data
paper readiness. See `docs/reconciliation/EXPERIMENT_READINESS_AFTER.md` before any larger run.

Use the current Python 3.11 interpreter directly:

```text
python -m pip install -r requirements.txt
python -m validation.cli all --fixtures-only
pytest -q
```

The bounded real-data M1 smoke is intentionally non-paper evidence. Formal Exp1-Exp4, Final Test,
LLM audit, paper promotion, and the full-year paper experiment have not run. Hidden-size selection
remains pending development-stage Exp1 selection; candidates are `[16, 32]`, with no winner frozen.
