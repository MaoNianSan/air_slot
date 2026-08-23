import json
from pathlib import Path

from exp.exp3.action_consequence_literature_mapping import materialize
from model.M3.registry import PRINCIPAL_IDS


ROOT = Path(__file__).resolve().parents[3]


def test_consequence_mapping_covers_all_actions_without_effect_overclaim(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["status"] == "M3_ACTION_CONSEQUENCE_LITERATURE_MAPPING_MATERIALIZED"
    assert artifact["action_count"] == 23
    assert tuple(row["action_id"] for row in artifact["mapping_table"]) == PRINCIPAL_IDS
    assert all(row["literature"] for row in artifact["mapping_table"])
    assert all(row["effect_size_status"] == ("IDENTIFIED" if row["action_id"] == "A00" else "NOT_IDENTIFIED") for row in artifact["mapping_table"])
    assert artifact["formal_support_upgrade"] is False
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
