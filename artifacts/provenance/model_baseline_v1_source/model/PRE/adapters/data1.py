from pathlib import Path
from model.common.errors import ContractError
from model.common.paths import project_path
from model.PRE.canonical.normalization import (
    canonicalize_flightlist_row,
    canonicalize_airport_row,
    canonicalize_eurostat_payload,
    canonicalize_eurostat_passengers_payload,
    canonicalize_metar_row,
    canonicalize_state_vector_row,
)
from .base import AdapterDescription, SourceValidationReport, SourceValidationRequest
from .readers import iter_csv_rows
from .registry import RawReadRequest, SourceAdapterRegistry


class Data1Adapter:
    _families = (
        "opensky_state_vectors",
        "opensky_flightlist",
        "iem_metar",
        "eurostat",
        "ourairports",
    )

    def describe(self) -> AdapterDescription:
        return AdapterDescription(
            dataset_instance_id="data1_2019", source_families=self._families
        )

    def capabilities(self) -> dict[str, str]:
        return {
            "qnh_mslp": "QNH_NOT_MSLP",
            "schedule": "UNSUPPORTED",
            "aircraft_metadata_2019": "UNSUPPORTED",
            "passenger_reference": "EMPIRICAL_REFERENCE",
        }

    def validate_source(
        self, request: SourceValidationRequest
    ) -> SourceValidationReport:
        supported = request.source_family in self._families
        return SourceValidationReport(
            dataset_instance_id="data1_2019",
            source_family=request.source_family,
            status="DECLARED" if supported else "UNSUPPORTED",
            reason_code=None if supported else "SOURCE_FAMILY_NOT_DECLARED",
        )

    def iter_canonical(
        self, request: RawReadRequest, *, replay_lag_minutes: int | None = None
    ):
        if not isinstance(request, RawReadRequest):
            raise ContractError("RAW_READ_REQUEST_REQUIRED")
        definition = SourceAdapterRegistry.load(
            project_path("registries", "source_adapter_registry.yaml")
        ).get(request.dataset_instance_id, request.source_family)

        def _eurostat_converter(payload):
            if payload.get("extension", {}).get("id") == "AVIA_PAOA":
                return canonicalize_eurostat_passengers_payload(payload)
            return canonicalize_eurostat_payload(payload)

        converters = {
            "iem_metar": lambda row: canonicalize_metar_row(
                row, replay_lag_minutes=replay_lag_minutes
            ),
            "opensky_flightlist": canonicalize_flightlist_row,
            "opensky_state_vectors": lambda row: canonicalize_state_vector_row(
                row, replay_lag_minutes=replay_lag_minutes
            ),
            "ourairports": canonicalize_airport_row,
            "eurostat": lambda row: _eurostat_converter(row["payload"]),
        }
        if request.source_family not in converters:
            raise ContractError("CANONICALIZER_NOT_IMPLEMENTED")
        for raw in iter_csv_rows(request, definition):
            converted = converters[request.source_family](raw.values)
            values = converted if isinstance(converted, tuple) else (converted,)
            for value in values:
                yield value.model_copy(
                    update={
                        "source_path": raw.source_path,
                        "source_fingerprint": raw.source_fingerprint,
                        "source_row_number": raw.row_number,
                    }
                )
