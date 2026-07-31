from __future__ import annotations

from dataclasses import dataclass
import os
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator, TypeVar

from tqdm import tqdm

T = TypeVar("T")


@dataclass
class Progress:
    level: str = "normal"

    def __post_init__(self) -> None:
        if self.level not in {"quiet", "normal", "detail"}:
            raise ValueError(f"Invalid progress level: {self.level}")
        self._stage = "initializing"
        self._model: str | None = None
        self._last_checkpoint: str | None = None
        self._rows_processed = 0
        self._started = time.monotonic()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._runtime: dict[str, object] = {}

    def start_heartbeat(self, *, module: str, mode: str, interval_seconds: int = 300, runtime: dict[str, object] | None = None) -> None:
        if self.level == "quiet" or self._heartbeat_thread is not None:
            return

        self._runtime = dict(runtime or {})

        def emit() -> None:
            while not self._heartbeat_stop.wait(interval_seconds):
                memory_mb = None
                try:
                    import psutil

                    memory_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
                except (ImportError, OSError):
                    pass
                print(
                    "heartbeat "
                    f"module={module} mode={mode} stage={self._stage} "
                    f"model={self._model} "
                    f"elapsed={int(time.monotonic() - self._started)}s "
                    f"last_checkpoint={self._last_checkpoint} "
                    f"rows_processed={self._rows_processed} "
                    f"memory_mb={memory_mb} "
                    f"requested_n_jobs={self._runtime.get('requested_n_jobs', 1)} "
                    f"resolved_n_jobs={self._runtime.get('resolved_n_jobs', 1)} "
                    f"outer_workers={self._runtime.get('outer_workers', 1)} "
                    f"inner_model_threads={self._runtime.get('inner_model_threads', 1)} "
                    f"timestamp={datetime.now(timezone.utc).isoformat()}",
                    flush=True,
                )

        self._heartbeat_thread = threading.Thread(target=emit, name=f"{module}-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1)

    def stage(self, index: int, total: int, label: str) -> None:
        self._stage = f"{index}/{total}:{label}"
        self._model = next((name for name in ("M1", "M2", "M3", "M4") if name in label), None)
        if self.level != "quiet":
            print(f"[{index}/{total}] {label}", flush=True)

    def checkpoint(self, path: str | None, *, rows_processed: int) -> None:
        self._last_checkpoint = path
        self._rows_processed = int(rows_processed)

    def note(self, message: str) -> None:
        if self.level == "detail":
            print(message, flush=True)

    def summary(self, message: str) -> None:
        if self.level != "quiet":
            print(message, flush=True)

    def iter(self, items: Iterable[T], *, desc: str, total: int | None = None) -> Iterator[T]:
        if self.level == "quiet":
            yield from items
        else:
            yield from tqdm(items, desc=desc, total=total, dynamic_ncols=True)
