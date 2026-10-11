from pathlib import Path

from exp.jatm_s34.e4_development import run


def test_e4_preflight_is_fail_closed_and_keeps_test_blocked(tmp_path):
    result = run(root=Path.cwd(), output_root=tmp_path)
    assert result["status"] == "ENGINEERING_INCOMPLETE"
    assert len(result["years"]) == 6
    assert all(row["pre_status"] == "PRE_DEVELOPMENT_READY" for row in result["years"])
    assert all(row["test_status"] == "BLOCKED_TEST_ACCESS" for row in result["years"])
    assert result["fixed_common"]["status"] == "READY_AUDITED_2017_H1"
