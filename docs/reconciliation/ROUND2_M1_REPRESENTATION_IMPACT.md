# ROUND2_M1_REPRESENTATION_IMPACT

This is a manuscript-impact memo only. No `.tex` file is changed.

## Section 3-4 alignment

The current Section 3 shorthand

```text
p(T_IB, D_OB, D_TX | h)
```

should later be written using the full implementation state

```text
chi_t = (h_history, r_fast, c_static)
p(T_IB, D_OB, D_TX | chi_t)
```

where:

- `h_history` is the GRU representation of the full admissible causal history;
- `r_fast` is the current/local-change/short-term autoregressive representation;
- `c_static` is PRE's typed static/reference context.

STATE_AWARE consumes `[h_history, projection(r_fast), projection(c_static)]`.
FAST consumes `[r_fast, c_static]`. This is not a reinterpretation of the FAST
path; the two estimators share the same scientific state components except for
the recurrent history block.

The primitive factorization remains

```text
T_IB_A00
  -> D_OB | T_IB_A00
  -> D_TX | T_IB_A00, D_OB
```

with `R_IB=max(0,T_IB_A00-t)` and `D_TO=D_OB+D_TX` derived. Replacing `h` with
`chi` makes Section 3 consistent with the Section 4 empirical implementation
and with the cross-stage claim: when legal factual information appears, PRE
changes the typed information state, M1 contracts the corresponding uncertain
component, and downstream scenarios update without future leakage.
