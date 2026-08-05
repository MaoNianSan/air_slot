from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


MEMBERSHIP_COLUMNS = [
    "membership_id",
    "chain_episode_id",
    "observation_id",
    "source",
    "flight_id",
    "request_start",
    "request_end",
    "interval_type",
    "split",
    "membership_role",
    "availability_supported",
    "membership_reason",
]
IDENTITY_COLUMNS = {
    "state": ("aircraft_id", "icao24"),
    "weather": ("airport_id", "airport"),
    "flow": ("airport_id", "airport"),
}


def _stable_membership_ids(
    chain_ids: pd.Series,
    observation_ids: pd.Series,
    interval_types: pd.Series,
) -> list[str]:
    payload = (
        chain_ids.astype("string").fillna("")
        + "|"
        + observation_ids.astype("string").fillna("")
        + "|"
        + interval_types.astype("string").fillna("")
    )
    return [
        hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        for value in payload
    ]


def _vectorized_roles(
    source: str,
    event_time: pd.Series,
    request_rows: pd.DataFrame,
) -> np.ndarray:
    if source == "weather":
        return np.full(len(event_time), "WEATHER_CONTEXT", dtype=object)
    if source == "flow":
        return np.full(len(event_time), "AIRPORT_CONTEXT", dtype=object)
    episode_start = pd.to_datetime(
        request_rows.get(
            "episode_start_time", pd.Series(pd.NaT, index=request_rows.index)
        ),
        utc=True,
    )
    predecessor_end = pd.to_datetime(
        request_rows.get(
            "predecessor_lastseen_proxy",
            pd.Series(pd.NaT, index=request_rows.index),
        ),
        utc=True,
    )
    successor_start = pd.to_datetime(
        request_rows.get(
            "successor_firstseen_proxy",
            pd.Series(pd.NaT, index=request_rows.index),
        ),
        utc=True,
    )
    events = pd.to_datetime(event_time, utc=True)
    return np.select(
        [
            episode_start.notna().to_numpy() & events.lt(episode_start).to_numpy(),
            predecessor_end.notna().to_numpy()
            & events.le(predecessor_end).to_numpy(),
            successor_start.notna().to_numpy()
            & events.lt(successor_start).to_numpy(),
        ],
        ["PREDECESSOR_HISTORY", "PREDECESSOR_ACTIVE", "TURNAROUND_CONTEXT"],
        default="SUCCESSOR_CONTEXT",
    )


def interval_join_partition(
    observations: pd.DataFrame,
    requests: pd.DataFrame,
    *,
    source: str,
    observation_date: str,
) -> pd.DataFrame:
    if source not in IDENTITY_COLUMNS:
        raise ValueError(f"MEMBERSHIP_SOURCE_UNSUPPORTED={source}")
    observation_identity, request_identity = IDENTITY_COLUMNS[source]
    required_observation = {
        "observation_id",
        "source",
        "observation_date",
        "event_time",
        "availability_time",
        observation_identity,
    }
    required_request = {
        "chain_episode_id",
        "source",
        "request_start",
        "request_end",
        "interval_type",
        "split",
        request_identity,
    }
    missing_observation = sorted(required_observation - set(observations.columns))
    missing_request = sorted(required_request - set(requests.columns))
    if missing_observation:
        raise ValueError(
            "MEMBERSHIP_OBSERVATION_IDENTITY_COLUMNS_MISSING="
            + ",".join(missing_observation)
        )
    if missing_request:
        raise ValueError(
            "MEMBERSHIP_REQUEST_IDENTITY_COLUMNS_MISSING="
            + ",".join(missing_request)
        )
    if observations.empty or requests.empty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    day_start = pd.Timestamp(observation_date, tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    obs = observations[
        observations["source"].eq(source)
        & observations["observation_date"].astype("string").eq(observation_date)
    ].copy()
    req = requests[
        requests["source"].eq(source)
        & pd.to_datetime(requests["request_start"], utc=True).lt(day_end)
        & pd.to_datetime(requests["request_end"], utc=True).ge(day_start)
    ].copy()
    if obs.empty or req.empty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    obs["event_time"] = pd.to_datetime(obs["event_time"], utc=True, errors="coerce")
    obs["availability_time"] = pd.to_datetime(
        obs["availability_time"], utc=True, errors="coerce"
    )
    req["request_start"] = pd.to_datetime(
        req["request_start"], utc=True, errors="coerce"
    )
    req["request_end"] = pd.to_datetime(
        req["request_end"], utc=True, errors="coerce"
    )
    if obs["event_time"].isna().any():
        raise ValueError("MEMBERSHIP_OBSERVATION_EVENT_TIME_MISSING")
    if req[["request_start", "request_end"]].isna().any(axis=None):
        raise ValueError("MEMBERSHIP_REQUEST_INTERVAL_MISSING")
    request_groups = {
        str(identity): group.sort_values(
            ["request_start", "request_end", "chain_episode_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        for identity, group in req.groupby(
            request_identity, sort=False, dropna=False
        )
        if pd.notna(identity)
    }
    pieces: list[pd.DataFrame] = []
    for identity, obs_group in obs.groupby(
        observation_identity, sort=False, dropna=False
    ):
        if pd.isna(identity):
            continue
        req_group = request_groups.get(str(identity))
        if req_group is None or req_group.empty:
            continue
        obs_group = obs_group.sort_values(
            ["event_time", "observation_id"], kind="mergesort"
        ).reset_index(drop=True)
        event_ns = obs_group["event_time"].astype("int64").to_numpy()
        left = np.searchsorted(
            event_ns,
            req_group["request_start"].astype("int64").to_numpy(),
            side="left",
        )
        right = np.searchsorted(
            event_ns,
            req_group["request_end"].astype("int64").to_numpy(),
            side="right",
        )
        lengths = right - left
        valid = lengths > 0
        if not valid.any():
            continue
        positions = np.flatnonzero(valid)
        obs_positions = np.concatenate(
            [np.arange(left[pos], right[pos], dtype=np.int64) for pos in positions]
        )
        req_positions = np.repeat(positions, lengths[valid])
        selected_obs = obs_group.take(obs_positions).reset_index(drop=True)
        selected_req = req_group.take(req_positions).reset_index(drop=True)
        available = selected_obs["availability_time"].le(selected_req["request_end"])
        piece = pd.DataFrame(
            {
                "chain_episode_id": selected_req["chain_episode_id"].to_numpy(),
                "observation_id": selected_obs["observation_id"].to_numpy(),
                "source": source,
                "flight_id": selected_obs.get(
                    "flight_id", pd.Series(pd.NA, index=selected_obs.index)
                ).to_numpy(),
                "request_start": selected_req["request_start"].to_numpy(),
                "request_end": selected_req["request_end"].to_numpy(),
                "interval_type": selected_req["interval_type"].to_numpy(),
                "split": selected_req["split"].to_numpy(),
                "membership_role": _vectorized_roles(
                    source, selected_obs["event_time"], selected_req
                ),
                "availability_supported": available.to_numpy(dtype=bool),
                "membership_reason": np.where(
                    available.to_numpy(dtype=bool),
                    "EVENT_IN_REQUEST_AND_IDENTITY_MATCH",
                    "EVENT_MATCHED_BUT_AVAILABLE_AFTER_REQUEST_END",
                ),
            }
        )
        piece.insert(
            0,
            "membership_id",
            _stable_membership_ids(
                piece["chain_episode_id"],
                piece["observation_id"],
                piece["interval_type"],
            ),
        )
        pieces.append(piece[MEMBERSHIP_COLUMNS])
    if not pieces:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    return (
        pd.concat(pieces, ignore_index=True)
        .drop_duplicates(
            ["chain_episode_id", "observation_id", "interval_type"], keep="last"
        )
        .sort_values(
            ["chain_episode_id", "source", "observation_id"], kind="mergesort"
        )
        .reset_index(drop=True)
    )


def build_membership(
    observations: pd.DataFrame,
    requests: pd.DataFrame,
) -> pd.DataFrame:
    if observations.empty or requests.empty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    obs = observations.copy()
    if "observation_date" not in obs:
        if "event_time" not in obs:
            raise ValueError("MEMBERSHIP_OBSERVATION_DATE_AND_EVENT_TIME_MISSING")
        obs["observation_date"] = pd.to_datetime(
            obs["event_time"], utc=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    pieces = [
        interval_join_partition(
            group,
            requests,
            source=str(source),
            observation_date=str(observation_date),
        )
        for (source, observation_date), group in obs.groupby(
            ["source", "observation_date"], sort=True, dropna=False
        )
        if pd.notna(source) and pd.notna(observation_date)
    ]
    nonempty = [piece for piece in pieces if not piece.empty]
    if not nonempty:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    return (
        pd.concat(nonempty, ignore_index=True)
        .drop_duplicates(
            ["chain_episode_id", "observation_id", "interval_type"], keep="last"
        )
        .sort_values(
            ["chain_episode_id", "source", "observation_id"], kind="mergesort"
        )
        .reset_index(drop=True)
    )
