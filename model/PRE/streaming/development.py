from __future__ import annotations

import json
import time
import gc
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import psutil
import torch

from model.common.enums import SupportState
from model.common.identity import content_id
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.containment import (
    episode_containment_from_rows,
    episode_node_count,
)
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    aircraft_tail,
    config_hash,
    latest_weather,
    lightweight_flights,
    load_timezones,
    ontime_paths,
    registry_hash,
    weather_index,
)


DEVELOPMENT_START = date(2019, 8, 1)
DEVELOPMENT_END = date(2019, 9, 30)
FINAL_TEST_START = date(2019, 10, 1)


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def pre_contract_hash(root: Path) -> str:
    paths = (
        root / "model" / "PRE" / "pipeline.py",
        root / "model" / "PRE" / "mapping.py",
        root / "model" / "PRE" / "episode" / "builder.py",
        root / "model" / "PRE" / "episode" / "containment.py",
        root / "model" / "PRE" / "episode" / "node_builder.py",
        root / "model" / "PRE" / "streaming" / "data2.py",
        root / "model" / "PRE" / "streaming" / "development.py",
    )
    return content_id(
        {str(path.relative_to(root)): _file_hash(path) for path in paths}
    )


def source_hashes(root: Path) -> dict[str, str]:
    paths = ontime_paths(root, months=(7, 8, 9))
    data2_root = root / "data2"
    paths += tuple(
        sorted((data2_root / "raw" / "weather" / "noaa" / "2019").glob("*.csv"))
    )
    paths += (
        data2_root / "refs" / "weather_station_map.csv",
        data2_root / "refs" / "us_airport_timezones.csv",
    )
    return {
        str(path.relative_to(root)): _file_hash(path)
        for path in paths
    }


@dataclass
class StreamCounts:
    source_rows: int = 0
    source_rows_skipped: int = 0
    carry_source_rows: int = 0
    candidate_episodes: int = 0
    constructed_episodes: int = 0
    pre_published_episodes: int = 0
    pre_eligible_episodes: int = 0
    decision_nodes: int = 0
    pre_eligible_nodes: int = 0
    abstain_episodes: int = 0
    insufficient_history_episodes: int = 0
    cross_split_removed_episodes: int = 0
    cross_split_removed_nodes: int = 0
    weather_supported_nodes: int = 0
    weather_abstain_nodes: int = 0
    target_support_counts: Counter = field(default_factory=Counter)
    variable_support_counts: Counter = field(default_factory=Counter)
    evidence_class_counts: Counter = field(default_factory=Counter)
    abstention_reason_counts: Counter = field(default_factory=Counter)
    history_length_counts: Counter = field(default_factory=Counter)
    weather_freshness_count: int = 0
    weather_freshness_sum_minutes: float = 0.0
    weather_freshness_min_minutes: float | None = None
    weather_freshness_max_minutes: float | None = None

    def as_dict(self) -> dict:
        freshness_mean = (
            None
            if not self.weather_freshness_count
            else self.weather_freshness_sum_minutes / self.weather_freshness_count
        )
        return {
            "source_rows": self.source_rows,
            "source_rows_skipped": self.source_rows_skipped,
            "carry_source_rows": self.carry_source_rows,
            "candidate_episodes": self.candidate_episodes,
            "constructed_episodes": self.constructed_episodes,
            "pre_published_episodes": self.pre_published_episodes,
            "pre_eligible_episodes": self.pre_eligible_episodes,
            "decision_nodes": self.decision_nodes,
            "pre_eligible_nodes": self.pre_eligible_nodes,
            "abstain_episodes": self.abstain_episodes,
            "insufficient_history_episodes": self.insufficient_history_episodes,
            "cross_split_removed_episodes": self.cross_split_removed_episodes,
            "cross_split_removed_nodes": self.cross_split_removed_nodes,
            "weather_supported_nodes": self.weather_supported_nodes,
            "weather_abstain_nodes": self.weather_abstain_nodes,
            "target_support_counts": dict(self.target_support_counts),
            "variable_support_counts": dict(self.variable_support_counts),
            "evidence_class_counts": dict(self.evidence_class_counts),
            "abstention_reason_counts": dict(self.abstention_reason_counts),
            "history_length_counts": {
                str(key): value for key, value in sorted(self.history_length_counts.items())
            },
            "weather_freshness_minutes": {
                "count": self.weather_freshness_count,
                "mean": freshness_mean,
                "min": self.weather_freshness_min_minutes,
                "max": self.weather_freshness_max_minutes,
            },
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "StreamCounts":
        counts = cls()
        scalar_names = (
            "source_rows",
            "source_rows_skipped",
            "carry_source_rows",
            "candidate_episodes",
            "constructed_episodes",
            "pre_published_episodes",
            "pre_eligible_episodes",
            "decision_nodes",
            "pre_eligible_nodes",
            "abstain_episodes",
            "insufficient_history_episodes",
            "cross_split_removed_episodes",
            "cross_split_removed_nodes",
            "weather_supported_nodes",
            "weather_abstain_nodes",
        )
        for name in scalar_names:
            setattr(counts, name, int(payload.get(name, 0)))
        for name in (
            "target_support_counts",
            "variable_support_counts",
            "evidence_class_counts",
            "abstention_reason_counts",
        ):
            setattr(counts, name, Counter(payload.get(name, {})))
        counts.history_length_counts = Counter(
            {int(key): value for key, value in payload.get("history_length_counts", {}).items()}
        )
        freshness = payload.get("weather_freshness_minutes", {})
        counts.weather_freshness_count = int(freshness.get("count", 0))
        counts.weather_freshness_sum_minutes = float(freshness.get("sum", 0.0))
        if not counts.weather_freshness_sum_minutes and counts.weather_freshness_count:
            counts.weather_freshness_sum_minutes = float(freshness.get("mean", 0.0)) * counts.weather_freshness_count
        counts.weather_freshness_min_minutes = freshness.get("min")
        counts.weather_freshness_max_minutes = freshness.get("max")
        return counts


def _node_count(episode) -> int:
    if episode.episode_start_time > episode.episode_end_time:
        raise RuntimeError("PRE_STREAM_NEGATIVE_EPISODE_WINDOW")
    return episode_node_count(
        episode_start_time=episode.episode_start_time,
        episode_end_time=episode.episode_end_time,
    )


def summarize_episode_publication(
    episode,
    *,
    weather,
    weather_max_age_minutes: int,
    target_support,
    minimum_history_nodes: int = 2,
) -> dict:
    """Aggregate exact PRE support/evidence semantics without retaining PREState objects."""
    node_count = _node_count(episode)
    target_supported = [
        item
        for item in target_support
        if item.active and item.support_state is SupportState.SUPPORTED
    ]
    weather_supported = 0
    freshness = []
    decision_time = episode.episode_start_time
    for _ in range(node_count):
        observation = latest_weather(
            weather,
            episode.connection_airport_id,
            decision_time,
            weather_max_age_minutes,
        )
        if observation is not None:
            weather_supported += 1
            freshness.append(
                (decision_time - observation.availability_time).total_seconds() / 60.0
            )
        decision_time += timedelta(minutes=5)
    return {
        "node_count": node_count,
        "eligible_nodes": node_count if target_supported else 0,
        "eligible_episode": bool(target_supported and node_count),
        "abstain_episode": not bool(target_supported and node_count),
        "insufficient_history": node_count < minimum_history_nodes,
        "weather_supported_nodes": weather_supported,
        "weather_abstain_nodes": node_count - weather_supported,
        "weather_freshness_minutes": freshness,
    }


def _merge_episode(
    counts: StreamCounts,
    summary: dict,
    target_support,
) -> None:
    node_count = summary["node_count"]
    counts.pre_published_episodes += 1
    counts.decision_nodes += node_count
    counts.pre_eligible_nodes += summary["eligible_nodes"]
    counts.weather_supported_nodes += summary["weather_supported_nodes"]
    counts.weather_abstain_nodes += summary["weather_abstain_nodes"]
    counts.history_length_counts[node_count] += 1
    if summary["eligible_episode"]:
        counts.pre_eligible_episodes += 1
    if summary["abstain_episode"]:
        counts.abstain_episodes += 1
    if summary["insufficient_history"]:
        counts.insufficient_history_episodes += 1
    for item in target_support:
        counts.target_support_counts[
            f"{item.target_name}:{item.support_state.value}"
        ] += node_count
    counts.variable_support_counts["schedule_reference:SUPPORTED"] += node_count
    counts.variable_support_counts[
        "current_weather:SUPPORTED"
    ] += summary["weather_supported_nodes"]
    counts.variable_support_counts[
        "current_weather:ABSTAIN"
    ] += summary["weather_abstain_nodes"]
    counts.variable_support_counts["predecessor_motion:ABSTAIN"] += node_count
    counts.evidence_class_counts["schedule_reference:DIRECT"] += node_count
    counts.evidence_class_counts[
        "current_weather:DIRECT"
    ] += summary["weather_supported_nodes"]
    counts.abstention_reason_counts[
        "current_weather:NO_LEGAL_RECORD_AT_DECISION_TIME_OR_STALE"
    ] += summary["weather_abstain_nodes"]
    counts.abstention_reason_counts["predecessor_motion:NO_TRAJECTORY"] += node_count
    for value in summary["weather_freshness_minutes"]:
        counts.weather_freshness_count += 1
        counts.weather_freshness_sum_minutes += value
        counts.weather_freshness_min_minutes = (
            value
            if counts.weather_freshness_min_minutes is None
            else min(counts.weather_freshness_min_minutes, value)
        )
        counts.weather_freshness_max_minutes = (
            value
            if counts.weather_freshness_max_minutes is None
            else max(counts.weather_freshness_max_minutes, value)
        )


def _heartbeat(started: float, *, month: int, episodes: int, nodes: int) -> None:
    process = psutil.Process()
    print(
        json.dumps(
            {
                "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "PHASE": "PRE_DEVELOPMENT_STREAM",
                "CURRENT_MONTH": f"2019-{month:02d}",
                "EPISODES_PROCESSED": episodes,
                "DECISION_NODES_PROCESSED": nodes,
                "ELAPSED_SECONDS": round(time.perf_counter() - started, 3),
                "RSS_MB": round(process.memory_info().rss / 1024**2, 3),
                "FINAL_TEST_ACCESS_COUNT": 0,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def run_development_pre_stream(
    scientific,
    *,
    root: Path,
    manifest_path: Path,
    resume_path: Path,
    minimum_history_nodes: int = 2,
    heartbeat_seconds: float = 45.0,
    max_episodes: int | None = None,
) -> dict:
    if max_episodes is not None and manifest_path.name == "PRE_DEVELOPMENT_STREAM_MANIFEST.json":
        raise RuntimeError("OFFICIAL_PRE_STREAM_MANIFEST_REJECTS_SAMPLED_RUN")
    started = time.perf_counter()
    process = psutil.Process()
    peak_rss_mb = process.memory_info().rss / 1024**2
    registry_hash_value = registry_hash(root)
    config_hash_value = config_hash(root)
    contract_hash = pre_contract_hash(root)
    sources = source_hashes(root)
    run_key = content_id(
        {
            "sources": sources,
            "registry_hash": registry_hash_value,
            "config_hash": config_hash_value,
            "PRE_contract_hash": contract_hash,
            "development_start": DEVELOPMENT_START.isoformat(),
            "development_end": DEVELOPMENT_END.isoformat(),
            "minimum_history_nodes": minimum_history_nodes,
        }
    )
    counts = StreamCounts()
    previous_rows = ()
    completed_months = []
    start_month = 7
    elapsed_before = 0.0
    prior_peak_rss_mb = 0.0
    if resume_path.is_file():
        payload = torch.load(resume_path, map_location="cpu", weights_only=False)
        if payload.get("run_key") == run_key:
            counts = StreamCounts.from_dict(payload.get("counts", {}))
            previous_rows = tuple(payload.get("previous_rows", ()))
            completed_months = list(payload.get("completed_months", ()))
            start_month = int(payload.get("next_month", 7))
            elapsed_before = float(payload.get("elapsed_seconds", 0.0))
            prior_peak_rss_mb = float(payload.get("peak_rss_mb", 0.0))
            peak_rss_mb = max(peak_rss_mb, prior_peak_rss_mb)
    paths = {month: path for month, path in zip((7, 8, 9), ontime_paths(root, (7, 8, 9)))}
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    weather_max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        root / "data2",
        replay_lag,
        start_inclusive=date(2019, 7, 31),
        end_exclusive=FINAL_TEST_START,
    )
    publisher = ProductionPREPublisher.from_project()
    target_support = publisher.target_support("data2_2019")
    stopped_early = False
    last_heartbeat = time.perf_counter()
    for month in (7, 8, 9):
        if month < start_month:
            continue
        current_rows, skipped = lightweight_flights(paths[month], zones)
        if month == 7:
            counts.carry_source_rows = len(current_rows) + skipped
            previous_rows = aircraft_tail(current_rows)
        else:
            counts.source_rows += len(current_rows) + skipped
            counts.source_rows_skipped += skipped
            chunk = list(previous_rows) + current_rows
            by_id = {row["flight_id"]: row for row in chunk}
            month_key = f"2019-{month:02d}"
            episodes = []
            for episode in build_data2_episode_records(chunk):
                if by_id[episode.successor_flight_id].get("service_date", "")[:7] != month_key:
                    continue
                counts.candidate_episodes += 1
                containment = episode_containment_from_rows(episode, by_id)
                if not containment.allowed:
                    counts.cross_split_removed_episodes += 1
                    counts.cross_split_removed_nodes += _node_count(episode)
                    continue
                episodes.append(episode)
            counts.constructed_episodes += len(episodes)
            for episode in episodes:
                summary = summarize_episode_publication(
                    episode,
                    weather=weather,
                    weather_max_age_minutes=weather_max_age,
                    target_support=target_support,
                    minimum_history_nodes=minimum_history_nodes,
                )
                _merge_episode(counts, summary, target_support)
                now = time.perf_counter()
                peak_rss_mb = max(peak_rss_mb, process.memory_info().rss / 1024**2)
                if now - last_heartbeat >= heartbeat_seconds:
                    _heartbeat(
                        started,
                        month=month,
                        episodes=counts.pre_published_episodes,
                        nodes=counts.decision_nodes,
                    )
                    last_heartbeat = now
                if max_episodes is not None and counts.pre_published_episodes >= max_episodes:
                    stopped_early = True
                    break
            previous_rows = aircraft_tail(current_rows)
            del chunk, by_id, episodes
        del current_rows
        gc.collect()
        completed_months.append(f"2019-{month:02d}")
        cumulative_elapsed = elapsed_before + (time.perf_counter() - started)
        resume_payload = {
            "schema_version": "AIR_SLOT_PRE_DEVELOPMENT_STREAM_RESUME_V1",
            "run_key": run_key,
            "completed_months": completed_months,
            "next_month": month + 1,
            "previous_rows": previous_rows,
            "counts": {
                **counts.as_dict(),
                "weather_freshness_minutes": {
                    **counts.as_dict()["weather_freshness_minutes"],
                    "sum": counts.weather_freshness_sum_minutes,
                },
            },
            "elapsed_seconds": cumulative_elapsed,
            "peak_rss_mb": peak_rss_mb,
            "final_test_access_count": 0,
        }
        temporary_resume = resume_path.with_suffix(resume_path.suffix + ".tmp")
        torch.save(resume_payload, temporary_resume)
        temporary_resume.replace(resume_path)
        if stopped_early:
            break
    elapsed = elapsed_before + (time.perf_counter() - started)
    completion_status = "PARTIAL_ENGINEERING_SMOKE" if stopped_early else "PASS"
    manifest = {
        "schema_version": "AIR_SLOT_PRE_DEVELOPMENT_STREAM_MANIFEST_V2",
        "completion_status": completion_status,
        "run_key": run_key,
        "source_hashes": sources,
        "registry_hash": registry_hash_value,
        "scientific_config_hash": config_hash_value,
        "PRE_contract_hash": contract_hash,
        "development_date_bounds": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "minimum_history_nodes_for_count": minimum_history_nodes,
        "counts": counts.as_dict(),
        "old_pre_eligible_episodes": 951359,
        "old_pre_eligible_nodes": 13721540,
        "new_pre_eligible_episodes": counts.pre_eligible_episodes,
        "new_pre_eligible_nodes": counts.pre_eligible_nodes,
        "cross_split_removed_episodes": counts.cross_split_removed_episodes,
        "cross_split_removed_nodes": counts.cross_split_removed_nodes,
        "weather_audit": weather_audit,
        "elapsed_seconds": elapsed,
        "peak_rss_mb": peak_rss_mb,
        "resume_manifest": str(resume_path.relative_to(root)),
        "completed_months": completed_months,
        "bounded_memory_strategy": "MONTH_CHUNKS_WITH_LAST_AIRCRAFT_CARRY_AND_AGGREGATE_PRE_PUBLICATION",
        "sampling_performed": max_episodes is not None,
        "D_TO_classification_performed": False,
        "final_test_access_count": 0,
    }
    _write_manifest(manifest_path, manifest)
    return manifest
