from __future__ import annotations

import gc
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from model.PRE.cohort import split_for_date
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.episode.node_builder import build_rolling_decision_nodes
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    config_hash,
    development_source_manifest_hash,
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


def development_input_identity(root: Path) -> dict[str, str]:
    """Return PRE-owned Development input identities for downstream lineage."""
    return {
        "source_manifest_hash": development_source_manifest_hash(root),
        "config_hash": config_hash(root),
        "registry_hash": registry_hash(root),
    }


def eligible_development_episodes_from_rows(rows: list[dict], *,
                                            split_resolver=None):
    """Yield split-contained Development episodes from PRE-canonical rows."""
    by_id = {row["flight_id"]: row for row in rows}
    for episode in build_data2_episode_records(rows):
        successor_date = date.fromisoformat(
            by_id[episode.successor_flight_id]["service_date"]
        )
        resolve_split = split_resolver or split_for_date
        if resolve_split(successor_date) != "development":
            continue
        containment = episode_containment_from_rows(
            episode, by_id, split_resolver=resolve_split)
        if containment.allowed and containment.split == "development":
            yield episode, by_id


def build_development_episode_nodes(
    root: Path,
    episodes: tuple[object, ...],
    paths: tuple[Path, ...],
    zones: dict[str, str],
    *,
    split_resolver=None,
):
    """Construct the PRE-owned rolling grid for selected Development episodes."""
    schedules, outcomes = load_selected_typed_records(episodes, paths, zones)
    config_hash_value = config_hash(root)
    registry_hash_value = registry_hash(root)
    nodes = []
    for episode in episodes:
        episode_nodes = build_rolling_decision_nodes(
            episode=episode,
            predecessor_outcome=outcomes[episode.predecessor_flight_id],
            successor_outcome=outcomes[episode.successor_flight_id],
            config_hash=config_hash_value,
            registry_hash=registry_hash_value,
            legal_record_ids=episode.source_record_ids,
        )
        resolve_split = split_resolver or split_for_date
        if any(
            resolve_split(node.decision_time.date()) != "development"
            for node in episode_nodes
        ):
            raise RuntimeError("PRE_DEVELOPMENT_NODE_SPLIT_VIOLATION")
        nodes.extend(episode_nodes)
    return tuple(nodes), config_hash_value, registry_hash_value


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
    dataset_instance_id: str = "data2_2019",
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
            dataset_instance_id=dataset_instance_id,
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


def materialize_preselected_cohorts(
    scientific,
    *,
    root: Path,
    partitions: dict[str, tuple],
    selection_audit: dict | None = None,
    heartbeat=None,
    taxi_reference=None,
    turnaround_reference=None,
    year: int = 2019,
    dataset_instance_id: str = "data2_2019",
    split_resolver=None,
) -> PREDevelopmentCohorts:
    """Publish PRE states for already selected non-Test episode reservoirs.

    M4b: ``year`` / ``dataset_instance_id`` / ``split_resolver``
    parameterize the flow for the data2_2017_2022 instance; the defaults
    reproduce the legacy data2_2019 behavior exactly."""
    expected = {"train", "calibration", "development"}
    if set(partitions) != expected:
        raise ValueError("PRE_PRESELECTED_PARTITIONS_INVALID")
    all_ids = [
        episode.episode_id
        for name in ("train", "calibration", "development")
        for episode in partitions[name]
    ]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("PRE_PRESELECTED_EPISODE_DUPLICATE")

    paths = ontime_paths(root, year=year)
    data2_root = root / "data2"
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    selected = tuple(
        episode
        for name in ("train", "calibration", "development")
        for episode in partitions[name]
    )
    schedules, outcomes = load_selected_typed_records(
        selected, paths, zones, heartbeat=heartbeat,
        dataset_instance_id=dataset_instance_id,
    )
    resolve_split = split_resolver or split_for_date
    for name in ("train", "calibration", "development"):
        if any(
            resolve_split(schedules[episode.successor_flight_id].service_date)
            != name
            for episode in partitions[name]
        ):
            raise ValueError(f"PRE_PRESELECTED_SPLIT_VIOLATION:{name}")
    items = {
        episode.episode_id: (
            episode,
            schedules[episode.successor_flight_id],
            outcomes[episode.predecessor_flight_id],
            outcomes[episode.successor_flight_id],
        )
        for episode in selected
    }
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        data2_root,
        replay_lag,
        heartbeat=heartbeat,
        end_exclusive=date(year, 10, 1),
        stamp_year=str(year),
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
            dataset_instance_id=dataset_instance_id,
        )
    audit = {
        **(selection_audit or {}),
        "sampled_episodes": {name: len(partitions[name]) for name in partitions},
        "pre_decision_nodes": {
            name: sum(len(item.nodes) for item in published[name]) for name in published
        },
        "stage_counts": stage_counts,
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
    additional_development=(),
    year: int = 2019,
    dataset_instance_id: str = "data2_2019",
    split_resolver=None,
) -> PREDevelopmentCohorts:
    """Build Development-safe typed PRE states without invoking M1."""
    paths = ontime_paths(root, year=year)
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
        year=year,
        dataset_instance_id=dataset_instance_id,
        split_resolver=split_resolver,
    )
    if reservoirs["test"]:
        raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
    partitions = {
        name: tuple(sorted(reservoirs[name], key=lambda item: item.episode_id))
        for name in ("train", "calibration", "development")
    }
    extra_development = tuple(additional_development)
    if extra_development:
        existing_ids = {
            item.episode_id for values in partitions.values() for item in values
        }
        duplicate_ids = existing_ids & {item.episode_id for item in extra_development}
        if duplicate_ids:
            raise ValueError(
                f"PRE_ADDITIONAL_DEVELOPMENT_DUPLICATE:{sorted(duplicate_ids)}"
            )
        development_floor = date(year, 8, 1).isoformat()
        development_ceiling = date(year, 9, 30).isoformat()
        if any(
            item.episode_start_time.date().isoformat() < development_floor
            or item.episode_end_time.date().isoformat() > development_ceiling
            for item in extra_development
        ):
            raise ValueError("PRE_ADDITIONAL_DEVELOPMENT_SPLIT_VIOLATION")
        partitions["development"] = tuple(
            sorted(
                partitions["development"] + extra_development,
                key=lambda item: item.episode_id,
            )
        )
    del reservoirs
    gc.collect()
    selection_audit = {
        "cohort_seed": cohort_seed,
        "cohort_counts": cohort_counts,
        "additional_development_episode_count": len(extra_development),
        "pool_sizes": pool_sizes,
        "total_episode_pool": total_episodes,
        "ontime_rows_by_month": per_month,
        "ontime_rows_skipped": skipped,
    }
    return materialize_preselected_cohorts(
        scientific,
        root=root,
        partitions=partitions,
        selection_audit=selection_audit,
        heartbeat=heartbeat,
        taxi_reference=taxi_reference,
        turnaround_reference=turnaround_reference,
        year=year,
        dataset_instance_id=dataset_instance_id,
        split_resolver=split_resolver,
    )
