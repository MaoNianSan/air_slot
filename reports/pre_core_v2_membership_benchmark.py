from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import psutil


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pre"))

from src.core.contracts import stable_id  # noqa: E402
from src.core.membership_interval_join import (  # noqa: E402
    MEMBERSHIP_COLUMNS,
    interval_join_partition,
)


STATE_ROOT = (
    ROOT
    / "pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b"
    / "observations/source=state"
)


def _frame_hash(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values(
        ["chain_episode_id", "source", "observation_id"], kind="mergesort"
    ).reset_index(drop=True)
    digest = hashlib.sha256()
    digest.update("|".join(MEMBERSHIP_COLUMNS).encode("ascii"))
    digest.update(
        pd.util.hash_pandas_object(
            ordered[MEMBERSHIP_COLUMNS], index=False, categorize=True
        ).values.tobytes()
    )
    return digest.hexdigest()


def _role(event_time: pd.Timestamp, request: pd.Series) -> str:
    if pd.notna(request.get("episode_start_time")) and event_time < request["episode_start_time"]:
        return "PREDECESSOR_HISTORY"
    if pd.notna(request.get("predecessor_lastseen_proxy")) and event_time <= request["predecessor_lastseen_proxy"]:
        return "PREDECESSOR_ACTIVE"
    if pd.notna(request.get("successor_firstseen_proxy")) and event_time < request["successor_firstseen_proxy"]:
        return "TURNAROUND_CONTEXT"
    return "SUCCESSOR_CONTEXT"


def _brute_force(observations: pd.DataFrame, requests: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, request in requests.iterrows():
        candidates = observations[
            observations["aircraft_id"].astype("string").eq(str(request["icao24"]))
            & observations["event_time"].between(
                request["request_start"], request["request_end"], inclusive="both"
            )
        ]
        for _, observation in candidates.iterrows():
            available = bool(
                pd.notna(observation["availability_time"])
                and observation["availability_time"] <= request["request_end"]
            )
            rows.append(
                {
                    "membership_id": stable_id(
                        request["chain_episode_id"],
                        observation["observation_id"],
                        request["interval_type"],
                    ),
                    "chain_episode_id": request["chain_episode_id"],
                    "observation_id": observation["observation_id"],
                    "source": "state",
                    "flight_id": observation.get("flight_id", pd.NA),
                    "request_start": request["request_start"],
                    "request_end": request["request_end"],
                    "interval_type": request["interval_type"],
                    "split": request["split"],
                    "membership_role": _role(observation["event_time"], request),
                    "availability_supported": available,
                    "membership_reason": (
                        "EVENT_IN_REQUEST_AND_IDENTITY_MATCH"
                        if available
                        else "EVENT_MATCHED_BUT_AVAILABLE_AFTER_REQUEST_END"
                    ),
                }
            )
    frame = pd.DataFrame(rows, columns=MEMBERSHIP_COLUMNS)
    if frame.empty:
        return frame
    return frame.drop_duplicates(
        ["chain_episode_id", "observation_id", "interval_type"], keep="last"
    ).sort_values(
        ["chain_episode_id", "source", "observation_id"], kind="mergesort"
    ).reset_index(drop=True)


def _load_largest_partition() -> tuple[Path, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    import pyarrow.parquet as pq

    candidates = []
    for path in sorted(STATE_ROOT.rglob("*.parquet")):
        candidates.append((int(pq.ParquetFile(path).metadata.num_rows), path))
    _, path = max(candidates)
    columns = [
        "observation_id", "source", "observation_date", "event_time",
        "availability_time", "aircraft_id", "flight_id", "chain_episode_id",
        "request_start", "request_end", "interval_type", "split",
    ]
    source = pd.read_parquet(path, columns=columns)
    request_columns = [
        "chain_episode_id", "aircraft_id", "request_start", "request_end",
        "interval_type", "split",
    ]
    requests = source[request_columns].drop_duplicates().rename(
        columns={"aircraft_id": "icao24"}
    )
    requests["request_start"] = pd.to_datetime(
        requests["request_start"], utc=True, errors="raise"
    )
    requests["request_end"] = pd.to_datetime(
        requests["request_end"], utc=True, errors="raise"
    )
    requests["source"] = "state"
    for column in (
        "episode_start_time", "predecessor_lastseen_proxy",
        "successor_firstseen_proxy",
    ):
        requests[column] = pd.NaT
    unmatched = requests.iloc[[0]].copy()
    unmatched["chain_episode_id"] = "benchmark-no-matching-request"
    unmatched["icao24"] = "__NO_MATCHING_AIRCRAFT__"
    unmatched["request_start"] = pd.Timestamp("2022-05-16 00:00", tz="UTC")
    unmatched["request_end"] = pd.Timestamp("2022-05-16 23:59:59", tz="UTC")
    requests = pd.concat([requests, unmatched], ignore_index=True)
    observations = source[
        [
            "observation_id", "source", "observation_date", "event_time",
            "availability_time", "aircraft_id", "flight_id",
        ]
    ].copy()
    del source
    overlap_count = 0
    real_requests = requests[requests["chain_episode_id"].ne("benchmark-no-matching-request")]
    for _, group in real_requests.sort_values(
        ["icao24", "request_start"], kind="mergesort"
    ).groupby("icao24", sort=False):
        prior_end = pd.to_datetime(
            group["request_end"].cummax().shift(), utc=True, errors="coerce"
        )
        overlap_count += int(
            (prior_end.notna() & group["request_start"].le(prior_end)).sum()
        )
    metadata = {
        "request_rows_real": len(real_requests),
        "request_rows_total": len(requests),
        "identity_groups": int(observations["aircraft_id"].nunique()),
        "overlapping_request_rows": overlap_count,
        "no_match_request_rows": 1,
    }
    return path, observations, requests, metadata


def _safe_reference_probe(
    observations: pd.DataFrame, requests: pd.DataFrame
) -> dict[str, object]:
    real = requests[requests["chain_episode_id"].ne("benchmark-no-matching-request")]
    identities = (
        observations["aircraft_id"].value_counts().head(8).index.astype(str).tolist()
    )
    subset_requests = real[real["icao24"].astype(str).isin(identities)].head(40).copy()
    selected_identities = set(subset_requests["icao24"].astype(str))
    subset_observations = (
        observations[observations["aircraft_id"].astype(str).isin(selected_identities)]
        .groupby("aircraft_id", sort=False, group_keys=False)
        .head(2_000)
        .copy()
    )
    started = time.perf_counter()
    brute = _brute_force(subset_observations, subset_requests)
    brute_seconds = time.perf_counter() - started
    started = time.perf_counter()
    vectorized = interval_join_partition(
        subset_observations,
        subset_requests,
        source="state",
        observation_date="2022-05-16",
    )
    vectorized_seconds = time.perf_counter() - started
    pd.testing.assert_frame_equal(
        vectorized[MEMBERSHIP_COLUMNS],
        brute[MEMBERSHIP_COLUMNS],
        check_dtype=False,
    )
    return {
        "observation_rows": len(subset_observations),
        "request_rows": len(subset_requests),
        "membership_rows": len(vectorized),
        "brute_force_seconds": brute_seconds,
        "interval_join_seconds": vectorized_seconds,
        "result_hash": _frame_hash(vectorized),
        "status": "PASS",
    }


def main() -> None:
    path, observations, requests, metadata = _load_largest_partition()
    reference = _safe_reference_probe(observations, requests)
    process = psutil.Process()
    baseline_rss = process.memory_info().rss
    peak_rss = [baseline_rss]
    stop = threading.Event()

    def sample_memory() -> None:
        while not stop.wait(0.02):
            peak_rss[0] = max(peak_rss[0], process.memory_info().rss)

    monitor = threading.Thread(target=sample_memory, daemon=True)
    monitor.start()
    started = time.perf_counter()
    membership = interval_join_partition(
        observations,
        requests,
        source="state",
        observation_date="2022-05-16",
    )
    elapsed = time.perf_counter() - started
    peak_rss[0] = max(peak_rss[0], process.memory_info().rss)
    stop.set()
    monitor.join()
    result_hash = _frame_hash(membership)
    projections = {
        "fast_state_membership_seconds": elapsed * 5,
        "middle_state_membership_seconds": elapsed * 72,
        "full_state_membership_seconds": elapsed * 181,
    }
    output = {
        "status": "PASS",
        "source_partition": str(path.resolve()),
        "observation_date": "2022-05-16",
        "observation_rows": len(observations),
        **metadata,
        "membership_rows": len(membership),
        "elapsed_seconds": elapsed,
        "baseline_rss_mb": baseline_rss / 1024**2,
        "peak_rss_mb": peak_rss[0] / 1024**2,
        "peak_incremental_memory_mb": (peak_rss[0] - baseline_rss) / 1024**2,
        "observation_rows_per_second": len(observations) / elapsed,
        "membership_rows_per_second": len(membership) / elapsed,
        "result_hash": result_hash,
        "safe_brute_force_reference": reference,
        "projections": projections,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
