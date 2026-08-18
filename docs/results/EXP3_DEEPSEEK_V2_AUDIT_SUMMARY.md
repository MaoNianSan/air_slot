# Exp3 DeepSeek V2 Audit Summary

## Status

- `DEVELOPMENT_ONLY = TRUE`; `TEMPORARY_REPORT = TRUE`; `NOT_FINAL_PAPER_RESULT = TRUE`
- `FINAL_TEST_ACCESS_COUNT = 0`; `PAPER_FULL_RUN = FALSE`; `LLM_TO_MODEL_FEEDBACK = FALSE`
- Status: `COMPLETED`; closure `AIR_SLOT_LLM_AUDIT_V2_CLOSURE`; auxiliary/evaluation-only

## Design

- Decision: `AIR_SLOT_LLM_AUDIT_V2_STATE_CONDITIONED_EXPLANATION`; model `deepseek-v4-flash`; rule `COST_FIRST_WITH_QUALITY_GATE`; `model_escalation_occurred=false`
- Purpose: state-conditioned operational reasonableness explanation of frozen Development recommendations; it does not validate the model and cannot alter M3/M4

## Pilot

- N = 50; schema pass rate 0.98; parse failure rate 0.02; unsupported-fact-assertion rate 0.0; known-false-prerequisite-ignored rate 0.0; unknown-prerequisite-asserted-true rate 0.0; status `PASS`

## Principal

- 128 episodes x 3 repetitions = 382 judgements

| Judgement | N | Percentage |
|---|---|---|
| ACCEPT | 15 | 3.9267% |
| ACCEPT_WITH_RESERVATIONS | 268 | 70.1571% |
| REJECT | 0 | 0.0000% |
| INSUFFICIENT_INFORMATION | 99 | 25.9162% |

Repeat exact agreement 0.453125; accept-family agreement 0.453125; confidence HIGH 95 / MEDIUM 264 / LOW 23; missing-information overlap 0.00025201612903225806.

## Interpretation

Most model outputs were judged operationally plausible only with explicit reservations (70.16%), while a substantial minority could not be responsibly assessed from the current state information (25.92%). This is an auxiliary operational reasonableness audit; it does not validate the model and was not used to alter M3/M4.

## Provenance

- Prompt hash `sha256:771121de45de8db5f68f7e6d7757c992996592e07e9061ce843090d5bfb7c8af`; schema hash `sha256:16ca615e308e505744cdcb3c4446565254116c3423f11a035b625b460dcf88cc`; audit contract hash `sha256:8cc0b226d944022b5bb662c8bd2e08efe7d801407530d5a66ea8ef4dd4c9e350`
- Report: `llm_audit_v2/DEEPSEEK_LLM_AUDIT_REPORT_V2.json`; evidence `EXP234_LLM_AUDIT_PILOT_EVIDENCE_V2.json`; diagnostic `EXP234_LLM_AUDIT_PILOT_DIAGNOSTIC_V2.json` (local freeze namespace)
- V1 pilot preserved as `DIAGNOSTIC_FAIL_UNDER_SUPERSEDED_AUDIT_CONSTRUCT` (`EXP234_LLM_AUDIT_PILOT_EVIDENCE_V1.json`)

