# Air Slot

Air Slot is a clean scientific implementation of an evidence-aware local airline-recovery interface.
Scientific authority is `mission.md > roadmap.md > tech-stack.md > latest manuscript`.
Physical layout authority is `framework.txt`; dataset profiles and audits provide evidence rather
than overriding those scientific contracts.

The current tree contains foundation contracts, bounded production adapters/PRE components,
development implementations of M1-M4, and experiment/reporting interfaces. Engineering presence
does not imply real-data validation, paper readiness, or scientific claims. See the global scientific
conformance audit before any larger run.

Use the current Python 3.11 interpreter directly:

```text
python -m pip install -r requirements.txt
python -m validation.cli all --fixtures-only
pytest -q
```
