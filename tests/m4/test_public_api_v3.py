import subprocess
import sys


def test_current_m4_package_does_not_export_legacy_risk_names():
    code = (
        "import model.M4 as m; "
        "assert 'evaluate_residual_risk' not in vars(m); "
        "assert 'RiskEvaluationEnvelope' not in vars(m); "
        "assert 'M4Service' in vars(m)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
