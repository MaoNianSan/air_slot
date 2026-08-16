from pathlib import Path
import pytest
from model.common.errors import RegistryError
from model.PRE.feature_registry.loader import load_registry_bundle
import json
import shutil


def test_shipped_registries_have_reproducible_manifest():
    bundle = load_registry_bundle(Path("registries"))
    assert bundle.manifest.combined_sha256.startswith("sha256:")
    assert all("M4" not in r.downstream_consumers for r in bundle.data_usage_rules)


def test_missing_registry_is_rejected(tmp_path: Path):
    with pytest.raises(RegistryError): load_registry_bundle(tmp_path)


def test_published_manifest_mismatch_is_rejected(tmp_path: Path):
    for path in Path("registries").iterdir():
        if path.is_file(): shutil.copy2(path, tmp_path / path.name)
    manifest = json.loads((tmp_path / "registry_manifest.json").read_text(encoding="utf-8"))
    manifest["combined_sha256"] = "sha256:" + "0" * 64
    (tmp_path / "registry_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RegistryError, match="manifest mismatch"):
        load_registry_bundle(tmp_path)
