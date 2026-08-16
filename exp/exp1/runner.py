from exp.common.runner import BaseRunner
class Exp1Runner(BaseRunner):
    experiment="exp1";variants=("empirical","current","fixed_history","adaptive_history","independent_heads","leakage_diagnostic")
