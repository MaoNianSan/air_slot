"""Gate-B raw-source binding: guards, profile identity and typed exclusions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from formal import v2_phase7_final_test_run as runner
from formal.v2_phase7 import constants as C
from formal.v2_phase7.executor import pipeline, raw_entry, raw_source


def _open_authorization() -> dict[str, object]:
    return {
        "authorization_id": "GATE_B_HUMAN_RELEASE",
        "release": runner.make_release(),
        "access_epoch": {
            "status": "PHASE7_ACCESS_EPOCH_OPEN",
            "access_epoch_id": "epoch-test",
            "phase7_increment": 1,
            "current_total": 2,
            "raw_read_started": True,
        },
    }


def test_production_callback_binds_the_raw_source_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}

    def fake_run_sealed_pipeline(context, **kwargs):
        recorded["context"] = context
        recorded.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr(pipeline, "run_sealed_pipeline", fake_run_sealed_pipeline)
    context = {"release": {}, "access_epoch": {}}

    result = runner.production_pipeline(context)

    assert result == {"status": "PASS"}
    assert recorded["adapter"] is raw_source.production_raw_adapter
    assert recorded["context"] is context


def test_raw_entry_refuses_to_materialize_without_authorization() -> None:
    calls: list[object] = []

    def spy(authorization):
        calls.append(authorization)
        return {}

    with pytest.raises(runner.TypedBlocker) as error:
        raw_entry.materialize_canonical_nodes(
            authorization=None,
            adapter=spy,
        )
    assert error.value.code == "PHASE7_MATERIALIZATION_AUTHORIZATION_REQUIRED"
    assert calls == []

    closed = _open_authorization()
    closed["access_epoch"] = dict(closed["access_epoch"], status="CLOSED")
    with pytest.raises(runner.TypedBlocker) as closed_error:
        raw_entry.materialize_canonical_nodes(
            authorization=closed,
            adapter=spy,
        )
    assert closed_error.value.code == "PHASE7_MATERIALIZATION_ACCESS_EPOCH_NOT_OPEN"
    assert calls == []


def test_raw_entry_invokes_the_adapter_only_after_authorization() -> None:
    calls: list[object] = []

    def spy(_authorization):
        calls.append(_authorization)
        raise runner.TypedBlocker("SPY_RAW_READ", "synthetic")

    with pytest.raises(runner.TypedBlocker) as error:
        raw_entry.materialize_canonical_nodes(
            authorization=_open_authorization(),
            adapter=spy,
        )
    assert error.value.code == "SPY_RAW_READ"
    assert len(calls) == 1


def test_production_adapter_requires_an_explicit_local_input_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(raw_source.LOCAL_INPUT_ROOT_ENV, raising=False)
    monkeypatch.setattr(
        raw_source, "missing_local_inputs", lambda root: ("data2/raw",)
    )

    with pytest.raises(runner.TypedBlocker) as error:
        raw_source.resolve_local_input_root()

    assert error.value.code == "PHASE7_LOCAL_INPUT_ROOT_REQUIRED"
    assert error.value.detail["environment_variable"] == (
        raw_source.LOCAL_INPUT_ROOT_ENV
    )


def test_local_input_root_resolution_prefers_the_frozen_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(raw_source.LOCAL_INPUT_ROOT_ENV, raising=False)
    monkeypatch.setattr(raw_source, "missing_local_inputs", lambda root: ())

    root, record = raw_source.resolve_local_input_root()

    assert root == C.ROOT
    assert record["local_input_root_resolution"] == "FROZEN_EXECUTION_WORKTREE"


def test_declared_reference_payloads_match_frozen_development_inputs() -> None:
    from exp.exp2 import development_inputs as dev_inputs
    from model.common.paths import PROJECT_ROOT

    expected = {
        "turnaround": dev_inputs.TURNAROUND_A2_REFERENCE,
        "taxi": dev_inputs.PREP_ROOT
        / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
        "downstream_exposure": dev_inputs.PREP_ROOT
        / "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json",
        "passenger": dev_inputs.PREP_ROOT
        / "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json",
        "expected_passengers": dev_inputs.PASSENGER_REF_ROOT
        / "T100_EXPECTED_PAX_PER_FLIGHT_REFERENCE.json",
        "connection_share": dev_inputs.PASSENGER_REF_ROOT
        / "DB1B_CONNECTION_SHARE_REFERENCE.json",
    }
    resolved = {
        name: (PROJECT_ROOT / relative).resolve()
        for name, relative in raw_source.REFERENCE_PAYLOAD_FILES.items()
    }

    assert resolved == {
        name: path.resolve() for name, path in expected.items()
    }


def test_production_profile_matches_the_frozen_cohort_contract() -> None:
    profile = raw_source.PRODUCTION_RAW_PROFILE
    metadata = profile.as_metadata()

    assert profile.materialization_scope == raw_entry.MATERIALIZATION_SCOPE
    assert profile.source_months == (10, 11, 12)
    assert profile.allow_final_test is True
    assert profile.expected_split == "test"
    assert profile.expected_episode_count == 128
    assert metadata["cohort_manifest_file_sha256"] == (
        C.COHORT_MANIFEST_FILE_SHA256
    )
    assert json.dumps(metadata, sort_keys=True)


def test_frozen_cohort_manifest_reconstructs_the_selected_episode_identity() -> (
    None
):
    episode_ids = raw_source.load_cohort_manifest(
        raw_source.PRODUCTION_RAW_PROFILE
    )

    assert len(episode_ids) == 128
    assert list(episode_ids) == sorted(episode_ids)
    assert (
        raw_source._sha256_bytes("\n".join(episode_ids).encode("utf-8"))
        == C.SELECTED_EPISODE_HASH
    )


def test_cohort_manifest_rejects_a_tampered_episode_identity() -> None:
    profile = raw_source.PRODUCTION_RAW_PROFILE
    tampered = raw_source.RawMaterializationProfile(
        **{
            **profile.__dict__,
            "expected_selected_episode_hash": "sha256:" + "0" * 64,
        }
    )

    with pytest.raises(runner.TypedBlocker) as error:
        raw_source.load_cohort_manifest(tampered)

    assert error.value.code == (
        "PHASE7_RAW_COHORT_SELECTED_EPISODE_HASH_MISMATCH"
    )


def test_reference_payload_records_carry_the_file_hashes(tmp_path: Path) -> None:
    payloads: dict[str, object] = {}
    for name, relative in raw_source.REFERENCE_PAYLOAD_FILES.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"reference": name}) + "\n", encoding="utf-8")
        payloads[name] = target

    loaded, records = raw_source.load_reference_payloads(reference_root=tmp_path)

    assert set(loaded) == set(raw_source.REFERENCE_PAYLOAD_FILES)
    for name, target in payloads.items():
        assert records[name]["resolved_path"] == str(target)
        assert records[name]["file_sha256"] == raw_source._file_sha256(target)


def test_missing_reference_payload_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(runner.TypedBlocker) as error:
        raw_source.load_reference_payloads(reference_root=tmp_path)

    assert error.value.code == "PHASE7_RAW_REFERENCE_PAYLOAD_MISSING"


def _stub_node(decision_node_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        decision_node_id=decision_node_id,
        episode_id="episode-1",
        decision_time=datetime(2019, 10, 1, 12, 0),
        operational_stage=SimpleNamespace(value="PRE_IB"),
    )


class _StubState:
    def __init__(self) -> None:
        self.successor_state = {
            "route_context": SimpleNamespace(
                value={"destination_airport_id": "CLT"}
            ),
            "schedule_reference": SimpleNamespace(
                value={
                    "scheduled_departure_utc": datetime(2019, 10, 1, 13, 30)
                }
            ),
        }

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {"stub": True}


def _node_binding(binding: object | None, reason: str | None) -> object:
    from validation.v2_phase5.common import NodeBinding

    return NodeBinding(
        node_id="node-1",
        episode_id="episode-1",
        chain_id="chain-1",
        binding=binding,
        audit={
            "status": "SUPPORTED" if binding is not None else "UNSUPPORTED_REFERENCE",
            "reason_codes": [] if reason is None else [reason],
            "reference_support": {"downstream_exposure": "ABSTAIN"},
        },
    )


def _stub_published() -> SimpleNamespace:
    state = _StubState()
    return SimpleNamespace(
        episode=SimpleNamespace(
            connection_airport_id="PGV",
            episode_id="episode-1",
            dataset_instance_id="data2_2019",
        ),
        nodes=(_stub_node("node-1"),),
        states=(state,),
        successor_schedule=object(),
        predecessor_outcome=object(),
        successor_outcome=object(),
    )


def test_abstaining_reference_nodes_are_typed_exclusions_not_zero_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import model.M1.coverage as coverage
    import validation.v2_phase5.common as phase5_common

    monkeypatch.setattr(
        coverage,
        "active_node_prefixes",
        lambda **kwargs: iter(
            [(_stub_node("node-1"), (_StubState(),), ())]
        ),
    )
    monkeypatch.setattr(
        phase5_common,
        "build_node_binding",
        lambda **kwargs: _node_binding(
            None, "PHASE5_REFERENCE_ABSTAIN:downstream_exposure"
        ),
    )
    monkeypatch.setattr(
        phase5_common, "chain_id_for_episode", lambda episode: "chain-1"
    )

    nodes, excluded = raw_source.build_node_records(
        (_stub_published(),),
        normalization=None,
        taxi_reference=None,
        reference_bundle=None,
    )

    assert nodes == ()
    assert len(excluded) == 1
    assert excluded[0]["typed_state"] == raw_source.UNSUPPORTED_REFERENCE_STATE
    assert excluded[0]["zero_filled"] is False


def test_supported_reference_nodes_build_canonical_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import model.M1.coverage as coverage
    import model.M1.data as m1_data
    import model.M1.factual_state as m1_factual
    import validation.v2_phase5.common as phase5_common
    from model.M2.consequence_service import ConsequenceReferenceBinding

    binding = ConsequenceReferenceBinding(
        reference_id="node-1",
        turnaround_reference_minutes=57.0,
        taxi_reference_minutes=0.0,
        expected_pax=120.0,
        connection_share=0.3,
        downstream_exposure=1.1,
    )
    monkeypatch.setattr(
        coverage,
        "active_node_prefixes",
        lambda **kwargs: iter(
            [(_stub_node("node-1"), (_StubState(),), ())]
        ),
    )
    monkeypatch.setattr(
        phase5_common,
        "build_node_binding",
        lambda **kwargs: _node_binding(binding, None),
    )
    monkeypatch.setattr(
        phase5_common, "chain_id_for_episode", lambda episode: "chain-1"
    )
    monkeypatch.setattr(
        m1_data, "encode_pre_sequence", lambda prefix, normalization: _Tensor()
    )
    monkeypatch.setattr(
        m1_factual,
        "factual_observed_state",
        lambda state, taxi_reference_minutes=None: {
            "D_OB": 12.0,
            "observed_at": datetime(2019, 10, 1, 12, 5),
        },
    )

    nodes, excluded = raw_source.build_node_records(
        (_stub_published(),),
        normalization=None,
        taxi_reference=None,
        reference_bundle=None,
    )

    assert excluded == ()
    assert len(nodes) == 1
    node = nodes[0]
    assert node.binding["turnaround_reference_minutes"] == 57.0
    assert node.binding["expected_pax"] == 120.0
    assert node.sobt_minutes == 90.0
    assert node.observed["observed_at"] == "2019-10-01T12:05:00"
    assert node.history_values == ((1.0, 2.0),)


class _Tensor:
    def tolist(self) -> list[list[float]]:
        return [[1.0, 2.0]]
