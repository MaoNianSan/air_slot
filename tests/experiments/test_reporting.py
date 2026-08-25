import csv
import json

import pytest

from exp.common.reporting import ExperimentReporter


def test_reporter_writes_json_csv_and_summary_with_lineage(tmp_path, common_result):
    paths = ExperimentReporter().write_bundle(common_result, tmp_path / "report")

    restored = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert restored["experiment_id"] == common_result.experiment_id
    assert restored["variant_id"] == common_result.variant_id
    assert restored["artifact_versions"] == common_result.artifact_versions

    with paths["csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["experiment_id"] == common_result.experiment_id
    assert rows[0]["variant_id"] == common_result.variant_id
    assert json.loads(rows[0]["artifact_lineage"]) == common_result.artifact_versions

    summary = paths["summary"].read_text(encoding="utf-8")
    assert common_result.experiment_id in summary
    assert common_result.variant_id in summary
    assert "M1_SCENARIOS" in summary


def test_reporter_rejects_overwrite(tmp_path, common_result):
    reporter = ExperimentReporter()
    path = tmp_path / "result.json"
    reporter.write_json(common_result, path)
    with pytest.raises(FileExistsError, match="OVERWRITE_REJECTED"):
        reporter.write_json(common_result, path)
