import json
from pathlib import Path

from exp.exp2.formal_development import VARIANTS, run_formal_development


ROOT = Path(__file__).resolve().parents[2]


def test_formal_development_records_all_variants_and_preserves_guards(tmp_path):
    paths = run_formal_development(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    lineage = json.loads(paths["lineage"].read_text(encoding="utf-8"))

    assert manifest["status"] == "EXP2_FORMAL_EXECUTION_COMPLETE"
    assert tuple(manifest["variants"]) == VARIANTS
    assert manifest["m1_binding"]["model_id"] == "M1_V2_GRU_H32"
    assert manifest["safety"] == {
        "M1_TRAINING_RUNS_THIS_EXECUTION": 0,
        "TUNING_RUNS_THIS_EXECUTION": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "FULL": False,
        "PAPER_FULL_RUN": False,
    }
    assert set(metrics["variants"]) == set(VARIANTS)
    assert all(
        row["execution_status"] == "BLOCKED_BEFORE_METRIC_GENERATION"
        for row in metrics["variants"].values()
    )
    assert lineage["gates"]["M1_COHORT_BINDING"]["intersection_nodes"] == 0
    assert lineage["gates"]["M1_POSITIVE_TAIL"]["policy"] == "UNRESOLVED"
    assert lineage["FINAL_TEST_ACCESS_COUNT"] == 0
    assert lineage["PAPER_FULL_RUN"] is False
