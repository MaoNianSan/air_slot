# 002 Production Data and PRE Validation

Engineering status: PASS for first-implementation scope. Scientific validation status is not asserted.

- Bounded real reads passed for data1 METAR and data2 BTS On-Time.
- Bounded canonical Parquet/ZSTD writes passed for both datasets outside raw roots.
- Repeated data2 canonicalization produced identical run and manifest identities.
- Future/post-hoc evidence is excluded from formal publication; legal values receive evidence-ledger and variable-lineage records.
- Raw source trees were opened read-only and the real-smoke test detected no data1 raw-tree mutation.

Unresolved local-debug validation:

- Full source-family coverage for OpenSky state-vector tar, Eurostat, OurAirports, DB1B, and T-100 needs larger real runs and layout variants.
- Replay lag and weather max age remain development-frozen; bounded smoke uses a declared 5-minute diagnostic replay lag only.
- Full-year episode/cache throughput, partition sizing, disk capacity, and resume after process interruption require VS/local execution.
- data1 reconstructed event rules require empirical QA; data2 actual event fields remain post-hoc only.
