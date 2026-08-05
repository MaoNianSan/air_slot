from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from .partition_builder import build_partition


Task = tuple[str, Path, Path, str, str, pd.DataFrame]


def worker_count(cfg: dict[str, Any], paths: list[Path]) -> int:
    settings = cfg.get("core_membership", {})
    if settings.get("partition_unit") != "source_date":
        raise ValueError("MEMBERSHIP_PARTITION_UNIT_MUST_BE_SOURCE_DATE")
    if bool(settings.get("nested_parallelism", False)):
        raise ValueError("MEMBERSHIP_NESTED_PARALLELISM_FORBIDDEN")
    requested = max(1, int(settings.get("workers", 4)))
    maximum = max(1, min(6, int(settings.get("max_workers", 6))))
    workers = min(requested, maximum, max(1, len(paths)))
    largest = max(
        (path.stat().st_size for path in paths if path.exists()), default=0
    )
    if largest >= int(settings["single_worker_partition_bytes"]):
        return 1
    if largest >= int(settings["reduced_worker_partition_bytes"]):
        return min(workers, 2)
    return workers


def execute(tasks: list[Task], workers: int) -> list[tuple[str, dict[str, Any]]]:
    if workers == 1:
        return [
            (
                key,
                build_partition(
                    str(observation_path),
                    str(path),
                    source,
                    observation_date,
                    subset,
                ),
            )
            for key, observation_path, path, source, observation_date, subset in tasks
        ]
    results: list[tuple[str, dict[str, Any]]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                build_partition,
                str(observation_path),
                str(path),
                source,
                observation_date,
                subset,
            ): key
            for key, observation_path, path, source, observation_date, subset in tasks
        }
        for future in as_completed(futures):
            results.append((futures[future], future.result()))
    return results
