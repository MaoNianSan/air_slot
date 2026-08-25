from datetime import datetime

import pytest
from pydantic import ValidationError

from exp.common.result_schema import ExperimentResult


def test_result_schema_json_round_trip_and_stable_hash(common_result):
    encoded = common_result.model_dump_json()
    restored = ExperimentResult.model_validate_json(encoded)

    assert restored == common_result
    assert restored.timestamp.tzinfo is not None
    assert restored.result_hash == common_result.result_hash
    assert restored.metrics["STATE_CRPS"].value is None


def test_result_schema_rejects_naive_timestamp_and_metric_key_mismatch(common_result):
    payload = common_result.model_dump(mode="python")
    payload["timestamp"] = datetime(2026, 8, 20, 8, 0)
    with pytest.raises(ValidationError, match="TIMESTAMP_TIMEZONE_REQUIRED"):
        ExperimentResult.model_validate(payload)

    payload = common_result.model_dump(mode="python")
    payload["metrics"] = {"WRONG_KEY": common_result.metrics["STATE_CRPS"]}
    with pytest.raises(ValidationError, match="METRIC_KEY_MISMATCH"):
        ExperimentResult.model_validate(payload)


def test_result_schema_requires_explicit_hashes(common_result):
    payload = common_result.model_dump(mode="python")
    payload["scenario_hash"] = "UNSET"
    with pytest.raises(ValidationError):
        ExperimentResult.model_validate(payload)

