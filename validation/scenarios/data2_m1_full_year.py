from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import random

import torch

from model.common.enums import OperationalStage
from model.M1.data import encode_pre_sequence
from model.M1.splits import ALL_SPLITS, split_for_date
from model.PRE.episode.builder import build_data2_episode_records


def gap_stats(gaps: list[float]) -> dict:
    ordered = sorted(gaps)
    count = len(ordered)
    return {"count": count,
            "percentiles": {q: ordered[min(count - 1, int(q * count / 100.0))]
                            for q in (5, 25, 50, 75, 95, 99)},
            "max": ordered[-1]}


def build_episode_reservoirs(flight_rows, by_id, *, sample_counts, seed):
    """Stream a deterministic per-split reservoir without materializing all episodes."""
    by_month = defaultdict(list)
    for row in flight_rows:
        if row.get("service_date"):
            by_month[row["service_date"][:7]].append(row)
    reservoirs = {split: [] for split in ALL_SPLITS}
    pool_sizes = {split: 0 for split in ALL_SPLITS}
    total, gaps = 0, []
    rng = random.Random(seed)
    for month_index in range(1, 13):
        key = f"2019-{month_index:02d}"
        previous = f"2019-{month_index - 1:02d}" if month_index > 1 else None
        chunk = list(by_month.get(key, ()))
        if previous:
            chunk.extend(by_month.get(previous, ()))
        for episode in sorted(build_data2_episode_records(chunk), key=lambda item: item.episode_id):
            service_date = by_id[episode.successor_flight_id]["service_date"]
            if service_date is None or service_date[:7] != key:
                continue
            split = split_for_date(date.fromisoformat(service_date))
            pool_sizes[split] += 1
            total += 1
            gaps.append((by_id[episode.successor_flight_id]["actual_departure_utc"]
                         - by_id[episode.predecessor_flight_id]["actual_arrival_utc"])
                        .total_seconds() / 60)
            reservoir = reservoirs[split]
            count = pool_sizes[split]
            if len(reservoir) < sample_counts[split]:
                reservoir.append(episode)
            else:
                index = rng.randrange(count)
                if index < sample_counts[split]:
                    reservoir[index] = episode
    return reservoirs, pool_sizes, total, gaps


def cohort(reservoirs):
    key = lambda episode: (episode.episode_id, episode.predecessor_flight_id)
    return tuple(sorted(reservoirs[split], key=key)
                 for split in ("train", "calibration", "development", "test"))


def raw_paths(data2_root: Path, ontime_csvs, coupon_csvs, zones_path, station_map_path):
    paths = list(ontime_csvs) + list(coupon_csvs) + [zones_path, station_map_path]
    paths.extend(sorted((data2_root / "raw" / "weather" / "noaa" / "2019").glob("*.csv")))
    return paths


def pick_prefix(item, stage, config_hash, registry_hash, weather_index,
                weather_max_age_minutes, *, states_builder):
    nodes, states = states_builder(item, config_hash, registry_hash, weather_index,
                                   weather_max_age_minutes)
    candidates = [index for index, node in enumerate(nodes) if node.operational_stage is stage]
    if not candidates:
        return None
    index = candidates[-1] if stage is OperationalStage.PRE_IB else candidates[0]
    return item, nodes[index], states[:index + 1]


def stage_inference(episodes, items, normalization, loaded, *, config_hash,
                    registry_hash, weather_index, weather_max_age, states_builder,
                    seed, scenario_count=16):
    selected, used = [], set()
    for stage in OperationalStage:
        for episode in episodes:
            if episode.episode_id in used:
                continue
            match = pick_prefix(items[episode.episode_id], stage, config_hash,
                                registry_hash, weather_index, weather_max_age,
                                states_builder=states_builder)
            if match is not None:
                selected.append(match)
                used.add(match[0][0].episode_id)
                break
    numerical = deterministic = True
    shapes, scenarios, stage_counts = {}, [], Counter()
    for item, node, states in selected:
        episode, schedule, _, successor_outcome = item
        values = encode_pre_sequence(states, normalization).unsqueeze(0)
        lengths = torch.tensor([len(states)])
        distributions = loaded.infer(values, lengths)
        shapes[node.operational_stage.value] = {
            name: list(distribution.shape) for name, distribution in distributions.items()}
        numerical &= all(torch.isfinite(distribution).all().item()
                         and abs(float(distribution.sum()) - 1.0) < 1e-5
                         for distribution in distributions.values())
        observed = {}
        if node.operational_stage in {OperationalStage.POST_IB_PRE_OB,
                                      OperationalStage.POST_OB_PRE_TO,
                                      OperationalStage.COMPLETED}:
            observed["R_IB"] = 0.0
        if node.operational_stage in {OperationalStage.POST_OB_PRE_TO,
                                      OperationalStage.COMPLETED}:
            observed["R_OB"] = max(0.0, (successor_outcome.actual_departure_utc
                - schedule.scheduled_departure_utc).total_seconds() / 60)
        if node.operational_stage is OperationalStage.COMPLETED:
            observed["T_TX"] = float(successor_outcome.taxi_out_minutes)
        created = loaded.sample(states[-1], values, lengths, observed=observed,
                                count=scenario_count, seed=seed)
        repeated = loaded.sample(states[-1], values, lengths, observed=observed,
                                 count=scenario_count, seed=seed)
        deterministic &= created == repeated
        scenarios.extend(created)
        stage_counts[node.operational_stage.value] += len(created)
    return selected, scenarios, dict(stage_counts), numerical, deterministic, shapes
