from __future__ import annotations

import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from action_contract import load_action_contract, v3_pre_action_contract
from ranking_contract import RANKING_DEPTHS


def test_all_metadata_uses_shared_ranking_depths() -> None:
    files = [
        PROJECT / "overall_run" / "src" / "pipeline_finalize.py",
        PROJECT / "overall_adv" / "src" / "pipeline.py",
        PROJECT / "part_adv" / "src" / "pipeline.py",
        PROJECT / "downstream_common.py",
        PROJECT / "overall_adv" / "src" / "pipeline_publication.py",
        PROJECT / "part_adv" / "src" / "pipeline_publication.py",
    ]
    repeated_literals = ("[1, 2, 3, 5]", "(1, 2, 3, 5)")
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert not any(literal in source for literal in repeated_literals), path
    for path in files[:4]:
        source = path.read_text(encoding="utf-8")
        assert "RANKING_DEPTHS" in source, path
    assert RANKING_DEPTHS == (1, 2, 3, 5)


def test_m3_action_inventory_has_one_v3_authority() -> None:
    contract = load_action_contract("V3")
    pre_contract = v3_pre_action_contract()
    assert pre_contract["action_ids"] == contract["action_ids"]
    assert pre_contract["formal_action_count"] == contract["formal_action_count"] == 26
    source_paths = [
        PROJECT / "overall_run" / "src" / "m3.py",
        PROJECT / "overall_run" / "src" / "config.py",
        PROJECT / "overall_run" / "src" / "selfcheck.py",
        PROJECT / "pre" / "config" / "actions.yaml",
    ]
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        assert "A71, A72, A73" not in source
        assert "A81, A82, A83" not in source
    assert "action_ids:" not in (PROJECT / "pre" / "config" / "actions.yaml").read_text(
        encoding="utf-8"
    )
