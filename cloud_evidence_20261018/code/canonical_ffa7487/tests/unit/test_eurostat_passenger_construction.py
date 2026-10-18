import copy
import json

import pytest

from model.PRE.adapters.data1 import Data1Adapter
from model.PRE.adapters.registry import RawReadRequest
from model.PRE.canonical.normalization import (
    canonicalize_eurostat_passengers_payload,
    canonicalize_eurostat_payload,
)
from model.common.errors import ContractError

DIM_IDS = ["freq", "unit", "tra_meas", "rep_airp", "schedule", "tra_cov", "time"]
SIZES = [3, 2, 9, 3, 5, 3, 1]

DIMS = {
    "freq": {"category": {"index": {"Q": 0, "M": 1, "A": 2}}},
    "unit": {"category": {"index": {"PAS": 0, "FLIGHT": 1}}},
    "tra_meas": {"category": {"index": {
        "PAS_BRD": 0, "PAS_BRD_ARR": 1, "PAS_BRD_DEP": 2, "PAS_CRD": 3,
        "PAS_CRD_ARR": 4, "PAS_CRD_DEP": 5, "CAF_PAS": 6, "CAF_PAS_ARR": 7,
        "CAF_PAS_DEP": 8}}},
    "rep_airp": {"category": {"index": {"BE_EBBR": 0, "DE_EDDF": 1, "FR_LFPG": 2}}},
    "schedule": {"category": {"index": {"TOT": 0, "SCHED": 1, "NSCHED": 2, "N_SCHED": 3, "UNK": 4}}},
    "tra_cov": {"category": {"index": {"TOTAL": 0, "NAT": 1, "INTL": 2}}},
    "time": {"category": {"index": {"2019-01": 0}}},
}


def encode(freq, unit, tra_meas, rep_airp, schedule, tra_cov, time=0):
    index = freq
    for size, value in zip(SIZES[1:], (unit, tra_meas, rep_airp, schedule, tra_cov, time)):
        index = index * size + value
    return index


def passenger_payload(cells, extension="AVIA_PAOA"):
    return {
        "class": "dataset", "label": "avia_paoa", "source": "Eurostat",
        "updated": "2026-08-01", "id": list(DIM_IDS), "size": list(SIZES),
        "dimension": copy.deepcopy(DIMS), "extension": {"id": extension},
        "value": {str(encode(*cell)): value for cell, value in cells},
    }


def test_frozen_slice_only_materialized():
    payload = passenger_payload([
        ((1, 0, 0, 0, 0, 0), 100),   # M/PAS/PAS_BRD/BE_EBBR/TOT/TOTAL -> include
        ((1, 0, 0, 1, 0, 0), 200),   # M/PAS/PAS_BRD/DE_EDDF/TOT/TOTAL -> include
        ((1, 0, 3, 0, 0, 0), 999),   # PAS_CRD -> exclude
        ((1, 0, 0, 1, 1, 0), 888),   # SCHED -> exclude
        ((1, 0, 0, 2, 0, 1), 777),   # NAT -> exclude
        ((0, 0, 0, 0, 0, 0), 50),    # freq Q -> exclude
        ((1, 1, 0, 0, 0, 0), 10),    # unit FLIGHT -> exclude
    ])
    records = canonicalize_eurostat_passengers_payload(payload)
    assert len(records) == 2
    by_airport = {record.join_key["rep_airp"]: record for record in records}
    assert set(by_airport) == {"BE_EBBR", "DE_EDDF"}
    for airport, expected in (("BE_EBBR", 100), ("DE_EDDF", 200)):
        record = by_airport[airport]
        assert record.value == expected
        assert record.grain == "airport_month"
        assert record.unit == "passengers"
        assert record.reference_period == "2019-01"
        assert record.join_key == {"rep_airp": airport, "time": "2019-01",
                                   "measure": "PAS_BRD", "schedule": "TOT", "tra_cov": "TOTAL"}
        assert record.provenance_rule_id == "D1-EUROSTAT"
        assert record.decision_time_role.value == "FROZEN_REFERENCE"


def test_sparse_missing_cells_are_not_zero_fabricated():
    payload = passenger_payload([((1, 0, 0, 0, 0, 0), 100)])
    records = canonicalize_eurostat_passengers_payload(payload)
    assert len(records) == 1
    assert records[0].join_key["rep_airp"] == "BE_EBBR"


def test_explicit_zero_is_preserved_as_observed():
    payload = passenger_payload([((1, 0, 0, 1, 0, 0), 0)])
    records = canonicalize_eurostat_passengers_payload(payload)
    assert len(records) == 1
    assert records[0].value == 0


def test_output_is_deterministic_and_sorted():
    cells = [((1, 0, 0, 1, 0, 0), 200), ((1, 0, 0, 0, 0, 0), 100)]
    first = canonicalize_eurostat_passengers_payload(passenger_payload(cells))
    second = canonicalize_eurostat_passengers_payload(passenger_payload(list(reversed(cells))))
    assert first == second
    assert [r.join_key["rep_airp"] for r in first] == ["BE_EBBR", "DE_EDDF"]
    assert first[0].canonical_record_id != first[1].canonical_record_id


def test_schema_mismatches_raise_explicitly():
    with pytest.raises(ContractError, match="EUROSTAT_JSON_STAT_SCHEMA_MISMATCH"):
        canonicalize_eurostat_passengers_payload({"class": "cube"})
    broken = passenger_payload([((1, 0, 0, 0, 0, 0), 100)])
    del broken["id"]
    with pytest.raises(ContractError, match="EUROSTAT_JSON_STAT_DIMENSIONS_MISMATCH"):
        canonicalize_eurostat_passengers_payload(broken)
    no_slice = passenger_payload([((1, 0, 0, 0, 0, 0), 100)])
    del no_slice["dimension"]["tra_meas"]["category"]["index"]["PAS_BRD"]
    with pytest.raises(ContractError, match="EUROSTAT_SLICE_MISSING:tra_meas:PAS_BRD"):
        canonicalize_eurostat_passengers_payload(no_slice)


def test_cube_metadata_path_unchanged_for_non_passenger_cubes():
    payload = passenger_payload([((1, 0, 0, 0, 0, 0), 100)], extension="AVIA_TF_AIRPM")
    record = canonicalize_eurostat_payload(payload)
    assert record.grain == "json_stat_cube"
    assert record.reference_name == "AVIA_TF_AIRPM"


def test_adapter_dispatches_passengers_to_airport_month(tmp_path):
    raw_root = tmp_path / "rawroot"
    output_root = tmp_path / "out"
    output_root.mkdir()
    flights_dir = raw_root / "raw" / "eurostat" / "2019" / "commercial_flights"
    passengers_dir = raw_root / "raw" / "eurostat" / "2019" / "passengers"
    flights_dir.mkdir(parents=True)
    passengers_dir.mkdir(parents=True)
    (flights_dir / "avia_tf_airpm_2019-01.json").write_text(
        json.dumps(passenger_payload([((1, 0, 0, 0, 0, 0), 100)], extension="AVIA_TF_AIRPM")),
        encoding="utf-8")
    (passengers_dir / "avia_paoa_2019-01.json").write_text(
        json.dumps(passenger_payload([((1, 0, 0, 0, 0, 0), 100),
                                      ((1, 0, 0, 1, 0, 0), 200)])), encoding="utf-8")
    request = RawReadRequest(dataset_instance_id="data1_2019", source_family="eurostat",
        raw_root=raw_root, output_root=output_root, year=2019, max_files=2)
    records = list(Data1Adapter().iter_canonical(request))
    grains = [record.grain for record in records]
    assert "json_stat_cube" in grains
    assert grains.count("airport_month") == 2
    passenger_records = [r for r in records if r.grain == "airport_month"]
    assert {r.join_key["rep_airp"] for r in passenger_records} == {"BE_EBBR", "DE_EDDF"}
