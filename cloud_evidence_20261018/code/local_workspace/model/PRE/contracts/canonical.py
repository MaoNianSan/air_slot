from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from model.common.enums import AvailabilityBasis
from model.common.value_objects import FrozenModel


class CanonicalSourceRecord(FrozenModel):
    canonical_record_id: str = Field(min_length=1)
    dataset_instance_id: str = Field(min_length=1)
    event_time: datetime | None = None
    availability_time: datetime | None = None
    availability_basis: AvailabilityBasis
    provenance_rule_id: str = Field(min_length=1)
    quality_flags: tuple[str, ...] = ()
    canonical_object_type: str

    @model_validator(mode="after")
    def canonical_time(self):
        for value in (self.event_time, self.availability_time):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("canonical timestamps require timezone")
        if self.availability_basis in {
            AvailabilityBasis.OBSERVED_AVAILABILITY,
            AvailabilityBasis.REPLAY_EVENT_TIME,
        } and self.availability_time is None:
            raise ValueError("admissible basis requires availability_time")
        return self


class FlightRecord(CanonicalSourceRecord):
    canonical_object_type: Literal["FlightRecord"] = "FlightRecord"
    flight_id: str
    source_flight_id: str | None = None
    aircraft_id: str | None = None
    aircraft_id_namespace: str | None = None
    origin_airport_id: str | None = None
    destination_airport_id: str | None = None


class OperationalEventRecord(CanonicalSourceRecord):
    canonical_object_type: Literal["OperationalEventRecord"] = "OperationalEventRecord"
    event_type: str
    event_time_lower: datetime | None = None
    event_time_upper: datetime | None = None
    reconstruction_rule_id: str | None = None


class TrajectoryObservation(CanonicalSourceRecord):
    canonical_object_type: Literal["TrajectoryObservation"] = "TrajectoryObservation"
    aircraft_id: str
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    velocity_mps: float | None = None
    on_ground: bool | None = None


class WeatherObservation(CanonicalSourceRecord):
    canonical_object_type: Literal["WeatherObservation"] = "WeatherObservation"
    airport_id: str | None = None
    temperature_c: float | None = None
    wind_speed_mps: float | None = None
    qnh_hpa: float | None = None
    mslp_hpa: None = None
    visibility_m: float | None = None


class AggregateReference(CanonicalSourceRecord):
    canonical_object_type: Literal["AggregateReference"] = "AggregateReference"
    reference_name: str
    grain: str
    join_key: dict[str, str]
    reference_period: str
    value: Any
    unit: str


class AirportReference(CanonicalSourceRecord):
    canonical_object_type: Literal["AirportReference"] = "AirportReference"
    airport_id: str
    airport_id_namespace: str
    icao_code: str | None = None
    iata_code: str | None = None
