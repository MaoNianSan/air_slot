# PRE Core V2

PRE has one contract: `AIR_CHAIN_CORE_V2`, schema `air-chain-core-2.0`, research
revision `AIR_CHAIN_CORE_V2_R2`.

Published bundles live at `pre/output_core/<mode>/AIR_CHAIN_CORE_V2/` and
contain episodes, events, observations, observation membership, calibration,
evidence audit, column registry, and `pre_manifest.json`. Observation and
membership data may be partitioned as declared by the manifest.

PRE owns raw ingestion, event reconstruction, flight-chain construction,
source-global observations, membership, train-only references, evidence
lineage, and publication validation. It does not own five-minute M1 timelines,
query-time feature selection, recurrent masks or state, M1 targets, predictions,
or samples.

```powershell
D:/Python311/python.exe pre/main.py inspect-config --mode fast
D:/Python311/python.exe pre/main.py build --mode fast
D:/Python311/python.exe pre/main.py validate --mode fast
D:/Python311/python.exe pre/main.py readiness --mode fast
D:/Python311/python.exe pre/main.py report --mode fast
```

Building Fast is a separate gated action. Tests and contract verification do
not authorize middle, full, or downstream experiments.
