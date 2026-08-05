from __future__ import annotations

import pandas as pd

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.existing_bundle_validator import validate_existing_bundle


def test_validator_rejects_unregistered_membership_file(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path)
    extra = tmp_path / "observation_membership/source=weather/observation_date=2022-05-02/extra.parquet"
    pd.read_parquet(bundle["membership_path"]).to_parquet(extra, index=False)
    result = validate_existing_bundle(tmp_path, bundle["cfg"], write_report=False)
    assert result["status"] == "FAIL"
    assert result["extra_unregistered_files"]["observation_membership"]
