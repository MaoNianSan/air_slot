import pytest

from exp.workflows.m1_v2_positive_tail_decision_packet import _safety


def test_positive_tail_packet_rejects_final_test_access():
    with pytest.raises(RuntimeError, match="FINAL_TEST_ACCESS_NONZERO"):
        _safety({"FINAL_TEST_ACCESS_COUNT": 1, "PAPER_FULL_RUN": False}, "TEST")


def test_positive_tail_packet_rejects_full_run():
    with pytest.raises(RuntimeError, match="FULL_TRUE"):
        _safety({"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "FULL": True}, "TEST")
