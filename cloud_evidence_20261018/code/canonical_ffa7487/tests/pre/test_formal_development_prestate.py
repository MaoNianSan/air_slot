from __future__ import annotations

import json
from pathlib import Path

from model.PRE.contracts.pre_state import PREState
from validation.model import materialize_m1_formal_development_prestate as freeze


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _states() -> list[dict]:
    return [json.loads(line) for line in freeze.STATES_PATH.read_text(encoding="utf-8").splitlines()]


def test_frozen_reservoir_ids_exactly_match_formal_cohort():
    cohort = _read(freeze.COHORT_PATH)
    partitions, _ = freeze.load_frozen_partitions(cohort)
    for split, episodes in partitions.items():
        assert tuple(item.episode_id for item in episodes) == tuple(
            sorted(cohort[f"{split}_episode_ids"])
        )


def test_materializer_does_not_select_or_import_exp1():
    source = Path(freeze.__file__).read_text(encoding="utf-8")
    assert "episode_reservoirs(" not in source
    assert "build_sampled_pre_cohorts(" not in source
    assert "exp.exp1" not in source
    assert "PREState(" not in source


def test_formal_prestate_manifest_and_final_test_guards():
    manifest = _read(freeze.MANIFEST_PATH)
    audit = _read(freeze.AUDIT_PATH)
    assert manifest["status"] == audit["status"] == "PASS"
    assert manifest["selection_reperformed"] is False
    assert manifest["development_episode_count"] == 128
    assert manifest["final_test_episode_count"] == 0
    assert manifest["final_test_access_count"] == 0
    assert audit["test_episode_materialized"] is False
    assert audit["episode_ids_exact_match"] is True


def test_prestate_serialization_roundtrip_and_node_uniqueness():
    rows = _states()
    assert rows
    for row in (rows[0], rows[len(rows) // 2], rows[-1]):
        PREState.model_validate(row)
    keys = [
        (row["decision_node"]["episode_id"], row["decision_node"]["decision_node_id"])
        for row in rows
    ]
    assert len(keys) == len(set(keys))
    assert all(row["decision_node"]["decision_time"] < "2019-10-01" for row in rows)


def test_all_frozen_m1_development_nodes_have_prestate():
    audit = _read(freeze.AUDIT_PATH)
    assert audit["m1_cache_node_alignment"] == "PASS"
    assert audit["cache_nodes_missing_prestate"] == 0
    assert audit["matched_node_count"] == audit["cache_node_count"]
