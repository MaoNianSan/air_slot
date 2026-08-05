from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import psutil


PRE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRE_ROOT))

from src.core.contracts import stable_id  # noqa: E402
from src.core.membership_interval_join import (  # noqa: E402
    MEMBERSHIP_COLUMNS,
    interval_join_partition,
)


OBSERVATION_COLUMNS = [
    "observation_id",
    "source",
    "observation_date",
    "event_time",
    "availability_time",
    "aircraft_id",
    "flight_id",
]
EMBEDDED_REQUEST_COLUMNS = [
    "chain_episode_id",
    "aircraft_id",
    "request_start",
    "request_end",
    "interval_type",
    "split",
]
OPTIONAL_REQUEST_COLUMNS = [
    "episode_start_time",
    "predecessor_lastseen_proxy",
    "successor_firstseen_proxy",
]


class BenchmarkInputError(ValueError):
    pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the read-only PRE Core V2 state Membership interval-join "
            "benchmark on an explicitly selected local Parquet partition."
        )
    )
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument(
        "--state-root",
        type=Path,
        help=(
            "Local directory containing state observation Parquet partitions; "
            "the partition with the largest metadata row count is selected."
        ),
    )
    location.add_argument(
        "--partition",
        type=Path,
        help="Exact local state observation Parquet file to benchmark.",
    )
    parser.add_argument(
        "--requests",
        type=Path,
        help=(
            "Optional read-only Parquet file or dataset of observation requests. "
            "Without it, request columns must be embedded in the selected partition."
        ),
    )
    parser.add_argument(
        "--reference-identities",
        type=int,
        default=8,
        help="Maximum identities used by the brute-force correctness probe (default: 8).",
    )
    parser.add_argument(
        "--reference-rows-per-identity",
        type=int,
        default=2000,
        help="Maximum observation rows per reference identity (default: 2000).",
    )
    parser.add_argument(
        "--reference-requests",
        type=int,
        default=40,
        help="Maximum requests used by the brute-force correctness probe (default: 40).",
    )
    parser.add_argument(
        "--skip-unmatched-probe",
        action="store_true",
        help="Do not append the synthetic no-matching-aircraft request.",
    )
    return parser.parse_args()


def _parquet_schema(path: Path) -> tuple[set[str], int]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    return set(parquet.schema_arrow.names), int(parquet.metadata.num_rows)


def _select_partition(state_root: Path | None, partition: Path | None) -> Path:
    if partition is not None:
        candidate = partition.expanduser()
        if not candidate.is_file():
            raise BenchmarkInputError(f"BENCHMARK_PARTITION_NOT_FOUND={candidate}")
        if candidate.suffix.lower() != ".parquet":
            raise BenchmarkInputError(f"BENCHMARK_PARTITION_NOT_PARQUET={candidate}")
        return candidate

    assert state_root is not None
    root = state_root.expanduser()
    if not root.is_dir():
        raise BenchmarkInputError(f"BENCHMARK_STATE_ROOT_NOT_FOUND={root}")
    candidates: list[tuple[int, Path]] = []
    for path in sorted(root.rglob("*.parquet")):
        _, row_count = _parquet_schema(path)
        candidates.append((row_count, path))
    if not candidates:
        raise BenchmarkInputError(f"BENCHMARK_STATE_ROOT_HAS_NO_PARQUET={root}")
    return max(candidates, key=lambda item: (item[0], str(item[1])))[1]


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


def _membership_role(event_time: pd.Timestamp, request: pd.Series) -> str:
    if (
        pd.notna(request.get("episode_start_time"))
        and event_time < request["episode_start_time"]
    ):
        return "PREDECESSOR_HISTORY"
    if (
        pd.notna(request.get("predecessor_lastseen_proxy"))
        and event_time <= request["predecessor_lastseen_proxy"]
    ):
        return "PREDECESSOR_ACTIVE"
    if (
        pd.notna(request.get("successor_firstseen_proxy"))
        and event_time < request["successor_firstseen_proxy"]
    ):
        return "TURNAROUND_CONTEXT"
    return "SUCCESSOR_CONTEXT"


def _brute_force(observations: pd.DataFrame, requests: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
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
                    "membership_role": _membership_role(
                        observation["event_time"], request
                    ),
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


def _load_requests(
    source_frame: pd.DataFrame,
    source_columns: set[str],
    requests_path: Path | None,
) -> pd.DataFrame:
    if requests_path is None:
        missing = sorted(set(EMBEDDED_REQUEST_COLUMNS) - source_columns)
        if missing:
            raise BenchmarkInputError(
                "BENCHMARK_REQUEST_COLUMNS_MISSING="
                + ",".join(missing)
                + "; provide --requests with a compatible local Parquet dataset"
            )
        selected = EMBEDDED_REQUEST_COLUMNS + [
            column for column in OPTIONAL_REQUEST_COLUMNS if column in source_columns
        ]
        requests = source_frame[selected].drop_duplicates().rename(
            columns={"aircraft_id": "icao24"}
        )
    else:
        path = requests_path.expanduser()
        if not path.exists():
            raise BenchmarkInputError(f"BENCHMARK_REQUESTS_NOT_FOUND={path}")
        requests = pd.read_parquet(path)
        if "icao24" not in requests and "aircraft_id" in requests:
            requests = requests.rename(columns={"aircraft_id": "icao24"})

    required = {
        "chain_episode_id",
        "icao24",
        "request_start",
        "request_end",
        "interval_type",
        "split",
    }
    missing = sorted(required - set(requests.columns))
    if missing:
        raise BenchmarkInputError(
            "BENCHMARK_REQUEST_DATASET_COLUMNS_MISSING=" + ",".join(missing)
        )
    requests = requests.copy()
    requests["source"] = "state"
    requests["request_start"] = pd.to_datetime(
        requests["request_start"], utc=True, errors="raise"
    )
    requests["request_end"] = pd.to_datetime(
        requests["request_end"], utc=True, errors="raise"
    )
    for column in OPTIONAL_REQUEST_COLUMNS:
        if column not in requests:
            requests[column] = pd.NaT
        else:
            requests[column] = pd.to_datetime(requests[column], utc=True, errors="coerce")
    if requests.empty:
        raise BenchmarkInputError("BENCHMARK_REQUEST_DATASET_EMPTY")
    return requests


def _load_partition(
    path: Path,
    requests_path: Path | None,
    include_unmatched_probe: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, str, dict[str, int]]:
    source_columns, _ = _parquet_schema(path)
    required_observation = set(OBSERVATION_COLUMNS) - {"flight_id"}
    missing = sorted(required_observation - source_columns)
    if missing:
        raise BenchmarkInputError(
            "BENCHMARK_OBSERVATION_COLUMNS_MISSING=" + ",".join(missing)
        )
    read_columns = list(required_observation)
    if "flight_id" in source_columns:
        read_columns.append("flight_id")
    if requests_path is None:
        read_columns.extend(
            column
            for column in EMBEDDED_REQUEST_COLUMNS + OPTIONAL_REQUEST_COLUMNS
            if column in source_columns and column not in read_columns
        )
    source_frame = pd.read_parquet(path, columns=read_columns)
    if source_frame.empty:
        raise BenchmarkInputError(f"BENCHMARK_PARTITION_EMPTY={path}")
    if "flight_id" not in source_frame:
        source_frame["flight_id"] = pd.NA

    normalized_dates = pd.to_datetime(
        source_frame["observation_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    dates = sorted(normalized_dates.dropna().unique().tolist())
    if len(dates) != 1:
        raise BenchmarkInputError(
            "BENCHMARK_PARTITION_DATE_COUNT=" + str(len(dates))
        )
    observation_date = str(dates[0])
    source_frame["observation_date"] = normalized_dates
    if not source_frame["source"].astype("string").eq("state").all():
        raise BenchmarkInputError("BENCHMARK_PARTITION_SOURCE_MUST_BE_STATE")

    requests = _load_requests(source_frame, source_columns, requests_path)
    real_request_count = len(requests)
    if include_unmatched_probe:
        unmatched = requests.iloc[[0]].copy()
        unmatched["chain_episode_id"] = "benchmark-no-matching-request"
        unmatched["icao24"] = "__NO_MATCHING_AIRCRAFT__"
        day_start = pd.Timestamp(observation_date, tz="UTC")
        unmatched["request_start"] = day_start
        unmatched["request_end"] = day_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        requests = pd.concat([requests, unmatched], ignore_index=True)

    observations = source_frame[OBSERVATION_COLUMNS].copy()
    observations["event_time"] = pd.to_datetime(
        observations["event_time"], utc=True, errors="raise"
    )
    observations["availability_time"] = pd.to_datetime(
        observations["availability_time"], utc=True, errors="coerce"
    )
    real_requests = requests[
        requests["chain_episode_id"].ne("benchmark-no-matching-request")
    ]
    overlap_count = 0
    for _, group in real_requests.sort_values(
        ["icao24", "request_start"], kind="mergesort"
    ).groupby("icao24", sort=False):
        prior_end = group["request_end"].cummax().shift()
        overlap_count += int(
            (prior_end.notna() & group["request_start"].le(prior_end)).sum()
        )
    metadata = {
        "request_rows_real": real_request_count,
        "request_rows_total": len(requests),
        "identity_groups": int(observations["aircraft_id"].nunique()),
        "overlapping_request_rows": overlap_count,
        "no_match_request_rows": int(include_unmatched_probe),
    }
    return observations, requests, observation_date, metadata


def _safe_reference_probe(
    observations: pd.DataFrame,
    requests: pd.DataFrame,
    observation_date: str,
    *,
    max_identities: int,
    rows_per_identity: int,
    max_requests: int,
) -> dict[str, object]:
    real = requests[
        requests["chain_episode_id"].ne("benchmark-no-matching-request")
    ]
    request_identities = set(real["icao24"].dropna().astype(str))
    identities = [
        str(identity)
        for identity in observations["aircraft_id"].value_counts().index
        if str(identity) in request_identities
    ][:max_identities]
    subset_requests = real[
        real["icao24"].astype(str).isin(identities)
    ].head(max_requests).copy()
    subset_observations = (
        observations[observations["aircraft_id"].astype(str).isin(identities)]
        .groupby("aircraft_id", sort=False, group_keys=False)
        .head(rows_per_identity)
        .copy()
    )
    if subset_observations.empty or subset_requests.empty:
        raise BenchmarkInputError("BENCHMARK_REFERENCE_SUBSET_EMPTY")

    started = time.perf_counter()
    brute = _brute_force(subset_observations, subset_requests)
    brute_seconds = time.perf_counter() - started
    started = time.perf_counter()
    vectorized = interval_join_partition(
        subset_observations,
        subset_requests,
        source="state",
        observation_date=observation_date,
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


def _run(args: argparse.Namespace) -> dict[str, object]:
    if min(
        args.reference_identities,
        args.reference_rows_per_identity,
        args.reference_requests,
    ) <= 0:
        raise BenchmarkInputError("BENCHMARK_REFERENCE_LIMITS_MUST_BE_POSITIVE")
    path = _select_partition(args.state_root, args.partition)
    observations, requests, observation_date, metadata = _load_partition(
        path,
        args.requests,
        include_unmatched_probe=not args.skip_unmatched_probe,
    )
    reference = _safe_reference_probe(
        observations,
        requests,
        observation_date,
        max_identities=args.reference_identities,
        rows_per_identity=args.reference_rows_per_identity,
        max_requests=args.reference_requests,
    )

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
        observation_date=observation_date,
    )
    elapsed = time.perf_counter() - started
    peak_rss[0] = max(peak_rss[0], process.memory_info().rss)
    stop.set()
    monitor.join()

    return {
        "status": "PASS",
        "source_partition": str(path.resolve()),
        "observation_date": observation_date,
        "observation_rows": len(observations),
        **metadata,
        "membership_rows": len(membership),
        "elapsed_seconds": elapsed,
        "baseline_rss_mb": baseline_rss / 1024**2,
        "peak_rss_mb": peak_rss[0] / 1024**2,
        "peak_incremental_memory_mb": (peak_rss[0] - baseline_rss) / 1024**2,
        "observation_rows_per_second": len(observations) / elapsed,
        "membership_rows_per_second": len(membership) / elapsed,
        "result_hash": _frame_hash(membership),
        "safe_brute_force_reference": reference,
    }


def main() -> None:
    args = _parse_args()
    try:
        result = _run(args)
    except (BenchmarkInputError, ImportError, OSError, ValueError) as exc:
        raise SystemExit(f"BENCHMARK_INPUT_ERROR={exc}") from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
