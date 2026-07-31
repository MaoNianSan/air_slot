from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from typing import TypeVar

import psutil
from tqdm import tqdm

T = TypeVar("T")


VALID_PROGRESS_LEVELS = {
    "quiet",
    "normal",
    "detail",
}

_LEVEL_ORDER = {
    "quiet": 0,
    "normal": 1,
    "detail": 2,
}


def normalize_progress_level(value: str | None) -> str:
    level = str(value or "normal").strip().lower()
    if level not in VALID_PROGRESS_LEVELS:
        raise ValueError("progress_level must be one of: quiet, normal, detail")
    return level


def progress_enabled(*, level: str, minimum_level: str = "normal") -> bool:
    return _LEVEL_ORDER[normalize_progress_level(level)] >= _LEVEL_ORDER[normalize_progress_level(minimum_level)]


def progress_iter(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    description: str,
    unit: str = "item",
    level: str = "normal",
    minimum_level: str = "normal",
    leave: bool = True,
) -> Iterator[T]:
    """Iterate with a terminal-safe tqdm bar when the configured level permits it."""
    enabled = progress_enabled(level=level, minimum_level=minimum_level)
    if not enabled or not sys.stderr.isatty():
        return iter(iterable)
    return iter(tqdm(
        iterable,
        total=total,
        desc=description,
        unit=unit,
        file=sys.stderr,
        dynamic_ncols=True,
        disable=False,
        leave=leave,
    ))


def progress_bar(
    *,
    total: int | None = None,
    description: str,
    unit: str = "item",
    level: str = "normal",
    minimum_level: str = "normal",
    leave: bool = True,
) -> tqdm:
    """Create a tqdm bar for callers that need to update postfix values."""
    enabled = progress_enabled(level=level, minimum_level=minimum_level)
    return tqdm(
        total=total,
        desc=description,
        unit=unit,
        file=sys.stderr,
        dynamic_ncols=True,
        disable=not enabled or not sys.stderr.isatty(),
        leave=leave,
    )


def stage_message(message: str, *, level: str) -> None:
    """Write stable stage messages without corrupting an active progress bar."""
    if normalize_progress_level(level) == "quiet":
        return
    tqdm.write(message, file=sys.stderr)


class RunHeartbeat:
    def __init__(self, *, mode: str, config_id: str, level: str, interval_seconds: int = 300, runtime: dict[str, object] | None = None) -> None:
        self.mode = mode
        self.config_id = config_id
        self.level = normalize_progress_level(level)
        self.interval_seconds = int(interval_seconds)
        self.runtime = dict(runtime or {})
        self.stage = "initializing"
        self.last_checkpoint: str | None = None
        self.started = time.monotonic()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="pre-heartbeat", daemon=True)

    def start(self) -> None:
        if self.level != "quiet":
            self._thread.start()

    def update(self, stage: str) -> None:
        self.stage = stage

    def checkpointed(self, path: str) -> None:
        self.last_checkpoint = path

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            payload = {
                "module": "pre",
                "mode": self.mode,
                "stage": self.stage,
                "model_or_config": self.config_id,
                "elapsed": round(time.monotonic() - self.started, 1),
                "last_checkpoint": self.last_checkpoint,
                "memory_mb": round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "requested_n_jobs": self.runtime.get("requested_n_jobs", 1),
                "resolved_n_jobs": self.runtime.get("resolved_n_jobs", 1),
                "outer_workers": self.runtime.get("outer_workers", 1),
                "inner_model_threads": self.runtime.get("inner_model_threads", 1),
                "running_task_ids": [],
                "completed_task_count": 0,
                "pending_task_count": 0,
            }
            tqdm.write("HEARTBEAT " + json.dumps(payload, sort_keys=True), file=sys.stderr)
