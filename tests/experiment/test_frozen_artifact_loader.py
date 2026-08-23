from pathlib import Path

import pytest

from exp.common.frozen_artifact_loader import load_current_development_binding
from exp.common.lineage import build_formal_lineage


ROOT = Path(__file__).resolve().parents[2]


def test_current_development_binding_is_hash_complete():
    binding = load_current_development_binding(ROOT)
    values = binding.as_dict()
    assert set(values) == {
        "model_hash", "schema_hash", "cohort_hash", "scenario_hash",
        "support_hash", "m2_hash", "mapping_hash", "risk_policy_hash",
    }
    assert all(value.startswith("sha256:") for value in values.values())


def test_formal_lineage_rejects_unbound_hashes():
    with pytest.raises(Exception):
        build_formal_lineage(experiment="EXP2", variant="EXP2A_JOINT", hashes={})
