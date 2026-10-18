"""Stage x screening-capacity ``q`` Stage-I decision sufficiency regressions.

Two layers:

* development-safe contract tests of the frozen selector behaviour through
  :func:`formal.v2_phase7.stage_q_screening_sensitivity.materialize_stage_q_shortlist`
  on synthetic :class:`PrioritySignal` queues - no sealed epoch required;
* sealed-epoch projection tests that run the real entrypoint against the
  canonical-v2 epoch and assert the nominal ``q = 0.10`` reproduction plus the
  across-``q`` cohort / support / score invariants. These skip when the sealed
  epoch or the staged nominal baseline is not present in this checkout.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from formal.v2_phase7 import constants as C
from formal.v2_phase7 import stage_q_screening_sensitivity as module
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import SupportState

EPOCH_ROOT = C.STAGE_MATCHED_FINAL_TEST_ROOT
ATTENTION_PATH = EPOCH_ROOT / "checkpoints" / "ATTENTION_DECISIONS.json"
#: Resolved from the entrypoint's own candidate list so the test can never drift
#: from where the staged nominal baseline is actually looked for.
NOMINAL_BASELINE = (
    module.NOMINAL_BASELINE_CANDIDATES[0] / module.NOMINAL_BASELINE_NAME
)


def _signal(
    node_id: str,
    score: float,
    *,
    kind: SignalKind,
    episode_id: str | None = None,
) -> PrioritySignal:
    return PrioritySignal(
        signal_type=kind,
        episode_id=episode_id or f"ep-{node_id}",
        chain_id=f"chain-{node_id}",
        node_id=node_id,
        representation_id=C.REFERENCE_REPRESENTATION_ID,
        score=score,
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=1.0,
        comparison_support_threshold=0.9,
    )


def _queue(
    scores: dict[str, tuple[float, float]],
) -> tuple[dict[str, tuple[PrioritySignal, PrioritySignal]], tuple[str, ...]]:
    node_ids = tuple(sorted(scores))
    signals = {
        node_id: (
            _signal(node_id, delay, kind=SignalKind.DELAY),
            _signal(node_id, consequence, kind=SignalKind.CONSEQUENCE),
        )
        for node_id, (delay, consequence) in scores.items()
    }
    return signals, node_ids


def test_capacity_rule_is_ceil_q_n() -> None:
    scores = {f"n{index:02d}": (float(index), float(-index)) for index in range(29)}
    signals, node_ids = _queue(scores)
    for q in module.Q_GRID:
        _, consequence = module.materialize_stage_q_shortlist(
            "PRE_IB", q, frozen_signals=signals, stage_node_ids=node_ids
        )
        assert consequence.cohort_size == 29
        assert consequence.k == math.ceil(q * 29)
        assert sum(entry.selected for entry in consequence.entries) == consequence.k


def test_tie_break_is_score_then_episode_then_node() -> None:
    node_ids = ("bbb", "aaa", "ccc")
    signals = {
        node_id: (
            _signal(node_id, 1.0, kind=SignalKind.DELAY, episode_id=f"ep-{node_id}"),
            _signal(
                node_id, 1.0, kind=SignalKind.CONSEQUENCE, episode_id=f"ep-{node_id}"
            ),
        )
        for node_id in node_ids
    }
    # all scores equal -> (-score, episode_id, node_id) reduces to episode order
    _, consequence = module.materialize_stage_q_shortlist(
        "PRE_IB", 0.30, frozen_signals=signals, stage_node_ids=node_ids
    )
    assert [entry.node_id for entry in consequence.entries] == ["aaa", "bbb", "ccc"]
    assert [entry.rank for entry in consequence.entries] == [1, 2, 3]


def test_shortlists_are_stage_local_and_never_pooled() -> None:
    signals_a, nodes_a = _queue({"p1": (2.0, 1.0), "p2": (1.0, 2.0)})
    signals_b, nodes_b = _queue({"t1": (9.0, 1.0), "t2": (8.0, 2.0), "t3": (7.0, 3.0)})
    merged = dict(signals_a, **signals_b)
    _, pre = module.materialize_stage_q_shortlist(
        "PRE_IB", 0.30, frozen_signals=merged, stage_node_ids=nodes_a
    )
    _, turn = module.materialize_stage_q_shortlist(
        "POST_IB_PRE_OB", 0.30, frozen_signals=merged, stage_node_ids=nodes_b
    )
    # disjoint node sets, and each stage keeps its own capacity denominator
    assert set(nodes_a) & set(nodes_b) == set()
    assert pre.cohort_size == 2 and pre.k == 1
    assert turn.cohort_size == 3 and turn.k == 1
    # the cross-stage top score (t1 = 9.0) must not enter the PRE queue
    assert "t1" not in {entry.node_id for entry in pre.entries}


def test_consequence_shortlist_is_top_k_under_frozen_objective() -> None:
    from model.M4.evaluation import evaluate_attention_allocation

    scores = {
        "n1": (5.0, 0.5),
        "n2": (4.0, 0.4),
        "n3": (3.0, 0.3),
        "n4": (2.0, 0.9),
    }
    signals, node_ids = _queue(scores)
    for q in module.Q_GRID:
        delay, consequence = module.materialize_stage_q_shortlist(
            "PRE_IB", q, frozen_signals=signals, stage_node_ids=node_ids
        )
        priority = {node_id: scores[node_id][1] for node_id in node_ids}
        evaluation = evaluate_attention_allocation(
            cohort_id="synthetic",
            reference_id="consequence",
            comparator_id="delay",
            reference_decision=consequence,
            comparator_decision=delay,
            reference_priority=priority,
        )
        # the consequence shortlist maximises the frozen objective by construction
        assert evaluation.reference_attention_value >= (
            evaluation.comparator_attention_value
        )
        assert evaluation.L_att is not None and evaluation.L_att >= 0.0
        assert (
            evaluation.reference_shortlist
            == tuple(
                node_id
                for node_id in sorted(priority, key=lambda k: (-priority[k], k))[
                    : consequence.k
                ]
            )
        )


# ----------------------------------------------------------------------
# sealed canonical-v2 epoch projection
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def screening_run(tmp_path_factory) -> tuple[dict, Path]:
    if not ATTENTION_PATH.is_file():
        pytest.skip("sealed canonical-v2 epoch not present in this checkout")
    if not NOMINAL_BASELINE.is_file():
        pytest.skip("staged nominal-q baseline not present in this checkout")
    out_dir = tmp_path_factory.mktemp("stage_q_screening")
    module.main(
        ["--epoch-root", str(EPOCH_ROOT), "--out-dir", str(out_dir)]
    )
    manifest = json.loads(
        (out_dir / module.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    return manifest, out_dir


def test_nominal_q_reproduces_canonical_stage1(screening_run) -> None:
    manifest, _ = screening_run
    nominal = manifest["nominal_reproduction_check"]
    assert nominal["pre"]["canonical_match"] is True
    assert nominal["turn"]["canonical_match"] is True
    assert manifest["regression_checks"]["nominal_pre_matches_canonical"] is True
    assert manifest["regression_checks"]["nominal_turn_matches_canonical"] is True
    # published nominal anchors
    assert nominal["pre"]["N_supported"] == 29 and nominal["pre"]["K"] == 3
    assert nominal["pre"]["changed_positions"] == 0
    assert nominal["pre"]["retained_value"] == 1.0
    assert nominal["turn"]["N_supported"] == 127 and nominal["turn"]["K"] == 13
    assert nominal["turn"]["changed_positions"] == 5
    assert nominal["turn"]["retained_value"] == pytest.approx(
        0.9275697132482993, abs=1e-15
    )


def test_cohort_support_and_scores_are_invariant_across_q(screening_run) -> None:
    manifest, out_dir = screening_run
    checks = manifest["regression_checks"]
    assert checks["pre_supported_population_is_constant"] is True
    assert checks["turn_supported_population_is_constant"] is True
    assert checks["support_mask_identical_across_q"] is True
    assert checks["reference_scores_identical_across_q"] is True
    assert checks["delay_scores_identical_across_q"] is True
    assert checks["no_canonical_node_backfill"] is True
    assert checks["pre_and_turn_are_ranked_separately"] is True

    import pandas as pd

    records = pd.read_parquet(out_dir / module.RECORDS_NAME)
    for stage, expected_n in (("PRE_IB", 29), ("POST_IB_PRE_OB", 127)):
        frame = records[records.stage == stage]
        # one frozen score per chain, identical at every q
        for column in ("reference_priority", "delay_score"):
            by_q = frame.groupby("q")[column].apply(lambda s: tuple(s.round(15)))
            assert by_q.nunique() == 1, (stage, column)
        assert frame.groupby("q").size().eq(expected_n).all()


def test_capacity_grid_and_objective_identities(screening_run) -> None:
    manifest, out_dir = screening_run
    import pandas as pd

    summary = pd.read_csv(out_dir / module.SUMMARY_NAME)
    assert sorted(summary.q.unique()) == sorted(module.Q_GRID)
    assert set(summary.stage) == set(module.STAGES)
    for _, row in summary.iterrows():
        assert int(row.K) == math.ceil(row.q * int(row.N_supported))
        assert int(row.intersection_count) + int(row.changed_positions) == int(row.K)
        assert row.overlap_rate == pytest.approx(
            row.intersection_count / row.K, abs=1e-15
        )
        assert row.replacement_rate == pytest.approx(
            row.changed_positions / row.K, abs=1e-15
        )
        assert row.retained_value == pytest.approx(1.0 - row.attention_loss, abs=1e-12)
        assert row.attention_loss >= 0.0
        assert row.delay_shortlist_consequence_value <= (
            row.reference_consequence_value + 1e-12
        )
