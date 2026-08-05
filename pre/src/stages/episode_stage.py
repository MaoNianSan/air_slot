from __future__ import annotations

from ..episode import build_episodes, prepare_legs
from ..input import (
    load_aircraft,
    load_airports,
    load_eurostat,
    load_flightlist,
    load_metar,
)
from ..predecessor_matcher import build_predecessor_features
from ..reference import (
    fit_airport_reference,
    fit_movement_reference,
    fit_passenger_reference,
    fit_turnaround_reference,
    fit_weather_climatology,
)
from .context import PreBuildContext


def run_episode_stage(ctx: PreBuildContext) -> None:
    ctx.require("complete_dates")
    cfg = ctx.cfg
    started = ctx.stage("[2.2] Build episodes and references")
    flightlist = load_flightlist(cfg, ctx.complete_dates)
    aircraft = load_aircraft(cfg)
    airports = load_airports(cfg)
    metar = load_metar(cfg)
    passengers = load_eurostat(cfg, "eurostat_passengers")
    commercial_flights = load_eurostat(cfg, "eurostat_flights")
    airport_reference = fit_airport_reference(airports, commercial_flights, cfg)
    legs = prepare_legs(
        flightlist,
        aircraft,
        airport_reference.table,
        ctx.complete_dates,
        cfg,
    )
    movement_reference = fit_movement_reference(legs, cfg)
    episodes, clipping_bounds = build_episodes(legs, movement_reference, cfg)
    turnaround_reference = fit_turnaround_reference(legs, cfg)
    predecessor_features = build_predecessor_features(
        legs, movement_reference, turnaround_reference, cfg
    )
    episodes = episodes.merge(
        predecessor_features,
        on="episode_id",
        how="left",
        validate="one_to_one",
    )
    passenger_reference = fit_passenger_reference(
        passengers, commercial_flights, legs, cfg
    )
    weather_climatology = fit_weather_climatology(metar, cfg)
    ctx.flightlist = flightlist
    ctx.aircraft = aircraft
    ctx.airports = airports
    ctx.metar = metar
    ctx.passengers = passengers
    ctx.commercial_flights = commercial_flights
    ctx.airport_reference = airport_reference
    ctx.legs = legs
    ctx.movement_reference = movement_reference
    ctx.episodes = episodes
    ctx.clipping_bounds = clipping_bounds
    ctx.turnaround_reference = turnaround_reference
    ctx.predecessor_features = predecessor_features
    ctx.passenger_reference = passenger_reference
    ctx.weather_climatology = weather_climatology
    ctx.finish(
        "2.2_build_episodes_and_references",
        started,
        input_rows=len(flightlist),
        output_rows=len(episodes),
    )
