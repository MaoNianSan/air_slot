"""Development-safe regressions for the canonical stage-node contract."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from formal import v2_phase7_final_test_run as runner
from formal.v2_phase7 import constants as C
from formal.v2_phase7.executor import raw_source, stages as S
from formal.v2_phase7.executor.attention_decisions import build_attention_decisions
from formal.v2_phase7.executor.nodes import (
    CanonicalNode,
    canonical_nodes_payload,
    canonical_stage_group,
    canonicalize_stage_nodes,
)
from formal.v2_phase7.executor.runner import run_development_safe_dag
from model.common.decision_contracts import (
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState


def _node(
    node_id: str,
    episode_id: str,
    stage: str,
    decision_time: str,
) -> CanonicalNode:
    return CanonicalNode(
        node_id=node_id,
        episode_id=episode_id,
        chain_id=f"chain-{episode_id}",
        stage=stage,
        decision_time=decision_time,
        sobt_minutes=90.0,
        connection_airport_id="AAA",
        destination_airport_id="BBB",
        observed={},
        binding={"turnaround_reference_minutes": 41.0},
        history_values=((0.0, 0.0),),
        pre_state={},
    )


def test_rolling_to_canonical_reduction_uses_one_node_per_episode_stage() -> None:
    rolling = (
        _node("a-pre-t0", "A", "PRE_IB", "2019-01-01T00:00:00+00:00"),
        _node("a-pre-t1", "A", "PRE_IB", "2019-01-01T00:05:00+00:00"),
        _node("a-pre-t2", "A", "PRE_IB", "2019-01-01T00:10:00+00:00"),
        _node("a-turn-t3", "A", "POST_IB_PRE_OB", "2019-01-01T00:15:00+00:00"),
        _node("a-turn-t4", "A", "POST_IB_PRE_OB", "2019-01-01T00:20:00+00:00"),
        _node("b-pre-t0", "B", "PRE_IB", "2019-01-01T00:00:00+00:00"),
        _node("b-pre-t1", "B", "PRE_IB", "2019-01-01T00:05:00+00:00"),
    )
    selected = canonicalize_stage_nodes(rolling)
    assert {node.node_id for node in selected} == {
        "a-pre-t0",
        "a-turn-t3",
        "b-pre-t0",
    }
    payload = canonical_nodes_payload(
        rolling,
        scope="UNIT_TEST",
        provenance={"scope": "SYNTHETIC"},
    )
    assert payload["materialized_rolling_node_count"] == 7
    assert payload["node_count"] == 3
    assert set(payload["canonical_decision_node_ids"]) == {
        "a-pre-t0",
        "a-turn-t3",
        "b-pre-t0",
    }
    assert payload["rolling_stage_counts"] == {
        "POST_IB_PRE_OB": 2,
        "PRE_IB": 5,
    }


def test_canonical_identity_selection_ignores_representation_and_support() -> None:
    identities = [
        {
            "node_id": "early",
            "episode_id": "episode",
            "stage": "PRE_IB",
            "decision_time": "2019-01-01T00:00:00+00:00",
            "representation_id": "HISTORY_JOINT",
            "support": "ABSTAIN",
        },
        {
            "node_id": "late",
            "episode_id": "episode",
            "stage": "PRE_IB",
            "decision_time": "2019-01-01T00:05:00+00:00",
            "representation_id": "CURRENT_JOINT",
            "support": "SUPPORTED",
        },
    ]
    selected = canonical_stage_group(identities)
    assert [item["node_id"] for item in selected] == ["early"]


class _StubState:
    def __init__(self, departure: datetime) -> None:
        self.successor_state = {
            "route_context": SimpleNamespace(
                value={"destination_airport_id": "BBB"}
            ),
            "schedule_reference": SimpleNamespace(
                value={"scheduled_departure_utc": departure}
            ),
        }

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"stub": True}


class _StubTensor:
    def tolist(self) -> list[list[float]]:
        return [[1.0, 2.0]]


def _published_node(
    node_id: str,
    decision_time: datetime,
) -> tuple[SimpleNamespace, _StubState]:
    node = SimpleNamespace(
        decision_node_id=node_id,
        episode_id="episode-1",
        decision_time=decision_time,
        operational_stage=SimpleNamespace(value="PRE_IB"),
    )
    state = _StubState(decision_time)
    return node, state


def test_canonical_node_abstains_when_earliest_support_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import model.M1.coverage as coverage
    import model.M1.data as m1_data
    import model.M1.factual_state as m1_factual
    import validation.v2_phase5.common as phase5_common

    early_node, early_state = _published_node(
        "early", datetime(2019, 1, 1, 0, 0)
    )
    late_node, late_state = _published_node(
        "late", datetime(2019, 1, 1, 0, 5)
    )
    monkeypatch.setattr(
        coverage,
        "active_node_prefixes",
        lambda **kwargs: iter(
            [(early_node, (early_state,), ()), (late_node, (late_state,), ())]
        ),
    )
    monkeypatch.setattr(
        phase5_common,
        "chain_id_for_episode",
        lambda episode: "chain-1",
    )

    def _binding(**kwargs: Any) -> Any:
        from validation.v2_phase5.common import NodeBinding

        node_id = str(kwargs["node_id"])
        supported = node_id == "late"
        binding = None
        if supported:
            from model.M2.consequence_service import (
                ConsequenceReferenceBinding,
            )

            binding = ConsequenceReferenceBinding(
                reference_id=node_id,
                turnaround_reference_minutes=41.0,
                taxi_reference_minutes=0.0,
                expected_pax=120.0,
                connection_share=0.3,
                downstream_exposure=1.1,
            )
        return NodeBinding(
            node_id=node_id,
            episode_id="episode-1",
            chain_id="chain-1",
            binding=binding,
            audit={
                "status": "SUPPORTED" if supported else "UNSUPPORTED_REFERENCE",
                "reason_codes": [] if supported else ["PHASE5_REFERENCE_ABSTAIN"],
                "reference_support": {"downstream_exposure": "ABSTAIN"},
            },
        )

    monkeypatch.setattr(phase5_common, "build_node_binding", _binding)
    monkeypatch.setattr(
        m1_data,
        "encode_pre_sequence",
        lambda prefix, normalization: _StubTensor(),
    )
    monkeypatch.setattr(
        m1_factual,
        "factual_observed_state",
        lambda state, taxi_reference_minutes=None: {},
    )
    published = SimpleNamespace(
        episode=SimpleNamespace(
            connection_airport_id="AAA",
            episode_id="episode-1",
            dataset_instance_id="data2_2019",
        ),
        nodes=(early_node, late_node),
        states=(early_state, late_state),
        successor_schedule=object(),
        predecessor_outcome=object(),
        successor_outcome=object(),
    )
    nodes, excluded, rolling = raw_source.materialize_node_records(
        (published,),
        normalization=None,
        taxi_reference=None,
        reference_bundle=None,
    )
    assert nodes == ()
    assert [item["node_id"] for item in excluded] == ["early"]
    assert excluded[0]["canonical_decision_node"] is True
    assert [(item["node_id"], item["canonical_selected"]) for item in rolling] == [
        ("early", True),
        ("late", False),
    ]


def _attention_row(
    variant: str,
    node_id: str,
    episode_id: str,
    stage: str,
) -> dict[str, Any]:
    def signal(kind: SignalKind) -> dict[str, Any]:
        value = PrioritySignal(
            signal_type=kind,
            episode_id=episode_id,
            chain_id=f"chain-{episode_id}",
            node_id=node_id,
            representation_id=variant,
            score=1.0,
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        from formal.v2_phase7.executor.codec import priority_signal_to_payload

        return priority_signal_to_payload(value)

    return {
        "variant": variant,
        "episode_id": episode_id,
        "node_id": node_id,
        "stage": stage,
        "delay_signal": signal(SignalKind.DELAY),
        "consequence_signal": signal(SignalKind.CONSEQUENCE),
    }


def test_stage1_rejects_duplicate_episode_stage_candidate_queue() -> None:
    rows = [
        _attention_row(variant, node_id, "episode-1", "PRE_IB")
        for variant in S.PRIMARY_STATE_VARIANTS
        for node_id in ("node-a", "node-b")
    ]
    with pytest.raises(runner.TypedBlocker) as error:
        build_attention_decisions(
            ("node-a", "node-b"),
            consequence_variants={
                "rows": rows,
                "reference_variant": S.REFERENCE_VARIANT,
            },
        )
    assert error.value.code == (
        "PHASE7_STAGE1_NONCANONICAL_EPISODE_STAGE_DUPLICATION"
    )


def test_rolling_information_is_preserved_outside_stage1() -> None:
    rolling = (
        _node("pre-early", "A", "PRE_IB", "2019-01-01T00:00:00+00:00"),
        _node("pre-late", "A", "PRE_IB", "2019-01-01T00:05:00+00:00"),
        _node("taxi", "A", "POST_OB_PRE_TO", "2019-01-01T00:10:00+00:00"),
        _node("comp", "A", "COMPLETED", "2019-01-01T00:15:00+00:00"),
    )
    payload = canonical_nodes_payload(
        rolling,
        scope="UNIT_TEST",
        provenance={},
    )
    assert payload["materialized_rolling_node_count"] == 4
    assert set(payload["materialized_rolling_node_ids"]) == {
        "pre-early",
        "pre-late",
        "taxi",
        "comp",
    }
    assert payload["canonical_stage_counts"] == {
        "COMPLETED": 1,
        "POST_OB_PRE_TO": 1,
        "PRE_IB": 1,
    }


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def test_failed_epoch_is_unmodified_by_development_safe_dag(
    tmp_path: Path,
) -> None:
    failed_root = C.CONSUMED_STAGE_MATCHED_FINAL_TEST_ROOT
    if not failed_root.is_dir():
        pytest.skip("failed stage-matched epoch is not materialized")
    before = _tree_sha256(failed_root)
    run_development_safe_dag(
        output_root=tmp_path / "safe_dag",
        node_limit=8,
        resume=False,
    )
    after = _tree_sha256(failed_root)
    assert after == before
