# G0-3 unit/time trace

- Status: `PASS_STATIC_UNIT_CHAIN_WITH_TYPED_TAXI_LIMIT`
- Source epoch: `artifacts\diagnostics\v2_phase7\gate_b0_dag`
- Scientific recomputation: `False`

| Stage | Decision time | Information cutoff OK | D_TO identity | M3 u | Status |
|---|---|---:|---:|---:|---|
| PRE_IB | 2019-08-07T21:50:00+00:00 | True | True | 5.0 | TRACE_COMPLETE_TO_U |
| POST_IB_PRE_OB | 2019-08-27T16:45:00+00:00 | True | True | 5.0 | TRACE_COMPLETE_TO_U |
| POST_OB_PRE_TO | 2019-08-16T21:19:00+00:00 | True | True | None | TRACE_COMPLETE_TO_PRIORITY_TAXI_U_NOT_AVAILABLE |

The raw actual successor fields are posthoc replay records when their availability time is after the decision time. They are reported for lineage and unit tracing, not admitted as inference inputs.
CU is a normalized consequence representation and is not currency. `u` is the frozen Stage-II modeled recovery-intensity variable, not an identified real-world action.
