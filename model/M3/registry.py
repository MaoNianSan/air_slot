from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile

import yaml
from pydantic import model_validator
from model.common.errors import RegistryError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel
from .contracts import ActionTemplate

# Principal/current library (manuscript): the 23 templates are required but the
# action universe is not a closed set; extra structural actions are allowed and
# must satisfy the full Gamma_a contract (Round 2, spec 6.1).
PRINCIPAL_IDS = (
    "A00", "A11", "A13", "A21", "A22", "A23", "A31", "A32", "A33",
    "A41", "A42", "A43", "A51", "A52", "A53", "A54", "A55",
    "A61", "A62", "A63", "A64", "A71", "A72",
)

class ActionRegistry(FrozenModel):
    schema_version: str
    templates: tuple[ActionTemplate, ...]
    enforce_principal_ids: bool = True
    registry_id: str = "ACTION_TEMPLATES_V1"
    source_path: str = ""
    source_sha256: str = ""
    registry_hash: str = ""

    @classmethod
    def load(cls, path: Path):
        registry = cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        return registry.model_copy(
            update={
                "registry_id": "ACTION_TEMPLATES_V1",
                "source_path": str(path),
                "source_sha256": f"sha256:{sha256(path.read_bytes()).hexdigest()}",
                "registry_hash": registry.digest(),
            }
        )

    def registry_payload(self) -> dict:
        return {
            "registry_id": self.registry_id,
            "schema_version": self.schema_version,
            "templates": [item.model_dump(mode="json") for item in self.templates],
        }

    def digest(self) -> str:
        return content_id(self.registry_payload())

    def write_manifest(
        self, output_path: Path, *, overwrite: bool = False
    ) -> Path:
        if output_path.exists() and not overwrite:
            raise RegistryError("ACTION_REGISTRY_MANIFEST_EXISTS")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest_version": "1.0.0",
            "registry_id": self.registry_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "registry_hash": self.digest(),
            "schema_version": self.schema_version,
            "template_ids": tuple(item.template_id for item in self.templates),
            "unfrozen_response_parameter_templates": tuple(
                item.template_id
                for item in self.templates
                if item.response_parameter_status.value == "NOT_FROZEN"
            ),
            "final_test_access_count": 0,
        }
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=str(output_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, output_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return output_path

    @model_validator(mode="after")
    def principal_subset_registry(self):
        ids=tuple(item.template_id for item in self.templates)
        if len(ids)!=len(set(ids)): raise RegistryError("DUPLICATE_ACTION_ID")
        if self.enforce_principal_ids and not set(PRINCIPAL_IDS) <= set(ids):
            raise RegistryError("PRINCIPAL_ACTION_SUBSET_MISMATCH")
        return self

    @model_validator(mode="after")
    def source_hash_consistent(self):
        if self.registry_hash and self.registry_hash != self.digest():
            raise RegistryError("ACTION_REGISTRY_HASH_MISMATCH")
        if self.source_sha256 and not self.source_sha256.startswith("sha256:"):
            raise RegistryError("ACTION_REGISTRY_SOURCE_HASH_INVALID")
        return self
