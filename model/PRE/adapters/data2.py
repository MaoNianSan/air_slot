import csv
from pathlib import Path
from model.common.errors import ContractError
from model.common.paths import project_path
from model.PRE.canonical.normalization import (
    canonicalize_aggregate_row,
    canonicalize_airport_row,
    canonicalize_isd_row,
    canonicalize_ontime_row,
    canonicalize_timezone_row,
    _normalize_isd_station_id,
)
from .base import AdapterDescription, SourceValidationReport, SourceValidationRequest
from .readers import iter_csv_rows
from .registry import RawReadRequest, SourceAdapterRegistry


class Data2Adapter:
    _families = (
        "bts_ontime",
        "bts_db1b",
        "bts_t100",
        "timezone_reference",
        "airport_reference",
        "noaa_isd",
    )

    def describe(self) -> AdapterDescription:
        return AdapterDescription(
            dataset_instance_id="data2_2019", source_families=self._families
        )

    def capabilities(self) -> dict[str, str]:
        return {
            "realized_events": "POSTHOC_DIRECT",
            "passenger_reference": "AGGREGATE_PROXY",
            "aircraft_type": "UNVERIFIED",
            "realtime_state": "UNSUPPORTED",
            "weather": "NOAA_ISD_DIRECT",
        }

    def validate_source(
        self, request: SourceValidationRequest
    ) -> SourceValidationReport:
        supported = request.source_family in self._families
        return SourceValidationReport(
            dataset_instance_id="data2_2019",
            source_family=request.source_family,
            status="DECLARED" if supported else "UNSUPPORTED",
            reason_code=None if supported else "SOURCE_FAMILY_NOT_DECLARED",
        )

    def iter_canonical(
        self,
        request: RawReadRequest,
        *,
        timezone_reference: Path | None = None,
        replay_lag_minutes: int | None = None,
    ):
        if not isinstance(request, RawReadRequest):
            raise ContractError("RAW_READ_REQUEST_REQUIRED")
        definition = SourceAdapterRegistry.load(
            project_path("registries", "source_adapter_registry.yaml")
        ).get(request.dataset_instance_id, request.source_family)
        if request.source_family == "bts_ontime":
            reference = (
                timezone_reference
                or request.raw_root / "refs" / "us_airport_timezones.csv"
            )
            with reference.open(encoding="utf-8-sig", newline="") as stream:
                timezones = {
                    row["iata"]: row["timezone"] for row in csv.DictReader(stream)
                }
            converter = lambda row: canonicalize_ontime_row(row, timezones)
        elif request.source_family == "timezone_reference":
            converter = canonicalize_timezone_row
        elif request.source_family == "airport_reference":
            converter = lambda row: canonicalize_airport_row(
                row,
                dataset_instance_id="data2_2019",
                rule_id="D2-AIRPORT-REFERENCE",
                logical_source="airport_reference",
            )
        elif request.source_family in {"bts_db1b", "bts_t100"}:
            converter = lambda row: canonicalize_aggregate_row(
                row,
                dataset_instance_id="data2_2019",
                source_family=request.source_family,
            )
        elif request.source_family == "noaa_isd":
            station_path = request.raw_root / "refs" / "weather_station_map.csv"
            with station_path.open(encoding="utf-8-sig", newline="") as stream:
                station_map = {
                    _normalize_isd_station_id(row["station"]): row["airport"]
                    for row in csv.DictReader(stream)
                }
            converter = lambda row: canonicalize_isd_row(
                row, station_map=station_map, replay_lag_minutes=replay_lag_minutes
            )
        else:
            raise ContractError("CANONICALIZER_NOT_IMPLEMENTED")
        for raw in iter_csv_rows(request, definition):
            converted = converter(raw.values)
            values = converted if isinstance(converted, tuple) else (converted,)
            for value in values:
                yield value.model_copy(
                    update={
                        "source_path": raw.source_path,
                        "source_fingerprint": raw.source_fingerprint,
                        "source_row_number": raw.row_number,
                    }
                )
