from __future__ import annotations

import gc
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    config_hash,
    episode_reservoirs,
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    publish_episode_states,
    registry_hash,
    weather_index,
)


@dataclass(frozen=True)
class PREPreparedEpisode:
    episode: object
    successor_schedule: object
    predecessor_outcome: object
    successor_outcome: object
    nodes: tuple
    states: tuple


@dataclass(frozen=True)
class PREDevelopmentCohorts:
    train: tuple[PREPreparedEpisode, ...]
    calibration: tuple[PREPreparedEpisode, ...]
    development: tuple[PREPreparedEpisode, ...]
    audit: dict


def _publish_partition(
    episodes,
    items,
    *,
    config_hash_value: str,
    registry_hash_value: str,
    weather,
    weather_max_age_minutes: int,
    publisher: ProductionPREPublisher,
    taxi_reference=None,
    turnaround_reference=None,
):
    output = []
    stages = Counter()
    for episode in episodes:
        item = items[episode.episode_id]
        nodes, states = publish_episode_states(
            item,
            config_hash_value,
            registry_hash_value,
            weather,
            weather_max_age_minutes,
            publisher=publisher,
            taxi_reference=taxi_reference,
            turnaround_reference=turnaround_reference,
        )
        stages.update(node.operational_stage.value for node in nodes)
        output.append(
            PREPreparedEpisode(
                episode=episode,
                successor_schedule=item[1],
                predecessor_outcome=item[2],
                successor_outcome=item[3],
                nodes=tuple(nodes),
                states=tuple(states),
            )
        )
    return tuple(output), dict(stages)


def build_sampled_pre_cohorts(
    scientific,
    *,
    root: Path,
    cohort_counts: dict[str, int],
    cohort_seed: int,
    preparation_state: Path,
    preparation_manifest: Path,
    resume: bool = True,
    heartbeat=None,
    taxi_reference=None,
    turnaround_reference=None,
) -> PREDevelopmentCohorts:
    """Build Development-safe typed PRE states without invoking M1."""
    paths = ontime_paths(root)
    data2_root = root / "data2"
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    reservoirs, pool_sizes, total_episodes, per_month, skipped = episode_reservoirs(
        root,
        paths,
        zones,
        cohort_counts=cohort_counts,
        cohort_seed=cohort_seed,
        state_path=preparation_state,
        manifest_path=preparation_manifest,
        resume=resume,
        heartbeat=heartbeat,
    )
    if reservoirs["test"]:
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    partitions = {
        name: tuple(sorted(reservoirs[name], key=lambda item: item.episode_id))
        for name in ("train", "calibration", "development")
    }
    selected = partitions["train"] + partitions["calibration"] + partitions["development"]
    del reservoirs
    gc.collect()
    schedules, outcomes = load_selected_typed_records(
        selected, paths, zones, heartbeat=heartbeat
    )
    items = {
        episode.episode_id: (
            episode,
            schedules[episode.successor_flight_id],
            outcomes[episode.predecessor_flight_id],
            outcomes[episode.successor_flight_id],
        )
        for episode in selected
    }
    replay_lag = int(
        scientific.parameters["data2_weather_replay_lag_minutes"].value
    )
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        data2_root, replay_lag, heartbeat=heartbeat
    )
    config_hash_value, registry_hash_value = config_hash(root), registry_hash(root)
    publisher = ProductionPREPublisher.from_project()
    published = {}
    stage_counts = {}
    for name in ("train", "calibration", "development"):
        published[name], stage_counts[name] = _publish_partition(
            partitions[name],
            items,
            config_hash_value=config_hash_value,
            registry_hash_value=registry_hash_value,
            weather=weather,
            weather_max_age_minutes=max_age,
            publisher=publisher,
            taxi_reference=taxi_reference,
            turnaround_reference=turnaround_reference,
        )
    audit = {
        "cohort_seed": cohort_seed,
        "cohort_counts": cohort_counts,
        "sampled_episodes": {
            name: len(partitions[name]) for name in partitions
        },
        "pre_decision_nodes": {
            name: sum(len(item.nodes) for item in published[name]) for name in published
        },
        "stage_counts": stage_counts,
        "pool_sizes": pool_sizes,
        "total_episode_pool": total_episodes,
        "ontime_rows_by_month": per_month,
        "ontime_rows_skipped": skipped,
        "weather": weather_audit,
        "config_hash": config_hash_value,
        "registry_hash": registry_hash_value,
        "final_test_access_count": 0,
    }
    return PREDevelopmentCohorts(
        train=published["train"],
        calibration=published["calibration"],
        development=published["development"],
        audit=audit,
    )
