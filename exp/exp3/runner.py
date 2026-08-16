from exp.common.runner import BaseRunner
class Exp3Runner(BaseRunner):
    experiment="exp3";variants=("full_contract","no_induced","no_evidence_distinction","no_coverage_restriction","mean_only","mean_cvar")
    protocol_variants=("FULL_CONTRACT","NO_EVIDENCE_DISTINCTION","NO_MATERIAL_COVERAGE_GATE","NO_INDUCED_CONSEQUENCE","RISK_NEUTRAL")
    reliability_semantics="EVIDENTIAL_CONTRACTUAL_SUPPORTABILITY"
    headline_metrics=("FormalCoverage","InvalidatedTop1Rate","FormalDecisionLeadTime")
