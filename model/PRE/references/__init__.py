"""Train-frozen passenger consequence reference builders."""

from .passenger_load_reference import (
    ExpectedPassengersReference,
    ExpectedPassengersReferenceCell,
    build_expected_passengers_reference,
    expected_passengers_reference_from_payload,
)
from .connection_share_reference import (
    ConnectionShareReference,
    ConnectionShareReferenceCell,
    ExpectedConnectingPassengerReference,
    derive_expected_connecting_passengers,
    build_connection_share_reference,
    connection_share_reference_from_payload,
)

__all__ = [
    "ExpectedPassengersReference",
    "ExpectedPassengersReferenceCell",
    "build_expected_passengers_reference",
    "expected_passengers_reference_from_payload",
    "ConnectionShareReference",
    "ConnectionShareReferenceCell",
    "ExpectedConnectingPassengerReference",
    "derive_expected_connecting_passengers",
    "build_connection_share_reference",
    "connection_share_reference_from_payload",
]
