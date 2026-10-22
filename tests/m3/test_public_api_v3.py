import subprocess
import sys


def test_current_m3_package_does_not_export_legacy_action_names():
    code = (
        "import model.M3 as m; "
        "assert 'ActionRegistry' not in vars(m); "
        "assert 'ActionEvaluationEnvelope' not in vars(m); "
        "assert 'M3Service' in vars(m)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
