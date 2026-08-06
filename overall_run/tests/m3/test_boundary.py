from __future__ import annotations

import inspect

from src.m3 import generate_m3_library
from src.m3.artifact import M3Artifact


def test_m3_generator_has_no_episode_or_downstream_inputs() -> None:
    parameters = inspect.signature(generate_m3_library).parameters
    forbidden = {"episode_id", "m1_prediction", "m2_loss_value", "m4_ranking", "sample_id"}
    assert forbidden.isdisjoint(parameters)


def test_m3_artifact_uses_response_draw_identity() -> None:
    fields = set(M3Artifact.__dataclass_fields__)
    assert "response_draw_ids" in fields
    assert "sample_ids" not in fields
