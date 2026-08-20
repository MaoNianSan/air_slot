# Round 2 M4 Manuscript Impact

## Sections affected when editing is authorized

The method overview should show M4 after M3 and distinguish consequence, monetary interpretation, risk aggregation, and ranking. The notation subsection needs separate definitions for `C^{CU}`, `L^m`, weighted `CVaR_alpha`, and `J^m(a)`. The uncertainty subsection must retain scenario weights through monetary conversion. The ranking subsection must distinguish authoritative, conditional, and abstained outputs. The limitations subsection must disclose every unfrozen monetary/tail/objective gate.

## Required wording corrections

Any direct equation from raw delay or PRE/M1 features to money should be removed from M4. Any equation applying action response inside M4 should instead consume M3 `C^{a,CU}`. “Residual risk” must mean loss after action response, not initial disruption impact. “RMB” must not be used for internal/test scales without an externally justified and frozen mapping registry.

## Evidence status

The new tests establish engineering properties: input isolation, CU immutability, system-specific mapping, artifact invalidation on version change, mapping provenance, scenario-weight preservation, weighted expectation/CVaR, tail gating, A00 handling, ranking labels, lineage propagation, and deterministic hashes. They do not establish production monetary parameters or action effectiveness.

## Human decisions required

1. Freeze the CU normalization basis used upstream.
2. Approve a production monetary system and source-backed `f_k^m` for every included component.
3. Resolve `M1_POSITIVE_TAIL_DECISION_REQUIRED` and freeze CVaR alpha/tail semantics.
4. Freeze the expected-loss/CVaR objective coefficients and metric version.
5. Decide whether `REFERENCE_BASED` M3 responses may ever enter authoritative rather than conditional ranking.

No TeX, M3, Exp1–4, experiment output, or production ranking was changed or executed.
