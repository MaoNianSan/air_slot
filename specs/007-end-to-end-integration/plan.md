# Implementation Plan: End-to-End First-Version Integration

Create an `airslot` orchestration package over the existing `model` and `exp` packages. Runtime modules own layered configuration, stable manifests, progress events, ordered parallel execution, strict resume, safe cleanup, artifact validation, and orchestration. The shared CLI delegates scientific work to PRE/M1/M2/M3/M4 and experiment modules. It writes only beneath explicitly supplied project output roots.

The synthetic path uses a deterministic fixture PRE request, a seeded untrained smoke M1 explicitly labelled `SMOKE_UNTRAINED`, frozen development valuation parameters, the frozen action registry, and M4 decision mapping. The real-data path is bounded and read-only. No smoke path is promotable.

Constitution check: PASS. The design preserves evidence support, chronology, formal/evaluation separation, deterministic lineage, typed failure, and dataset-independent M1-M4 boundaries.

