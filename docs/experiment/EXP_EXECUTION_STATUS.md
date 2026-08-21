# Experiment Execution Status

## Source Rewrite Status

AIR_SLOT_EXP1_4_SOURCE_REWRITE_FAST_COMPLETE

The active source protocols are:

| Experiment | Active Question | FAST Contract Status |
| --- | --- | --- |
| Exp1 | Why retain direct information roles and history? | FAST PASS |
| Exp2 | How much and what representation structure is sufficient? | FAST PASS |
| Exp3 | How should retained information evolve in time? | FAST PASS |
| Exp4 | Does the complete chain work adequately? | FAST PASS |

## Shared Gates

| Gate | Current Status | Effect |
| --- | --- | --- |
| Data2 factual replay availability | Unresolved scientific rule | No factual event is introduced into inference |
| M1 positive-tail policy | Unfrozen | Tail/CVaR-dependent outputs remain blocked |
| Non-A00 M3 V2 response | Not executable/formally supported | Formal multi-action outputs remain blocked |
| M4 monetary mapping and risk policy | Unfrozen | Monetary residual-risk/ranking outputs remain NOT_RUN |

The source rewrite does not alter PRE/M1/M2/M3/M4, Data1/Data2 definitions,
split boundaries, targets, action library, or M4 risk definition.

FAST evidence: `pytest -q tests/experiment` passed (82 tests) and
`python -m exp.cli smoke-all --output artifacts\diagnostics\exp_rewrite_fast`
completed with `status=PASS` for Exp1--Exp4. These are contract-only checks;
they do not constitute scientific execution or paper evidence.

## Safety

FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
