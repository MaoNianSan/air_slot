from __future__ import annotations

import pandas as pd

from ..contracts import FlightChainStage


def available_events(events: pd.DataFrame, query_time: object) -> pd.DataFrame:
    query = pd.Timestamp(query_time)
    query = query.tz_localize("UTC") if query.tzinfo is None else query.tz_convert("UTC")
    frame = events.copy()
    frame["availability_time"] = pd.to_datetime(
        frame["availability_time"], utc=True, errors="coerce"
    )
    return frame[frame["availability_time"].le(query)].copy()


def flight_chain_stage(
    episode: pd.Series,
    events: pd.DataFrame,
    query_time: object,
) -> FlightChainStage:
    visible = available_events(events, query_time)
    predecessor = str(episode.get("predecessor_flight_id", ""))
    successor = str(episode.get("successor_flight_id", ""))
    names = {
        (str(row.flight_id), str(row.event_name))
        for row in visible.itertuples(index=False)
    }
    if not predecessor or not successor or successor in {"<NA>", "nan", "None"}:
        return FlightChainStage.UNSUPPORTED
    if (successor, "ATOT_PLUS") in names:
        return FlightChainStage.COMPLETED
    if (successor, "AOBT_PLUS") in names:
        return FlightChainStage.SUCCESSOR_TAXI
    if (predecessor, "AIBT_MINUS") in names:
        return FlightChainStage.TURNAROUND
    if (predecessor, "ALDT_MINUS") in names:
        return FlightChainStage.PREDECESSOR_GROUND
    return FlightChainStage.PREDECESSOR_ENROUTE


def state_reset_required(
    previous_episode_id: str | None,
    episode_id: str,
    *,
    terminal_status: str = "",
    chain_changed: bool = False,
    aircraft_swap_terminal: bool = False,
    identity_revised: bool = False,
    model_compatible: bool = True,
    manifest_compatible: bool = True,
) -> bool:
    return any(
        (
            previous_episode_id not in {None, episode_id},
            terminal_status.upper() in {"TERMINATED", "CLOSED", "COMPLETED"},
            chain_changed,
            aircraft_swap_terminal,
            identity_revised,
            not model_compatible,
            not manifest_compatible,
        )
    )
