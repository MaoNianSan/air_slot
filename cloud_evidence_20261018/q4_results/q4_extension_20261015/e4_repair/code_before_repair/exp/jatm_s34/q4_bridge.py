"""Test-only input bridge for the frozen JATM S34 evaluation functions.

The Development materializer and M1 Development cache remain unchanged. This
adapter loads a previously frozen Q4 cohort and offers the same typed bridge
rows, with true `test` split provenance in every context/manifest.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from data2.scripts.consequence_stability_battery import (
    active_rows,
    build_training_examples,
    year_references,
)
from model.M1.pipeline import M1Pipeline
from model.PRE.contracts.pre_state import EpisodeRecord
from model.PRE.cohort import split_for_date_multiyear
from model.PRE.development import _publish_partition
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.pipeline import ProductionPREPublisher
from model.PRE.streaming.data2 import (
    config_hash,
    load_selected_typed_records,
    load_timezones,
    ontime_paths,
    registry_hash,
    weather_index,
)
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT
from .annual_bridge import _annual_bundle, load_annual_authorities
from .annual_tail import load_annual_tail
from .q4_cohort import Q4_MONTHS, q4_rank


class Q4CacheView:
    """Small inference view for existing consumers that require cache.partition.

    Unlike `M1DevelopmentBaseCache`, it is not persisted and does not relabel
    Q4 examples. Consumers must request `test`; the compatibility split is
    carried independently in `bridge['cache_split']`.
    """

    def __init__(self, examples, normalization, static_normalization):
        self._examples = tuple(examples)
        self.normalization = normalization
        self.static_normalization = static_normalization

    def partition(self, split: str, *, representation: str = "ADAPTIVE_HISTORY"):
        if split != "test":
            raise ValueError(f"Q4_CACHE_SPLIT_INVALID:{split}")
        if representation == "ADAPTIVE_HISTORY":
            return self._examples
        if representation == "CURRENT":
            return tuple(
                replace(example, values=example.values[-1:].clone())
                for example in self._examples
            )
        raise ValueError(f"Q4_CACHE_REPRESENTATION_INVALID:{representation}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_q4_cohort(cohort_dir: Path, *, year: int):
    cohort_dir = Path(cohort_dir).resolve()
    manifest_path = cohort_dir / "Q4_COHORT_MANIFEST.json"
    ids_path = cohort_dir / "Q4_SELECTED_COHORT.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != "JATM_S34_Q4_COHORT_V1"
            or manifest.get("status") != "COHORT_FROZEN"
            or int(manifest.get("year", -1)) != int(year)
            or manifest.get("split") != "test"
            or manifest.get("selected_episode_count") != 4096
            or manifest.get("selected_ids_sha256") != _sha256(ids_path)):
        raise RuntimeError(f"Q4_COHORT_MANIFEST_INVALID:{year}")
    records = []
    with ids_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            episode = EpisodeRecord.model_validate(row["episode"])
            if row.get("episode_id") != episode.episode_id:
                raise RuntimeError("Q4_COHORT_EPISODE_ID_MISMATCH")
            rank = str(row["rank"])
            if rank != q4_rank(episode.episode_id):
                raise RuntimeError("Q4_COHORT_RANK_MISMATCH")
            records.append((rank, episode))
    records.sort(key=lambda item: (item[0], item[1].episode_id))
    if (len(records) != 4096
            or len({episode.episode_id for _, episode in records}) != 4096):
        raise RuntimeError(f"Q4_COHORT_SIZE_OR_DUPLICATE_INVALID:{year}")
    return tuple(records), manifest


def iter_q4_bridges(
    *, year: int, n: int = 4096, chunk_size: int = 64,
    cohort_dir: Path, output_root: Path, node_limit: int | None = None,
    start_chunk: int = 0, device: str = "cpu",
    continuity_contract: str = "LEGACY_A_V1",
) -> Iterator[dict[str, Any]]:
    """Yield bounded annual Q4 bridges backed by the frozen selected IDs."""

    import torch

    year = int(year)
    if int(n) != 4096:
        raise ValueError(f"Q4_BRIDGE_N_FROZEN: {n}")
    if int(chunk_size) <= 0 or int(start_chunk) < 0:
        raise ValueError("Q4_BRIDGE_CHUNK_ARGUMENT_INVALID")
    selected, cohort_manifest = load_frozen_q4_cohort(cohort_dir, year=year)
    selected = selected[:int(n)]
    if node_limit is not None:
        selected = selected[:int(node_limit)]
    episodes = tuple(episode for _, episode in selected)

    data2_root = PROJECT_ROOT / "data2"
    q4_paths = ontime_paths(
        PROJECT_ROOT, months=Q4_MONTHS, allow_final_test=True, year=year
    )
    if len(q4_paths) != 3:
        raise RuntimeError(f"Q4_ON_TIME_PATHS_INCOMPLETE:{year}:{len(q4_paths)}")
    zones = load_timezones(data2_root / "refs" / "us_airport_timezones.csv")
    schedules, outcomes = load_selected_typed_records(
        episodes, q4_paths, zones, dataset_instance_id="data2_2017_2022"
    )

    scientific = load_config_layers(PROJECT_ROOT / "configs").scientific
    replay_lag = int(scientific.parameters["data2_weather_replay_lag_minutes"].value)
    max_age = int(scientific.parameters["weather_max_age_minutes"].value)
    weather, weather_audit = weather_index(
        data2_root, replay_lag,
        start_inclusive=date(year, 9, 1),
        end_exclusive=date(year + 1, 1, 1),
        stamp_year=str(year),
    )
    taxi, turnaround = year_references(year)
    authorities = load_annual_authorities(year, continuity_contract=continuity_contract)
    bundle = _annual_bundle(year)
    tail = load_annual_tail(year)
    history_checkpoint = PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_HISTORY_PRIMARY.pt"
    current_checkpoint = PROJECT_ROOT / "artifacts" / "models" / "m1" / f"YEAR_{year}" / "M1_CURRENT_COMPARATOR.pt"
    history_pipeline = M1Pipeline.load(history_checkpoint)
    current_pipeline = M1Pipeline.load(current_checkpoint)
    if device != "cpu":
        history_pipeline.to_device(device)
        current_pipeline.to_device(device)
    history_pipeline.tail_continuations = dict(tail)
    current_pipeline.tail_continuations = dict(tail)
    normalization = history_pipeline.normalization
    static_normalization = history_pipeline.static_normalization
    publisher = ProductionPREPublisher.from_project()
    config_hash_value = config_hash(PROJECT_ROOT)
    registry_hash_value = registry_hash(PROJECT_ROOT)

    # Data access and PRE materialization occur after Q4_SELECTED_COHORT.jsonl
    # and its manifest have been frozen. The immutable cohort is chunked only
    # for peak-memory control.
    output_root = Path(output_root).resolve()
    first_offset = int(start_chunk) * int(chunk_size)
    for offset in range(first_offset, len(episodes), int(chunk_size)):
        chunk_index = offset // int(chunk_size)
        chunk = episodes[offset:offset + int(chunk_size)]
        if not chunk:
            continue
        items = {
            episode.episode_id: (
                episode,
                schedules[episode.successor_flight_id],
                outcomes[episode.predecessor_flight_id],
                outcomes[episode.successor_flight_id],
            )
            for episode in chunk
        }
        for episode in chunk:
            containment = episode_containment_from_rows(
                episode,
                {episode.predecessor_flight_id: {
                    "service_date": schedules[episode.predecessor_flight_id].service_date.isoformat()
                }, episode.successor_flight_id: {
                    "service_date": schedules[episode.successor_flight_id].service_date.isoformat()
                }},
                split_resolver=split_for_date_multiyear,
            )
            if not containment.allowed or containment.split != "test":
                raise RuntimeError(f"Q4_BRIDGE_CONTAINMENT_VIOLATION:{episode.episode_id}")
        prepared, stage_counts = _publish_partition(
            chunk, items,
            config_hash_value=config_hash_value,
            registry_hash_value=registry_hash_value,
            weather=weather,
            weather_max_age_minutes=max_age,
            publisher=publisher,
            taxi_reference=taxi,
            turnaround_reference=turnaround,
            dataset_instance_id="data2_2017_2022",
        )
        for item in prepared:
            if any(
                split_for_date_multiyear(node.decision_time.date()) != "test"
                for node in item.nodes
            ):
                raise RuntimeError(
                    f"Q4_BRIDGE_NODE_SPLIT_VIOLATION:{item.episode.episode_id}"
                )
        rows, _ = active_rows(prepared, taxi_reference=taxi)
        examples = tuple(build_training_examples(
            rows, normalization, None, static_normalization=static_normalization
        ))
        prepared_by_id = {item.episode.episode_id: item for item in prepared}
        bridge_rows = tuple(
            (example, prepared_by_id[episode.episode_id], prefix)
            for example, (episode, prefix, _labels) in zip(examples, rows)
        )
        cache = Q4CacheView(examples, normalization, static_normalization)
        q4_access_count = len(chunk)
        yield {
            "authorities": replace(authorities, cache=cache,
                                   reference_bundle=bundle, taxi_reference=taxi),
            "bridge": {
                "cache": cache,
                "rows": bridge_rows,
                "mapping": None,
                "taxi_reference": taxi,
                "cache_split": "test",
                "manifest": {
                    "year": year,
                    "n": int(n),
                    "split": "test",
                    "chunk_index": chunk_index,
                    "chunk_offset": offset,
                    "chunk_episode_count": len(chunk),
                    "q4_cohort_manifest_hash": cohort_manifest["selected_ids_sha256"],
                    "final_test_access_count": q4_access_count,
                    "final_test_access_count_unit": "selected_q4_episodes_materialized",
                },
            },
            "tails": tail,
            "year": year,
            "n": int(n),
            "history_checkpoint": history_checkpoint,
            "current_checkpoint": current_checkpoint,
            "history_pipeline": history_pipeline,
            "current_pipeline": current_pipeline,
            "q4_cohort_manifest": cohort_manifest,
            "q4_weather_audit": weather_audit,
            "q4_access_count": q4_access_count,
            "stage_counts": stage_counts,
        }


def materialize_q4_case_cohort(
    *, year: int, cohort_dir: Path, output_root: Path,
    chunk_size: int = 64,
):
    """Materialize the fixed Q4 PRE cohort once for the E4 model grid."""

    prepared = []
    last_manifest = None
    for context in iter_q4_bridges(
        year=year, n=4096, chunk_size=chunk_size,
        cohort_dir=cohort_dir, output_root=output_root,
    ):
        prepared.extend(row[1] for row in context["bridge"]["rows"])
        last_manifest = context["q4_cohort_manifest"]
        del context
    if len(prepared) != 4096:
        raise RuntimeError(f"Q4_PREPARED_COHORT_SIZE_INVALID:{year}:{len(prepared)}")
    return SimpleNamespace(
        development=tuple(prepared),
        audit={
            "split": "test",
            "selected_episode_count": len(prepared),
            "q4_cohort_manifest": last_manifest,
            "final_test_access_count": len(prepared),
            "final_test_access_count_unit": "selected_q4_episodes_materialized",
        },
    )

