from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath

from validation.portability import canonical_relative_path, runtime_fingerprint


def test_paths_utc_utf8_and_runtime_fingerprint_are_portable():
    assert canonical_relative_path(PureWindowsPath("metadata\\datasets\\data1")) == "metadata/datasets/data1"
    assert canonical_relative_path(PurePosixPath("metadata/datasets/data2")) == "metadata/datasets/data2"
    fingerprint = runtime_fingerprint()
    assert set(fingerprint) == {"python_version", "package_versions", "platform", "device"}
    assert "environment" not in fingerprint
    assert datetime(2019, 1, 1, tzinfo=timezone.utc).isoformat().endswith("+00:00")
    assert "航班".encode("utf-8").decode("utf-8") == "航班"
