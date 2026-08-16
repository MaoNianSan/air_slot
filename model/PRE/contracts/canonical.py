from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from model.common.enums import AvailabilityBasis, DecisionTimeRole
from model.common.value_objects import FrozenModel, ProvenanceRef


class CanonicalSourceRecord(FrozenModel):
    canonical_record_id: str = Field(min_length=1)
    dataset_instance_id: str = Field(min_length=1)
    event_time: datetime | None = None
    availability_time: datetime | None = None
    availability_basis: AvailabilityBasis
    decision_time_role: DecisionTimeRole
    provenance_rule_id: str = Field(min_length=1)
    provenance: ProvenanceRef
    source_path: str | None = None
    source_fingerprint: str | None = None
    source_row_number: int | None = Field(default=None, ge=1)
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
        if self.provenance.dataset_instance_id != self.dataset_instance_id:
            raise ValueError("provenance dataset mismatch")
        if self.provenance.rule_id != self.provenance_rule_id:
            raise ValueError("provenance rule mismatch")
        return self


class FlightRecord(CanonicalSourceRecord):
    canonical_object_type: Literal["FlightRecord"] = "FlightRecord"
    flight_id: str
    service_date: date | None = None
    source_flight_id: str | None = None
    aircraft_id: str | None = None
    aircraft_id_namespace: str | None = None
    origin_airport_id: str | None = None
    destination_airport_id: str | None = None
    event_start_time: datetime
    event_end_time: datetime
    first_seen_utc: datetime | None = None
    last_seen_utc: datetime | None = None
    scheduled_departure_utc: datetime | None = None
    scheduled_arrival_utc: datetime | None = None
    schedule_semantics: str | None = None
    offline_membership_only: bool = True

    @model_validator(mode="after")
    def valid_interval(self):
        if self.event_start_time >= self.event_end_time:
            raise ValueError("flight interval must be positive")
        return self


class OperationalEventRecord(CanonicalSourceRecord):
    canonical_object_type: Literal["OperationalEventRecord"] = "OperationalEventRecord"
    event_type: str
    event_time_lower: datetime | None = None
    event_time_upper: datetime | None = None
    reconstruction_rule_id: str | None = None
    flight_id: str | None = None
    aircraft_id: str | None = None
    actual_departure_utc: datetime | None = None
    wheels_off_utc: datetime | None = None
    wheels_on_utc: datetime | None = None
    actual_arrival_utc: datetime | None = None
    taxi_out_minutes: float | None = None
    taxi_in_minutes: float | None = None
    cancelled: bool | None = None
    diverted: bool | None = None


class TrajectoryObservation(CanonicalSourceRecord):
    canonical_object_type: Literal["TrajectoryObservation"] = "TrajectoryObservation"
    aircraft_id: str
    aircraft_id_namespace: str = "ICAO24"
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    velocity_mps: float | None = None
    on_ground: bool | None = None
    baro_altitude_m: float | None = None
    geo_altitude_m: float | None = None
    heading_deg: float | None = None
    vertical_rate_mps: float | None = None
    position_time: datetime | None = None
    contact_time: datetime | None = None


class WeatherObservation(CanonicalSourceRecord):
    canonical_object_type: Literal["WeatherObservation"] = "WeatherObservation"
    airport_id: str | None = None
    temperature_c: float | None = None
    dewpoint_c: float | None = None
    wind_direction_deg: float | None = None
    wind_speed_mps: float | None = None
    wind_gust_mps: float | None = None
    qnh_hpa: float | None = None
    mslp_hpa: None = None
    visibility_m: float | None = None
    cloud_cover_codes: tuple[str, ...] = ()
    cloud_base_m: tuple[float | None, ...] = ()
    ceiling_base_m: float | None = None
    present_weather_codes: str | None = None


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
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    elevation_m: float | None = None
    airport_type: str | None = None
    timezone: str | None = None
