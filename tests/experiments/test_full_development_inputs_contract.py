"""Contract test for the frozen Data2 full-Development input artifact.

Offline, read-only.  Verifies that the materialized
``full_development_inputs_v1`` artifact is exactly the frozen M1 B2
Development cache: 1769 active nodes across the 128 Development episodes,
per-episode identity (historical id / node index / decision time / prefix
shape / active flags / target values), artifact-hash reproducibility, and
the Final Test hard wall.  Nothing is rebuilt.
"""

import json
from datetime import datetime
from pathlib import Path

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.data import FEATURE_NAMES_V2
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "experiment" / "full_development_inputs_v1"
CACHE_DIR = ROOT / "artifacts" / "diagnostics" / "m1_v2_feature_gate_b2"
CACHE = CACHE_DIR / "M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz"
CACHE_MANIFEST = CACHE_DIR / "M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json"
BINDING = ROOT / "artifacts" / "diagnostics" / "exp1_formal_execution_preparation" / "EXP1_M1_V2_ARTIFACT_BINDING.json"

NODE_COUNT = 1769
EPISODE_COUNT = 128
TARGET_NAMES = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
EXPECTED_STAGES = {"PRE_IB": 217, "POST_IB_PRE_OB": 1454, "POST_OB_PRE_TO": 98}


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _manifest() -> dict:
    return _load("FULL_DEVELOPMENT_INPUT_MANIFEST.json")


def _cache() -> M1DevelopmentBaseCache:
    manifest = _load_path(CACHE_MANIFEST)
    return M1DevelopmentBaseCache.load(
        CACHE, CACHE_MANIFEST, expected_cache_key=manifest["cache_key"]
    )


def _load_path(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _inputs_hash_candidates(payload: dict) -> tuple[str, ...]:
    """The recorded hash was computed over in-memory lineage datetimes (UTC Z);
    the file persists isoformat strings (+00:00).  Accept both forms."""
    payload = {key: value for key, value in payload.items() if key != "artifact_hash"}

    def zify(value):
        if isinstance(value, str):
            return value.replace("+00:00", "Z")
        if isinstance(value, dict):
            return {key: zify(item) for key, item in value.items()}
        if isinstance(value, list):
            return [zify(item) for item in value]
        return value

    as_loaded = dict(payload)
    lineage_z = dict(payload)
    lineage_z["inference_inputs"] = [
        {**row, "static_reference_lineage": zify(row["static_reference_lineage"])}
        for row in lineage_z["inference_inputs"]
    ]
    return content_id(as_loaded), content_id(lineage_z)


def test_manifest_contract_counts_and_safety():
    manifest = _manifest()
    assert manifest["schema_version"] == "AIR_SLOT_FULL_DEVELOPMENT_INPUT_MANIFEST_V1"
    assert manifest["status"] == "FULL_DEVELOPMENT_INPUTS_READY"
    assert manifest["episode_count"] == EPISODE_COUNT
    assert manifest["node_count"] == NODE_COUNT
    assert manifest["cohort_hash"].startswith("sha256:")
    assert manifest["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def test_manifest_frozen_hashes_match_cache_and_binding():
    manifest = _manifest()
    cache_manifest = _load_path(CACHE_MANIFEST)
    binding = _load_path(BINDING)
    assert binding["model_id"] == "M1_V2_GRU_H32"
    frozen = manifest["frozen_hashes"]
    assert frozen["cache_hash"] == cache_manifest["cache_hash"] == binding["frozen_contracts"]["cache_hash"]
    assert frozen["schema_hash"] == cache_manifest["feature_schema_hash"] == binding["frozen_contracts"]["feature_schema_hash"]
    assert frozen["model_hash"] == binding["checkpoint"]["sha256"]
    assert frozen["support_hash"] == binding["frozen_contracts"]["support_hash"]
    assert cache_manifest["final_test_access_count"] == 0
    assert cache_manifest["final_test_included"] is False


def test_artifact_hashes_recomputable_from_files():
    manifest = _manifest()
    cohort = _load("DATA2_FULL_DEVELOPMENT_COHORT.json")
    labels = _load("M1_V2_FULL_DEVELOPMENT_LABELS.json")
    inputs = _load("M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json")
    assert content_id({k: v for k, v in cohort.items() if k != "artifact_hash"}) == manifest["artifact_hashes"]["cohort"]
    assert content_id({k: v for k, v in labels.items() if k != "artifact_hash"}) == manifest["artifact_hashes"]["labels"]
    assert manifest["artifact_hashes"]["inputs"] in _inputs_hash_candidates(inputs)


def test_cache_development_rows_equal_1769_and_pair_per_episode():
    manifest = _manifest()
    cohort = _load("DATA2_FULL_DEVELOPMENT_COHORT.json")
    inputs = _load("M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json")
    cache = _cache()
    cached = cache.partition("development", representation="ADAPTIVE_HISTORY")
    assert len(cached) == NODE_COUNT
    assert cache.manifest["partition_counts"]["development"] == NODE_COUNT

    by_episode: dict[str, list] = {}
    for example in cached:
        by_episode.setdefault(example.episode_id, []).append(example)
    for values in by_episode.values():
        values.sort(key=lambda item: len(item.values))
    assert set(by_episode) == set(cohort["episode_ids"]) == set(inputs["pre_states_by_episode"])

    by_episode_inputs: dict[str, list] = {}
    for row in inputs["inference_inputs"]:
        by_episode_inputs.setdefault(row["episode_id"], []).append(row)
    assert len(by_episode_inputs) == EPISODE_COUNT

    feature_count = cache.manifest["feature_count"]
    assert feature_count == len(FEATURE_NAMES_V2)
    seen_current: set[str] = set()
    for episode_id in by_episode:
        rows = by_episode_inputs[episode_id]
        cache_rows = by_episode[episode_id]
        assert len(rows) == len(cache_rows)
        for row, example in zip(rows, cache_rows, strict=True):
            assert row["historical_decision_node_id"] == example.decision_node_id
            assert row["prefix_length"] == len(example.values)
            assert len(row["encoded_adaptive_prefix"]) == row["prefix_length"]
            assert all(len(frame) == feature_count for frame in row["encoded_adaptive_prefix"])
            assert row["decision_node_id"] not in seen_current
            seen_current.add(row["decision_node_id"])
            assert any(bool(value) for value in example.active.values())
    assert len(seen_current) == NODE_COUNT
    assert len(inputs["inference_inputs"]) == NODE_COUNT


def test_lineage_decision_nodes_and_labels_consistent():
    cohort = _load("DATA2_FULL_DEVELOPMENT_COHORT.json")
    inputs = _load("M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json")
    labels = _load("M1_V2_FULL_DEVELOPMENT_LABELS.json")
    cache = _cache()
    cached = cache.partition("development", representation="ADAPTIVE_HISTORY")
    by_episode: dict[str, list] = {}
    for example in cached:
        by_episode.setdefault(example.episode_id, []).append(example)
    for values in by_episode.values():
        values.sort(key=lambda item: len(item.values))

    assert len(cohort["decision_nodes"]) == NODE_COUNT
    assert len(cohort["node_lineage"]) == NODE_COUNT
    assert len(cohort["node_ids"]) == NODE_COUNT
    assert len(set(cohort["node_ids"])) == NODE_COUNT
    node_by_id = {node["decision_node_id"]: node for node in cohort["decision_nodes"]}

    historical_by_episode: dict[str, list[str]] = {}
    for row in cohort["node_lineage"]:
        historical_by_episode.setdefault(row["episode_id"], []).append(row["historical_decision_node_id"])
        assert row["current_decision_node_id"] in node_by_id
        assert node_by_id[row["current_decision_node_id"]]["node_index"] == row["node_index"]

    for episode_id, values in by_episode.items():
        assert historical_by_episode[episode_id] == [example.decision_node_id for example in values]

    label_rows = labels["labels"]
    assert labels["row_count"] == NODE_COUNT * len(TARGET_NAMES)
    assert len(label_rows) == NODE_COUNT * len(TARGET_NAMES)
    assert labels["labels_are_model_inputs"] is False
    by_node: dict[str, dict[str, dict]] = {}
    for row in label_rows:
        by_node.setdefault(row["decision_node_id"], {})[row["target_name"]] = row
    assert len(by_node) == NODE_COUNT
    for episode_id, values in by_episode.items():
        rows = [row for row in inputs["inference_inputs"] if row["episode_id"] == episode_id]
        for row, example in zip(rows, values, strict=True):
            node = node_by_id[row["decision_node_id"]]
            assert datetime.fromisoformat(node["decision_time"]) == datetime.fromisoformat(row["decision_time"])
            assert datetime.fromisoformat(node["information_cutoff"]) == datetime.fromisoformat(row["information_cutoff"])
            labels_for_node = by_node[row["decision_node_id"]]
            for target in TARGET_NAMES:
                assert labels_for_node[target]["active"] == bool(example.active[target])
                assert labels_for_node[target]["exact_minutes"] == example.targets[target]
                assert labels_for_node[target]["historical_decision_node_id"] == example.decision_node_id


def test_stage_distribution_frozen():
    cohort = _load("DATA2_FULL_DEVELOPMENT_COHORT.json")
    assert cohort["stage_distribution"] == EXPECTED_STAGES
    assert sum(EXPECTED_STAGES.values()) == NODE_COUNT
