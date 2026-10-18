from datetime import datetime, timezone, timedelta
import pytest
from model.common.errors import ContractError
from model.PRE.episode.builder import build_episode_chain


UTC = timezone.utc


def flight(fid, aircraft, origin, dest, start, end):
    return {"flight_id":fid, "aircraft_id":aircraft, "aircraft_id_namespace":"REGISTRATION",
            "origin_airport_id":origin, "destination_airport_id":dest,
            "event_start_time":start, "event_end_time":end, "dataset_instance_id":"data2_2019"}


def test_episode_builder_requires_identity_time_and_airport_continuity():
    t = datetime(2019, 1, 1, tzinfo=UTC)
    p = flight("p", "N1", "A", "B", t, t + timedelta(hours=1))
    s = flight("s", "N1", "B", "C", t + timedelta(hours=2), t + timedelta(hours=3))
    episode = build_episode_chain(p, s)
    assert episode.predecessor_flight_id == "p" and episode.connection_airport_id == "B"
    with pytest.raises(ContractError): build_episode_chain(p, {**s, "aircraft_id":"N2"})
    with pytest.raises(ContractError): build_episode_chain(p, {**s, "origin_airport_id":"X"})
