import json
from pathlib import Path

import pytest

from model.M3.registry_layer.actions import ActionRegistry
from model.common.errors import RegistryError


def test_shipped_action_registry_has_stable_source_and_content_hashes():
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert registry.registry_hash.startswith("sha256:")
    assert len(registry.registry_hash) == 71
    assert registry.source_sha256.startswith("sha256:")
    assert registry.digest() == registry.registry_hash
    assert len(registry.templates) == 23
    assert sum(
        item.response_parameter_status.value == "NOT_FROZEN"
        for item in registry.templates
    ) == 22


def test_action_registry_manifest_is_atomic_and_write_once(tmp_path):
    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    output = tmp_path / "m3_action_registry_manifest.json"
    registry.write_manifest(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registry_hash"] == registry.digest()
    assert payload["final_test_access_count"] == 0
    assert len(payload["template_ids"]) == 23
    with pytest.raises(RegistryError, match="ACTION_REGISTRY_MANIFEST_EXISTS"):
        registry.write_manifest(output)
