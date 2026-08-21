"""M1 V2 performance closure: cache store, microbatch equivalence, bucketing."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import torch

from model.M1.cache import (
    REQUIRED_CONTRACT_HASHES,
    M1DevelopmentBaseCache,
    cache_key,
)
from model.M1.data import fit_train_normalization
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.pipeline import M1Pipeline
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.streaming.data2 import aircraft_tail


TARGETS = ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX")
LOGIT_KEYS = ("T_IB_REMAINING_HAZARD", "D_OB_zero", "D_OB_quantile",
              "D_TX_zero", "D_TX_quantile")


def _example(episode, day, length, offset, *, node=None, static_values=None,
             static_context_lineage=None):
    return M1TrainingExample(
        episode_id=episode,
        episode_date=day,
        values=torch.arange(length * 4, dtype=torch.float32).reshape(length, 4) / 10 + offset,
        targets={name: (offset + index) % 6 for index, name in enumerate(TARGETS)},
        active={"T_IB_REMAINING_HAZARD": True, "D_OB": offset % 2 == 0, "D_TX": True},
        decision_node_id=node or f"{episode}-n{length}",
        static_values=static_values,
        static_context_lineage=static_context_lineage,
    )


def _contracts():
    return {name: f"sha256:{index:064x}"
            for index, name in enumerate(REQUIRED_CONTRACT_HASHES, start=1)}


def _cache(partitions):
    normalization = fit_train_normalization([], split="train")
    contracts = _contracts()
    key = cache_key(
        source_manifest_hash="sha256:" + "a" * 64,
        contract_hashes=contracts,
        cohort_counts={name: len(values) for name, values in partitions.items()},
        cohort_seed=7,
    )
    return M1DevelopmentBaseCache.from_partitions(
        partitions=partitions,
        normalization=normalization,
        audit={"final_test_access_count": 0},
        cache_key=key,
        source_manifest_hash="sha256:" + "a" * 64,
        contract_hashes=contracts,
    )


def test_cache_roundtrip_and_history_views(tmp_path: Path):
    long_e1 = _example("e1", date(2019, 6, 1), 5, 0)
    short_e1 = M1TrainingExample(
        episode_id=long_e1.episode_id,
        episode_date=long_e1.episode_date,
        values=long_e1.values[:2],
        targets=dict(long_e1.targets),
        active=dict(long_e1.active),
        decision_node_id="e1-n2",
    )
    examples = (
        short_e1,
        long_e1,
        _example("e2", date(2019, 6, 2), 3, 2),
    )
    cache = _cache({"train": examples, "calibration": (), "development": ()})
    data_path = tmp_path / "cache.npz"
    manifest_path = tmp_path / "manifest.json"
    manifest = cache.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=manifest["cache_key"])

    adaptive = loaded.partition("train")
    fixed = loaded.partition("train", representation="FIXED_HISTORY", window_minutes=10)
    current = loaded.partition("train", representation="CURRENT")
    assert [len(row.values) for row in adaptive] == [2, 5, 3]
    assert [len(row.values) for row in fixed] == [2, 3, 3]
    assert [len(row.values) for row in current] == [1, 1, 1]
    assert [row.decision_node_id for row in adaptive] == [row.decision_node_id for row in examples]
    assert manifest["final_test_included"] is False
    assert manifest["final_test_access_count"] == 0


def test_cache_roundtrip_preserves_static_context(tmp_path: Path):
    lineages = (
        {"context_id": "static-a", "source_hash": "sha256:aaa"},
        {"context_id": "static-b", "source_hash": "sha256:bbb"},
    )
    examples = tuple(
        _example(
            f"e{index}", date(2019, 6, index + 1), 3, index,
            static_values=torch.tensor([index, index + 0.5], dtype=torch.float32),
            static_context_lineage=lineage,
        )
        for index, lineage in enumerate(lineages, start=1)
    )
    cache = _cache({"train": examples, "calibration": (), "development": ()})
    data_path = tmp_path / "cache.npz"
    manifest_path = tmp_path / "manifest.json"
    manifest = cache.save(data_path, manifest_path)
    loaded = M1DevelopmentBaseCache.load(
        data_path, manifest_path, expected_cache_key=manifest["cache_key"])

    assert manifest["static_feature_count"] == 2
    assert torch.equal(loaded.store.static_values, torch.tensor(
        [[1.0, 1.5], [2.0, 2.5]], dtype=torch.float32))
    assert loaded.store.static_context_lineages == lineages
    restored = loaded.partition("train")
    assert torch.equal(restored[0].static_values, examples[0].static_values)
    assert restored[1].static_context_lineage == lineages[1]


def test_cache_rejects_final_test_example():
    with pytest.raises(ValueError, match="M1_CACHE_FINAL_TEST_EXAMPLE_REJECTED"):
        _cache({"train": (), "calibration": (), "development": (
            _example("test", date(2019, 10, 1), 2, 0),)})


def test_cache_requires_complete_contract_key():
    with pytest.raises(ValueError, match="M1_CACHE_CONTRACT_HASH_MISSING"):
        cache_key(
            source_manifest_hash="sha256:" + "a" * 64,
            contract_hashes={}, cohort_counts={}, cohort_seed=7)


def test_microbatch_gradient_and_batched_inference_match_fullbatch():
    examples = tuple(_example(f"e{index}", date(2019, 6, 1), index + 2, index)
                     for index in range(8))
    initial = M1Pipeline.smoke(4).model.state_dict()
    full = M1Pipeline.smoke(4)
    micro = M1Pipeline.smoke(4)
    full.model.load_state_dict(initial)
    micro.model.load_state_dict(initial)
    full_lifecycle = M1Lifecycle(full)
    micro_lifecycle = M1Lifecycle(micro)

    full_history = full_lifecycle.train(
        examples, epochs=1, learning_rate=0.01, batch_size=None, seed=7)
    micro_history = micro_lifecycle.train(
        examples, epochs=1, learning_rate=0.01, batch_size=3, seed=7)
    assert full_history[0]["loss"] == pytest.approx(micro_history[0]["loss"], abs=1e-6)
    assert micro_history[0]["optimizer_steps"] == 1
    for left, right in zip(full.model.parameters(), micro.model.parameters()):
        assert torch.allclose(left, right, rtol=1e-5, atol=1e-6)

    full_logits, full_labels, full_active, full_zero = full_lifecycle.batched_logits(
        examples, batch_size=None)
    batched_logits, batched_labels, batched_active, batched_zero = full_lifecycle.batched_logits(
        examples, batch_size=3)
    for name in LOGIT_KEYS:
        assert torch.allclose(full_logits[name], batched_logits[name], rtol=1e-5, atol=1e-6)
    for name in TARGETS:
        assert torch.equal(full_labels[name], batched_labels[name])
        assert torch.equal(full_active[name], batched_active[name])


def test_length_bucketing_reduces_padding():
    examples = tuple(_example(f"e{index}", date(2019, 6, 1), length, index)
                     for index, length in enumerate((2, 20, 3, 19, 4, 18, 5, 17)))
    global_padding = M1Lifecycle.batching_diagnostics(
        examples, batch_size=None, bucketed=False)
    bucketed = M1Lifecycle.batching_diagnostics(
        examples, batch_size=2, bucketed=True)
    assert bucketed["padding_fraction"] < global_padding["padding_fraction"]


def _flight(flight_id, aircraft, start_hour):
    scheduled_departure = datetime(2019, 1, 1, start_hour, tzinfo=timezone.utc)
    scheduled_arrival = scheduled_departure + timedelta(hours=1)
    return {
        "flight_id": flight_id,
        "aircraft_id": aircraft,
        "aircraft_id_namespace": "REGISTRATION",
        "origin_airport_id": "A",
        "destination_airport_id": "A",
        "event_start_time": scheduled_departure,
        "event_end_time": scheduled_arrival,
        "actual_departure_utc": scheduled_departure + timedelta(minutes=5),
        "actual_arrival_utc": scheduled_arrival + timedelta(minutes=5),
        "dataset_instance_id": "data2_2019",
    }


def test_cross_month_aircraft_tail_preserves_current_month_pairs():
    previous = [
        _flight("A1", "A", 1), _flight("A2", "A", 4),
        _flight("B1", "B", 2), _flight("B2", "B", 5),
    ]
    current = [_flight("A3", "A", 7), _flight("B3", "B", 8)]
    current_ids = {row["flight_id"] for row in current}
    baseline = {
        episode.episode_id for episode in build_data2_episode_records(previous + current)
        if episode.successor_flight_id in current_ids
    }
    optimized = {
        episode.episode_id for episode in build_data2_episode_records(
            list(aircraft_tail(previous)) + current)
        if episode.successor_flight_id in current_ids
    }
    assert optimized == baseline
