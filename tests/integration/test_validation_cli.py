import json
import subprocess
import sys
import time


def test_all_fixture_validation_cli_is_offline_fast_and_successful():
    started = time.monotonic()
    completed = subprocess.run([sys.executable, "-m", "validation.cli", "all", "--fixtures-only"],
        text=True, capture_output=True, check=False, timeout=60)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["summary"]["FAIL"] == 0
    assert time.monotonic() - started < 60
