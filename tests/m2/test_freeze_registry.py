import csv
from pathlib import Path

import pytest

from model.common.cu_normalization import CUNormalizationStatus
from model.M2.cu.registry import (
    FORMAL_SCOPE,
    FrozenData2ValuationRegistry,
    M2Data2FormalCuRegistry,
    REGISTRY_ID,
    build_m2_data2_formal_registry,
    compute_train_scales,
    load_m2_registry,
    write_m2_registry,
)
from model.M2.mapper import M2Mapper
from model.PRE.reference.data2_m2_train_fit import build_data2_m2_train_preparation
from model.common.errors import ContractError
from model.common.estimand import FormalEstimandStatus
from tests.fixtures.p0_p1_contracts import scope_fixture
from tests.m2.test_mapping import context, scenario, supported


def _scale_payload():
    return {
        name: {
            "median": float(index + 1) * 10.0,
            "positive_n": 100 + index,
            "population_rows": 1000 + index,
            "unit": "minutes",
            "definition": f"definition-{name}",
            "active_quantity_definition": f"definition-{name}",
            "fit_period": "2019-H1",
            "path": "artifacts/x/scales.json",
            "artifact_hash": "sha256:" + "9" * 64,
        }
        for index, name in enumerate(FORMAL_SCOPE)
    }


def _reference_payload():
    return {
        name: {
            "path": f"artifacts/x/{name}.json",
            "artifact_hash": f"sha256:{index:064d}",
            "reference_id": f"sha256:{index + 100:064d}",
            "manifest_freeze_id": f"sha256:{index + 200:064d}",
        }
        for index, name in enumerate(("turnaround", "taxi", "downstream_exposure", "expected_pax", "connection_share"))
    }


def _registry(**overrides):
    values = {
        "train_scale_artifact": _scale_payload(),
        "reference_artifacts": _reference_payload(),
        "semantic_channels": {
            "P_service": {
                "consequence_semantics": "passenger service / care burden",
                "baseline_empirical_realization": "expected passengers x I[D_TO >= 180]",
            },
            "R_operating": {
                "consequence_semantics": "operating / recovery-resource burden",
                "baseline_empirical_realization": "D_TX",
            },
        },
        "component_weights": {name: 1.0 for name in FORMAL_SCOPE},
        "fit_year": 2019,
        "fit_months": (1, 2, 3, 4, 5, 6),
        "db1b_quarters": (1, 2),
        "passenger_manifest": "artifacts/x/PASSENGER_REFERENCE_MANIFEST_V2.json",
    }
    values.update(overrides)
    return M2Data2FormalCuRegistry(**values)


def test_m2_registry_contract_rejects_scope_drift():
    with pytest.raises(ContractError, match="M2_V4_FORMAL_SCOPE_MISMATCH"):
        _registry(
            formal_scope=("F_continuity",),
        )


def test_m2_registry_requires_all_five_scales_and_four_references():
    with pytest.raises(ContractError, match="M2_V4_REQUIRES_SEVEN_TRAIN_SCALES"):
        _registry(
            train_scale_artifact=dict(list(_scale_payload().items())[:4]),
        )
    with pytest.raises(ContractError, match="M2_V4_PASSENGER_REFERENCE_ARTIFACT_MISSING"):
        _registry(
            reference_artifacts={"turnaround": _reference_payload()["turnaround"]},
        )


def test_m2_registry_weights_must_be_unity():
    with pytest.raises(ContractError, match="M2_COMPONENT_WEIGHT_NOT_UNITY"):
        _registry(
            component_weights={"F_continuity": 2.0, **{name: 1.0 for name in FORMAL_SCOPE[1:]}},
        )


def test_m2_registry_hash_is_self_consistent_and_write_once(tmp_path):
    base = _registry()
    registry = base.model_copy(update={"registry_hash": base.digest()})
    registry_path = tmp_path / "m2_data2_formal_cu_v1.json"
    manifest_path = tmp_path / "manifest.json"
    write_m2_registry(registry, registry_path=registry_path, manifest_path=manifest_path, root=tmp_path)
    assert registry_path.is_file() and manifest_path.is_file()
    loaded = load_m2_registry(registry_path)
    assert loaded.registry_id == REGISTRY_ID
    assert loaded.registry_hash == loaded.digest()
    with pytest.raises(ContractError, match="M2_REGISTRY_ALREADY_EXISTS"):
        write_m2_registry(registry, registry_path=registry_path, manifest_path=manifest_path, root=tmp_path)


def test_frozen_valuation_uses_positive_train_median_scale():
    registry = _registry()
    valuation = FrozenData2ValuationRegistry(registry)
    scope = scope_fixture(cu_normalization_registry_id=REGISTRY_ID)
    mapper = M2Mapper(valuation, scope)
    output = mapper.map_scenarios(
        (scenario(),),
        context(
            turnaround_reference=supported("turnaround_reference", 5),
            taxi_reference=supported("taxi_reference", 5),
                expected_downstream_exposure=supported("expected_downstream_exposure", 1),
                expected_passengers_per_flight=supported("expected_passengers_per_flight", 10),
                connection_share_reference=supported("connection_share_reference", 0.25),
                itinerary_buffer_reference=supported("itinerary_buffer_reference", 45),
                service_policy_reference=supported("service_policy_reference", 180),
        ),
    )[0]
    by_component = {row.component_id: row for row in output.component_vector.rows}
    for component in FORMAL_SCOPE:
        row = by_component[component]
        assert row.cu_status is CUNormalizationStatus.CU_FROZEN
        scale = registry.scale(component)
        assert row.constructed_value_cu == pytest.approx(row.native_quantity / scale)
    assert (
        output.formal_estimand_value.status is FormalEstimandStatus.FORMAL_AVAILABLE
    )


def test_fit_train_references_keys_match_registry_contract(monkeypatch):
    from model.PRE.reference import data2_m2_train_fit as fit

    from model.M2.context import smoke_reference_payloads
    from model.PRE.reference.exposure_data2 import (
        data2_downstream_exposure_from_payload,
    )
    from model.PRE.reference.passenger_data2 import (
        data2_passenger_reference_from_payload,
    )
    from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
    from model.PRE.reference.turnaround_data2 import (
        data2_turnaround_reference_from_payload,
    )

    payloads = smoke_reference_payloads()

    def _load(name):
        loaders = {
            "turnaround": data2_turnaround_reference_from_payload,
            "downstream_exposure": data2_downstream_exposure_from_payload,
            "taxi": data2_taxi_reference_from_payload,
            "passenger": data2_passenger_reference_from_payload,
        }
        return loaders[name](payloads[name])

    monkeypatch.setattr(
        fit, "build_data2_turnaround_reference",
        lambda rows, fit_period="2019-H1": _load("turnaround"),
    )
    monkeypatch.setattr(
        fit, "build_data2_downstream_exposure",
        lambda rows, fit_period="2019-H1": _load("downstream_exposure"),
    )
    monkeypatch.setattr(fit, "stream_passenger_routes", lambda coupon_paths: [])
    monkeypatch.setattr(
        fit, "build_data2_passenger_reference",
        lambda rows, fit_period="2019-H1", rule_id="": _load("passenger"),
    )
    monkeypatch.setattr(
        fit, "data2_taxi_reference_from_payload", lambda payload: _load("taxi"),
    )
    result = fit.fit_train_references([], root=Path("."), fit_period="2019-H1")
    assert set(result) == {"turnaround", "downstream_exposure", "passenger", "taxi"}


def test_m2_train_preparation_is_pre_owned_typed_canonical_artifact(tmp_path):
    timezone_path = tmp_path / "data2" / "refs" / "us_airport_timezones.csv"
    timezone_path.parent.mkdir(parents=True)
    timezone_path.write_text(
        "iata,ident,timezone\nJFK,KJFK,America/New_York\nLAX,KLAX,America/Los_Angeles\n",
        encoding="utf-8",
    )
    ontime = tmp_path / "data2" / "raw" / "bts" / "ontime" / "2019" / "month=01" / "rows.csv"
    ontime.parent.mkdir(parents=True)
    fields = [
        "FlightDate", "Reporting_Airline", "Tail_Number",
        "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime",
        "CRSArrTime", "DepTime", "ArrTime", "WheelsOff", "WheelsOn",
        "TaxiOut", "TaxiIn", "DepDelay", "ArrDelay", "DepDelayMinutes", "ArrDelayMinutes",
        "Cancelled", "Diverted",
    ]
    with ontime.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "FlightDate":"2019-01-02", "Reporting_Airline":"AA", "Tail_Number":"N1",
            "Flight_Number_Reporting_Airline":"10", "Origin":"JFK", "Dest":"LAX",
            "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0810",
            "ArrTime":"1110", "WheelsOff":"0820", "WheelsOn":"1100",
            "TaxiOut":"10", "TaxiIn":"10", "DepDelay":"10", "ArrDelay":"10",
            "DepDelayMinutes":"10",
            "ArrDelayMinutes":"10", "Cancelled":"0", "Diverted":"0",
        })
    artifact = build_data2_m2_train_preparation(root=tmp_path, months=(1,))
    assert artifact.schema_version == "DATA2_M2_TRAIN_PREPARATION_V1"
    assert artifact.final_test_access_count == 0
    assert artifact.months == (1,)
    assert len(artifact.rows) == 1
    assert artifact.rows[0]["aircraft_id"] == "N1"
    assert artifact.rows[0]["split"] == "train"


def test_frozen_valuation_abstains_when_passenger_route_missing():
    registry = _registry()
    valuation = FrozenData2ValuationRegistry(registry)
    scope = scope_fixture(
        components=FORMAL_SCOPE,
        cu_normalization_registry_id=REGISTRY_ID,
    )
    output = M2Mapper(valuation, scope).map_scenarios(
        (scenario(),),
        context(
            turnaround_reference=supported("turnaround_reference", 5),
            taxi_reference=supported("taxi_reference", 5),
            expected_downstream_exposure=supported("expected_downstream_exposure", 1),
        ),
    )[0]
    # Missing expected-passenger reference keeps the all-seven aggregate unavailable.
    assert output.formal_estimand_value.status is FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
    assert output.formal_estimand_value.value_cu is None
