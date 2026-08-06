# M1-M2 V2 Test Report

Date: 2026-08-06

## Commands and Results

    python -m compileall -q overall_run/src/m1 overall_run/src/m2
    RESULT=PASS

    python -m pytest overall_run/tests/m1 -q
    RESULT=60 passed, 4 warnings

    python -m pytest overall_run/tests/m2 -q
    RESULT=13 passed

    python -m pytest overall_run/tests/m2/test_m2_v2_integration.py -q
    RESULT=4 passed

The combined targeted run completed with 73 passed and 4 warnings.

These commands were rerun after refreshing `origin/main` and immediately
before the M1-M2 V2 synchronization commit; the results were unchanged.

## Covered

- frozen feature schema and five-minute snapshot grid;
- full-sequence versus incremental GRU state;
- no historical double encoding;
- revision replay and temporary state isolation;
- checkpoint and calibration identity;
- formal artifact requirements and NOT_RUN manifest semantics;
- M1 physical sample identities and horizon monotonicity;
- finite within-bin sampling and stable random streams;
- training-only empirical tail and unresolved overflow;
- M1ScenarioBundle serialization;
- M1-to-M2 alignment and reference provenance;
- evidence-driven subitem activation;
- unsupported not converted to zero;
- compact rule monotonicity, nonnegativity, and breakpoint limit;
- subitem CU additivity and RMB identity;
- currency-layer sensitivity isolation;
- row-order invariance;
- unresolved tail ABSTAIN and q95/CVaR blocking;
- synthetic M1 scenario to M2 loss and episode summary.

## Warnings

Four warnings come from existing sklearn classification tests with a
single-class fixture. They do not indicate failed M1/M2 contracts.

## Not Run

- full repository test suite;
- retired M2-to-M4 scalar contract tests;
- PRE, M1 training, calibration, formal evaluation, or production M2 data;
- fast, middle, full, precision, overall_adv, or part_adv.

## Status

    COMPILE_STATUS=PASS
    M1_UNIT_STATUS=PASS
    M2_UNIT_STATUS=PASS
    M1_TO_M2_SYNTHETIC_STATUS=PASS
    FORMAL_DATA_RUN_STATUS=NOT_RUN
    PRE_COMMIT_REVERIFICATION_STATUS=PASS
