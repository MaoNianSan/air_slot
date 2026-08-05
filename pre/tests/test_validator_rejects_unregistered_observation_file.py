from __future__ import annotations

import pandas as pd

from core_v2_bundle_fixture import build_synthetic_bundle
from src.core.validation import validate_existing_bundle


def test_validator_rejects_unregistered_observation_file(tmp_path) -> None:
    bundle = build_synthetic_bundle(tmp_path)
    extra = tmp_path / "observations/source=weather/observation_date=2022-05-02/extra.parquet"
    pd.read_parquet(bundle["observation_path"]).to_parquet(extra, index=False)
    result = validate_existing_bundle(tmp_path, bundle["cfg"], write_report=False)
    assert result["status"] == "FAIL"
    assert result["extra_unregistered_files"]["observations"]
