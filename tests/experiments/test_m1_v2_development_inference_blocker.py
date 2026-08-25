from pathlib import Path

from exp.workflows.m1_v2_development_inference_blocker import materialize_blocker_report


def test_blocker_report_is_content_addressed(tmp_path: Path):
    root = tmp_path
    files = {
        "artifacts/experiment/exp2/DATA2_DEVELOPMENT_PILOT_COHORT.json": {"config_hash": "sha256:old", "git_sha": "deadbeef", "node_ids": ["n1"]},
        "artifacts/diagnostics/exp1_formal_execution_preparation/EXP1_M1_V2_ARTIFACT_BINDING.json": {"frozen_contracts": {"feature_schema_hash": "sha256:feature"}},
        "artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2_MANIFEST.json": {"cache_hash": "sha256:cache", "partition_counts": {"development": 1769}},
        "artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt": {"x": 1},
    }
    for relative, payload in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            import json
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"checkpoint")
    # Supply the config files consumed by config_hash.
    for relative in ("configs/scientific/foundation.yaml", "configs/reproducibility/smoke.yaml", "configs/engineering/local.example.yaml"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x: 1\n", encoding="utf-8")
    output = materialize_blocker_report(root=root)
    payload = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED_M1_COHORT_CONFIG_PROVENANCE_UNRESOLVED"
    assert payload["FINAL_TEST_ACCESS_COUNT"] == 0
    assert payload["artifact_hash"].startswith("sha256:")
