from exp.common.runner import BaseRunner
class Exp4Runner(BaseRunner):
    experiment="exp4";variants=("m1_hidden_16","m1_hidden_32","roll_5","roll_10","m2_low","m2_base","m2_high","m3_low","m3_base","m3_high","m4_lambda_0","m4_lambda_10","m4_lambda_25","m4_lambda_50","alpha_80","alpha_90","alpha_95","mc_250","mc_500","mc_1000","mc_2000")
    protocol_variants=(
        "RISK_POLICY_SENSITIVITY", "NORMATIVE_VALUATION_SENSITIVITY",
        "SCENARIO_RESPONSE_SENSITIVITY", "ROLL_SENSITIVITY",
        "MONTE_CARLO_CONVERGENCE", "OPERATIONAL_BOUNDARY",
        "DATA1_PORTABILITY", "DEPLOYABILITY_STATE_AWARE_FAST",
    )
    principal_deployment_scenarios=1000
    e2e_p95_gate_seconds=300
