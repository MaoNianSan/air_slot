"""The current-stage positive-tail decision remains an explicit human gate."""

import json
from pathlib import Path

from exp.m1_v2_current_stage_positive_tail_decision_packet import (
    create_current_stage_positive_tail_packet,
)


ROOT = Path(__file__).resolve().parents[2]


def test_current_stage_positive_tail_packet_blocks_scenarios(tmp_path):
    packet_path = create_current_stage_positive_tail_packet(root=ROOT, output_root=tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["status"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED"
    assert packet["cohort"]["cohort_hash"] == "sha256:81f9ee2dcfa81bb9d72e5a1518f386295a63829c179d25bd6cb84e333a35b7a8"
    assert packet["configured_policy"]["value"] == "UNRESOLVED"
    assert packet["configured_policy"]["checkpoint_contract_policies"] == {
        "D_OB": "UNRESOLVED",
        "D_TX": "UNRESOLVED",
    }
    envelope = packet["scenario_envelope"]
    assert envelope["joint_state_distribution_artifact"] == "BLOCKED"
    assert envelope["marginal_distribution_artifact"] == "BLOCKED_FOR_SCENARIO_DERIVATION"
    assert "Exp2_4_metric_generation" in envelope["prohibited_without_human_decision"]
    assert packet["no_automatic_fallback"] is True
    assert packet["FINAL_TEST_ACCESS_COUNT"] == 0
    assert packet["PAPER_FULL_RUN"] is False
    assert packet["FULL"] is False

