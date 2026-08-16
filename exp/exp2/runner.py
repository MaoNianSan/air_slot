from exp.common.runner import BaseRunner
class Exp2Runner(BaseRunner):
    experiment="exp2";variants=("point_flight","point_full","distributional_flight","distributional_full","shuffled_lineage")
    protocol_variants=("P-F","P-C","D-F","D-C","LINEAGE_CORRUPTION")
    reference_evaluator="ALIGNED_DISTRIBUTIONAL_FULL_FIXED_FORMAL_SCOPE_FULL_DECISION_CONTRACT"
    headline_metrics=("ActionGapDistortion","PairwiseRankingReversalRate","ReferenceObjectiveSelectionPenalty")
