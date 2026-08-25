"""The current-stage positive-tail decision remains an explicit human gate."""

import json
from pathlib import Path

from exp.workflows.m1_v2_current_stage_positive_tail_decision_packet import (
    create_current_stage_positive_tail_packet,
)


ROOT = Path(__file__).resolve().parents[2]


def test_current_stage_positive_tail_packet_blocks_scenarios(tmp_path):
    packet_path = create_current_stage_positive_tail_packet(root=ROOT, output_root=tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["status"] == "M1_POSITIVE_TAIL_POLICY_FROZEN"
    assert packet["configured_policy"]["value"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    assert packet["configured_policy"]["target_q_max_minutes"] == {
        "T_IB_A00": 360, "D_OB": 210, "D_TX": 60,
    }
    assert packet["configured_policy"]["representation"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    envelope = packet["scenario_envelope"]
    assert envelope["joint_state_distribution_artifact"] == "BLOCKED"
    assert envelope["marginal_distribution_artifact"] == "BLOCKED_FOR_SCENARIO_DERIVATION"
    assert "Exp2_4_metric_generation" in envelope["prohibited_without_human_decision"]
    assert packet["human_decision_required"] == []
    assert packet["no_automatic_fallback"] is True
    assert packet["FINAL_TEST_ACCESS_COUNT"] == 0
    assert packet["PAPER_FULL_RUN"] is False
    assert packet["FULL"] is False
