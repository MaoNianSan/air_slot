from hashlib import sha256
import json
from pathlib import Path

from model.M1.pipeline import M1Pipeline


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def test_signed_warning_model_artifact_is_frozen_from_first_registered_seed():
    artifact = OUT / "M1_SIGNED_WARNING_MODEL_V1.pt"
    manifest = json.loads(
        (OUT / "M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json").read_text(encoding="utf-8")
    )
    source = ROOT / manifest["source_checkpoint"]
    assert manifest["status"] == "FROZEN"
    assert manifest["artifact_selection_rule"] == "FIRST_PRE_REGISTERED_W_SEED"
    assert manifest["development_metric_not_used_for_seed_selection"] is True
    assert manifest["hidden_size"] == 32
    assert manifest["fixed_history_window_minutes"] == 30
    assert manifest["training_seed"] == 20260813
    assert _hash(source) == _hash(artifact) == manifest["frozen_checkpoint_hash"]
    assert manifest["final_test_access_count"] == 0
    assert manifest["full_development_warning_inference"] == "NOT_RUN"
    assert manifest["paper_full_run"] is False

    pipeline = M1Pipeline.load(artifact)
    assert pipeline.model.hidden_size == 32
    assert set(pipeline.bins) == {"R_IB", "DELTA_OB", "T_TX"}
    assert pipeline.bins["DELTA_OB"].min_finite_minutes == -180
    assert pipeline.bins["DELTA_OB"].max_finite_minutes == 180


def test_warning_probability_manifest_freezes_signed_d_to_contract():
    manifest = json.loads(
        (OUT / "M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json").read_text(encoding="utf-8")
    )
    contract = manifest["warning_probability_contract"]
    assert manifest["target_contract"] == ["R_IB", "DELTA_OB", "T_TX"]
    assert contract["principal_event"] == "D_TO_POST_GT_30"
    assert contract["strict_operator"] == ">"
    assert contract["delay_threshold_minutes"] == 30
    assert contract["missing_taxi_reference"] == "ABSTAIN"
