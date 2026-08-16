from exp.common.runner import BaseRunner
class Exp1Runner(BaseRunner):
    experiment="exp1";variants=("empirical","current","fixed_history","adaptive_history","independent_heads","leakage_diagnostic")
    protocol_variants=("CURRENT","FIXED_HISTORY","ADAPTIVE_HISTORY","RETROSPECTIVE_LEAKAGE_DIAGNOSTIC")
    headline_comparison=("ADAPTIVE_HISTORY","FIXED_HISTORY")
    headline_metric="DecisionWindowGain"
