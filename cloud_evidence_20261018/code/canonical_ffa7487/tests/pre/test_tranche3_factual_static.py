"""Tranche 3 PRE factual-role + static/reference publication tests.

Covers spec section 14 items 11-28:
- 11 archive outcome does not imply inference availability
- 12 FACTUAL_REPLAY requires availability <= information_cutoff
- 13 PRE_IB unresolved
- 14 POST_IB fixes T_IB
- 15 POST_OB fixes T_IB + D_OB
- 16 COMPLETED fixes all
- 17 no future-event leakage
- 18 public event timestamp preserved
- 19-24 route/carrier/aircraft/schedule/turnaround/taxi published
- 25 taxi label/input freeze lineage identical
- 26 dynamic schedule countdown not duplicated static
- 27 retained identity not fabricated as numeric ordinal
- 28 unsupported resource state still forbidden
"""

from datetime import datetime, timezone

import pytest
import torch

from model.common.enums import SupportState
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1StaticReferenceContext,
    M1_V2_HAZARD_COORDINATE,
    static_reference_context_from_pre,
)
from model.M1.data import STATIC_FEATURE_COUNT, STATIC_FEATURE_NAMES
from model.M1.factual_state import factual_observed_state
from model.M1.model_layer.gru import M1V2GRU
from model.M1.pipeline import M1Pipeline
from model.M1.static_features import (
    M1StaticNormalizationArtifact,
    StaticNormalizationValue,
    static_reference_features_from_pre,
)
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre
from model.PRE.factual.availability import factual_replay_legal
from model.PRE.reference.taxi_data2 import Data2TaxiReference, Data2TaxiReferenceCell
from model.PRE.reference.turnaround_data2 import (
    Data2TurnaroundReference,
    Data2TurnaroundReferenceCell,
)

UTC = timezone.utc
ZONES = {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}


def _pred_row():
    # Predecessor window (UTC): dep 12:35, wheels-off 12:50, wheels-on 12:45,
    # arrival 12:55; event_time (min) = 12:35 so the availability gate is
    # illegal at cutoff 12:30 and legal at cutoff 13:00.
    return {"FlightDate": "2019-01-01", "Reporting_Airline": "AA",
        "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "9",
        "Origin": "LAX", "Dest": "JFK", "CRSDepTime": "0435", "CRSArrTime": "0755",
        "DepTime": "0435", "ArrTime": "0755", "WheelsOff": "0450", "WheelsOn": "0745",
        "TaxiOut": "15", "TaxiIn": "10", "DepDelay": "0", "ArrDelay": "0",
        "DepDelayMinutes": "0", "ArrDelayMinutes": "0",
        "Cancelled": "0", "Diverted": "0"}


def _succ_row():
    return {"FlightDate": "2019-01-01", "Reporting_Airline": "AA",
        "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "10",
        "Origin": "JFK", "Dest": "LAX", "CRSDepTime": "0800", "CRSArrTime": "1100",
        "DepTime": "0810", "ArrTime": "1120", "WheelsOff": "0825", "WheelsOn": "1105",
        "TaxiOut": "15", "TaxiIn": "15", "DepDelay": "10", "ArrDelay": "20",
        "DepDelayMinutes": "10", "ArrDelayMinutes": "20",
        "Cancelled": "0", "Diverted": "0"}


def _records():
    pred_schedule, pred_outcome = canonicalize_ontime_row(_pred_row(), ZONES)
    succ_schedule, succ_outcome = canonicalize_ontime_row(_succ_row(), ZONES)
    return (pred_schedule, pred_outcome, succ_schedule, succ_outcome),         pred_outcome.flight_id, succ_outcome.flight_id


def _publish(records, pred_id, succ_id, *, decision_time, cutoff, stage,
             policy="DECLARED_RULE", lag_minutes=0.0,
             taxi_reference=None, turnaround_reference=None, dataset="data2_2019"):
    return publish_production_pre(ProductionPRERequest(
        episode_id="ep", predecessor_id=pred_id, successor_id=succ_id,
        dataset_instance_id=dataset, decision_time=decision_time,
        information_cutoff=cutoff, records=tuple(records),
        config_hash="sha256:c", registry_hash="sha256:r",
        operational_stage=stage,
        factual_availability_policy=policy,
        factual_replay_declared_lag_minutes=lag_minutes,
        taxi_reference=taxi_reference, turnaround_reference=turnaround_reference,
    )).pre_state


def _taxi_reference(*, value=12.0):
    return Data2TaxiReference(
        reference_id="DATA2_TAXI_REFERENCE@1.0.0",
        dataset_instance_id="data2_2019", rule_id="DATA2_TAXI_REFERENCE",
        rule_version="1.0.0", fit_period="train", statistic_id="MEDIAN",
        minimum_support_rule="MIN_CELL_SIZE_50",
        fallback_hierarchy=("AIRPORT_CELL", "GLOBAL"),
        applicability_scope="AIRPORT_GROUP", global_value_minutes=value,
        global_sample_count=500,
        cells=(Data2TaxiReferenceCell(
            airport_id="JFK", value_minutes=value, sample_count=120,
            fallback_level="AIRPORT_CELL", provenance=("train",)),),
        manifest_freeze_id="sha256:taxi-ref",
        support_state=SupportState.SUPPORTED, reason_code="TRAIN_FROZEN")


def _static_normalization():
    return M1StaticNormalizationArtifact(
        fitted_split="train",
        episode_level_fit=True,
        episode_count=2,
        episode_ids_hash="sha256:static-normalization-test",
        values={
            "turnaround_reference_minutes": StaticNormalizationValue(
                count=2, mean=40.0, std=5.0, min=35.0, max=45.0
            ),
            "taxi_reference_minutes": StaticNormalizationValue(
                count=2, mean=10.0, std=2.0, min=8.0, max=12.0
            ),
        },
    )


def _static_pipeline():
    """Smoke pipeline wired with the PRE-published c_static block."""
    contracts = {
        M1_V2_HAZARD_COORDINATE: HazardBinContract(
            bin_width_minutes=5, max_finite_minutes=60),
        "D_OB": HurdleQuantileContract(
            target_name="D_OB", bin_width_minutes=5, max_finite_minutes=60,
            quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
            upper_tail_policy="TEST_ONLY_LINEAR"),
        "D_TX": HurdleQuantileContract(
            target_name="D_TX", bin_width_minutes=5, max_finite_minutes=30,
            quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
            upper_tail_policy="TEST_ONLY_LINEAR"),
    }
    torch.manual_seed(4)
    model = M1V2GRU(4, 16, contracts[M1_V2_HAZARD_COORDINATE],
                    contracts["D_OB"], contracts["D_TX"],
                    fast_input_size=4, static_input_size=STATIC_FEATURE_COUNT)
    return M1Pipeline(model, contracts, static_normalization=_static_normalization())


def _turnaround_reference(*, value=45.0):
    return Data2TurnaroundReference(
        reference_id="DATA2_TURNAROUND_REFERENCE@1.0.0",
        dataset_instance_id="data2_2019", rule_id="DATA2_TURNAROUND_REFERENCE",
        rule_version="1.0.0", fit_period="train", statistic_id="MEDIAN",
        minimum_support_rule="MIN_CELL_SIZE_50",
        fallback_hierarchy=("AIRPORT_CELL", "GLOBAL"),
        applicability_scope="AIRPORT_GROUP", global_value_minutes=value,
        global_sample_count=500,
        cells=(Data2TurnaroundReferenceCell(
            airport_id="JFK", value_minutes=value, sample_count=120,
            fallback_level="AIRPORT_CELL", provenance=("train",)),),
        manifest_freeze_id="sha256:turnaround-ref",
        support_state=SupportState.SUPPORTED, reason_code="TRAIN_FROZEN")


# ---------------------------------------------------------------------------
# 11/12. archive outcome vs inference availability
# ---------------------------------------------------------------------------

def test_11_archive_outcome_does_not_imply_inference_availability():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC), stage="POST_IB_PRE_OB",
                   policy="UNRESOLVED")
    # The realized records exist in the archive but UNRESOLVED never enables
    # the factual-replay role: inference sees no operational facts.
    assert "predecessor_operational_fact" not in pre.current_state
    assert "successor_operational_fact" not in pre.successor_state
    assert factual_observed_state(pre) == {}


def test_12_factual_replay_requires_availability_leq_cutoff():
    records, pred_id, succ_id = _records()
    # Predecessor arrival 12:55 + 30 min lag = 13:25 > 13:00 cutoff => blocked.
    before = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                      cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC), stage="POST_IB_PRE_OB",
                      lag_minutes=30.0)
    assert "predecessor_operational_fact" not in before.current_state
    # Same archive record, later cutoff 13:30 >= 13:25 => legal replay.
    after = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, 30, tzinfo=UTC),
                     cutoff=datetime(2019, 1, 1, 13, 30, tzinfo=UTC), stage="POST_OB_PRE_TO",
                     lag_minutes=30.0)
    fact = after.current_state["predecessor_operational_fact"].value
    assert fact["decision_time_role"] == "FACTUAL_REPLAY_EVIDENCE"
    assert fact["availability_time"] == datetime(2019, 1, 1, 13, 25, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 13-18. factual state contraction stages
# ---------------------------------------------------------------------------

def test_13_pre_ib_unresolved():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 12, 30, tzinfo=UTC), stage="PRE_IB")
    assert factual_observed_state(pre) == {}


def test_future_event_is_illegal_even_with_malformed_early_availability():
    cutoff = datetime(2019, 1, 1, 12, tzinfo=UTC)
    assert not factual_replay_legal(
        event_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
        availability_time=datetime(2019, 1, 1, 11, tzinfo=UTC),
        information_cutoff=cutoff,
        policy="DECLARED_RULE",
    )


def test_14_post_ib_fixes_t_ib():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC), stage="POST_IB_PRE_OB")
    observed = factual_observed_state(pre)
    assert observed["T_IB_A00"] == "2019-01-01T12:55:00+00:00"
    assert "D_OB" not in observed and "D_TX" not in observed


def test_15_post_ob_fixes_t_ib_and_d_ob():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 15, tzinfo=UTC), stage="POST_OB_PRE_TO")
    observed = factual_observed_state(pre)
    assert observed["T_IB_A00"] == "2019-01-01T12:55:00+00:00"
    assert observed["D_OB"] == pytest.approx(10.0)  # 13:10 actual - 13:00 CRS
    assert "D_TX" not in observed


def test_16_completed_fixes_all():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, 30, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 30, tzinfo=UTC), stage="COMPLETED",
                   taxi_reference=_taxi_reference(value=12.0),
                   turnaround_reference=_turnaround_reference())
    observed = factual_observed_state(pre)
    assert observed["T_IB_A00"] == "2019-01-01T12:55:00+00:00"
    assert observed["D_OB"] == pytest.approx(10.0)
    assert observed["D_TX"] == pytest.approx(3.0)  # 15 taxi_out - 12 reference


def test_17_no_future_event_leakage():
    records, pred_id, succ_id = _records()
    # Cutoff 13:00: the successor departure (13:10) and its future
    # WheelsOff/WheelsOn (13:25/19:05) exist in the archive but cannot enter
    # inference before the availability gate.
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC), stage="POST_IB_PRE_OB",
                   lag_minutes=0.0)
    assert "successor_operational_fact" not in pre.successor_state
    assert factual_observed_state(pre) == {"T_IB_A00": "2019-01-01T12:55:00+00:00"}


def test_18_public_event_timestamp_preserved():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, 30, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 30, tzinfo=UTC), stage="COMPLETED",
                   taxi_reference=_taxi_reference(value=12.0),
                   turnaround_reference=_turnaround_reference())
    observed = factual_observed_state(pre)
    # T_IB arrival (12:55) is before the decision time (R_IB = 0) but the
    # absolute UTC event identity is preserved, never collapsed to 0.
    assert observed["T_IB_A00"] == "2019-01-01T12:55:00+00:00"


# ---------------------------------------------------------------------------
# 19-24. static/reference publication fields
# ---------------------------------------------------------------------------

def _published_pre(*, taxi=None, turnaround=None):
    records, pred_id, succ_id = _records()
    return _publish(records, pred_id, succ_id, decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                    cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC), stage="POST_IB_PRE_OB",
                    taxi_reference=taxi, turnaround_reference=turnaround)


def test_19_route_published():
    pre = _published_pre()
    value = pre.successor_state["route_context"].value
    assert value["origin_airport_id"] == "JFK"
    assert value["destination_airport_id"] == "LAX"
    assert value["route_key"] == "JFK-LAX"
    assert pre.static_reference_publication["route_context"][
        "publication_status"] == "MODEL_FEATURE_PENDING"


def test_20_carrier_published():
    pre = _published_pre()
    value = pre.successor_state["carrier_context"].value
    assert value["carrier_id"] == "AA"


def test_21_aircraft_identity_published():
    pre = _published_pre()
    value = pre.successor_state["aircraft_identity"].value
    assert value["aircraft_id"] == "N1"
    assert value["aircraft_id_namespace"] == "REGISTRATION"
    assert pre.static_reference_publication["aircraft_identity"][
        "publication_status"] == "RETAINED_IDENTITY"


def test_22_schedule_reference_published():
    pre = _published_pre()
    value = pre.successor_state["schedule_reference"].value
    assert value["scheduled_departure_utc"] == datetime(2019, 1, 1, 13, tzinfo=UTC)
    assert value["schedule_semantics"] == "CRS_DEPARTURE"
    assert pre.static_reference_publication["schedule_reference"][
        "publication_status"] == "RETAINED_IDENTITY"


def test_23_turnaround_frozen_reference_published():
    pre = _published_pre(turnaround=_turnaround_reference(value=45.0))
    value = pre.successor_state["turnaround_reference"].value
    assert value["value"] == pytest.approx(45.0)
    assert value["reference_id"] == "DATA2_TURNAROUND_REFERENCE@1.0.0"
    assert value["freeze_id"] == "sha256:turnaround-ref"
    assert value["support_state"] == "SUPPORTED"
    assert pre.static_reference_publication["turnaround_reference"][
        "model_feature_status"] == "MODEL_FEATURE"


def test_24_taxi_frozen_reference_published():
    pre = _published_pre(taxi=_taxi_reference(value=12.0))
    value = pre.successor_state["taxi_reference"].value
    assert value["value"] == pytest.approx(12.0)
    assert value["reference_id"] == "DATA2_TAXI_REFERENCE@1.0.0"
    assert value["freeze_id"] == "sha256:taxi-ref"
    assert pre.static_reference_publication["taxi_reference"][
        "model_feature_status"] == "MODEL_FEATURE"


# ---------------------------------------------------------------------------
# 25-28. M1 static typed wiring over the PRE publication
# ---------------------------------------------------------------------------

def _static_context(pre):
    return static_reference_context_from_pre(pre.static_reference_publication)


def test_25_taxi_label_input_freeze_lineage_identical():
    taxi = _taxi_reference(value=12.0)
    pre = _published_pre(taxi=taxi, turnaround=_turnaround_reference(value=45.0))
    context = _static_context(pre)
    assert isinstance(context, M1StaticReferenceContext)
    assert context.static_context_status == "PRE_PUBLISHED"
    static, lineage = static_reference_features_from_pre(
        pre, context, _static_normalization()
    )
    turnaround_value, taxi_value, turnaround_missing, taxi_missing = static[0].tolist()
    assert taxi_value == pytest.approx(1.0)
    assert turnaround_value == pytest.approx(1.0)
    assert turnaround_missing == 0.0
    assert taxi_missing == 0.0
    # The D_TX label construction and the M1 static input reference the SAME
    # frozen taxi reference identity (freeze lineage equality).
    published_taxi = pre.successor_state["taxi_reference"].value
    assert published_taxi["reference_id"] == "DATA2_TAXI_REFERENCE@1.0.0"
    assert published_taxi["freeze_id"] == "sha256:taxi-ref"
    # Scenario provenance carries the same reference id/hash used by the label
    # and the static input (the pipeline consumes the published c_static).
    pipe = _static_pipeline()
    values = torch.zeros(1, 2, 4)
    scenarios = pipe.sample_from_pre(
        pre, values, torch.tensor([2]),
        observed=factual_observed_state(pre), count=2, seed=7)
    assert all(row.taxi_reference_id == "DATA2_TAXI_REFERENCE@1.0.0" for row in scenarios)
    assert all(row.taxi_reference_hash == "sha256:taxi-ref" for row in scenarios)


def test_reference_lineage_equal():
    pre = _published_pre(
        taxi=_taxi_reference(value=12.0),
        turnaround=_turnaround_reference(value=45.0),
    )
    context = _static_context(pre)
    assert context.turnaround_reference.value["value"] == pytest.approx(45.0)
    assert context.turnaround_reference.reference_id == (
        "DATA2_TURNAROUND_REFERENCE@1.0.0")
    assert context.turnaround_reference.freeze_id == "sha256:turnaround-ref"
    assert context.turnaround_reference.provenance is not None
    assert context.taxi_reference.value["value"] == pytest.approx(12.0)
    assert context.taxi_reference.reference_id == "DATA2_TAXI_REFERENCE@1.0.0"
    assert context.taxi_reference.freeze_id == "sha256:taxi-ref"
    assert context.taxi_reference.provenance is not None


def test_26_dynamic_schedule_countdown_not_duplicated_static():
    assert "schedule.signed_minutes_to_crs_departure" not in STATIC_FEATURE_NAMES
    pre = _published_pre()
    context = _static_context(pre)
    assert "schedule_reference" in context.published_fields()
    field = getattr(context, "schedule_reference")
    assert field.model_feature_status == "RETAINED_IDENTITY"
    assert "schedule_reference" not in context.model_feature_fields()


def test_27_retained_identity_not_fabricated_numeric_ordinal():
    # No frozen numeric references: the retained identities are published but
    # never become ordinal floats in c_static.
    pre = _published_pre()
    context = _static_context(pre)
    assert context.aircraft_identity.model_feature_status == "RETAINED_IDENTITY"
    assert context.route_context.model_feature_status == "MODEL_FEATURE_PENDING"
    static, lineage = static_reference_features_from_pre(
        pre, context, _static_normalization()
    )
    assert static.tolist() == [[0.0, 0.0, 1.0, 1.0]]
    assert lineage["aircraft_identity"]["aircraft_id"] == "N1"
    assert isinstance(lineage["aircraft_identity"]["aircraft_id"], str)


def test_28_unsupported_resource_state_still_forbidden():
    from model.PRE.canonical.normalization import canonicalize_metar_row
    from datetime import timedelta
    weather = canonicalize_metar_row(
        {"station": "LSZH", "valid": "2019-01-01 11:50+00:00",
         "tmpf": "32", "dwpf": "23", "drct": "180", "sknt": "10",
         "gust": "M", "mslp": "M", "vsby": "10",
         "metar": "LSZH 011150Z 18010KT Q1013"},
        replay_lag_minutes=5)
    pre = publish_production_pre(ProductionPRERequest(
        episode_id="e", predecessor_id="p", successor_id="s",
        dataset_instance_id="data1_2019",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=UTC),
        information_cutoff=datetime(2019, 1, 1, 12, tzinfo=UTC),
        records=(weather,), config_hash="sha256:c", registry_hash="sha256:r",
    )).pre_state
    # No schedule => route/carrier/aircraft/schedule fields ABSTAIN (never
    # fabricated SUPPORTED-with-None), and no numeric static block exists.
    assert pre.successor_state["route_context"].support_state is SupportState.ABSTAIN
    assert pre.successor_state["route_context"].reason_code == "NO_SCHEDULE"
    context = static_reference_context_from_pre(pre.static_reference_publication)
    static, _ = static_reference_features_from_pre(
        pre, context, _static_normalization()
    )
    assert static.tolist() == [[0.0, 0.0, 1.0, 1.0]]
