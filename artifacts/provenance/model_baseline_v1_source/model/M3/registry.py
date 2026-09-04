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
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from .contracts import ActionTemplate

# Active model library: exactly these 23 templates. Additional templates require
# a new versioned model freeze and cannot enter this registry implicitly.
PRINCIPAL_IDS = (
    "A00",
    "A11",
    "A13",
    "A21",
    "A22",
    "A23",
    "A31",
    "A32",
    "A33",
    "A41",
    "A42",
    "A43",
    "A51",
    "A52",
    "A53",
    "A54",
    "A55",
    "A61",
    "A62",
    "A63",
    "A64",
    "A71",
    "A72",
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
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        # Footprint roles/levels are registry-owned structural metadata. Keep
        # them alongside the compact template rows while materializing the
        # typed field consumed by M3.
        footprints = payload.pop("footprints", {}) or {}
        for template in payload.get("templates", []):
            template["footprint"] = footprints.get(template["template_id"], {})
        registry = cls.model_validate(payload)
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

    def numerical_readiness(self, *, response_registry=None):
        """Return action-level numerical completeness for the active catalog."""
        from .readiness import build_action_numerical_readiness

        return build_action_numerical_readiness(
            self,
            response_registry=response_registry,
        )

    def numerical_readiness_for(self, action_id: str, *, response_registry=None):
        """Return one action's numerical readiness record."""
        from .readiness import readiness_for_action

        return readiness_for_action(
            self,
            action_id,
            response_registry=response_registry,
        )

    def numerical_readiness_payload(self, *, response_registry=None) -> dict:
        """Build the deterministic ``M3_ACTION_NUMERICAL_READINESS`` payload."""
        records = self.numerical_readiness(response_registry=response_registry)
        payload = {
            "artifact_id": "M3_ACTION_NUMERICAL_READINESS",
            "schema_version": "M3_ACTION_NUMERICAL_READINESS_V1",
            "action_registry_id": self.registry_id,
            "action_registry_hash": self.digest(),
            "response_registry_id": (
                response_registry.registry_id if response_registry is not None else None
            ),
            "response_registry_hash": (
                response_registry.digest() if response_registry is not None else None
            ),
            "final_test_access_count": 0,
            "experiment_created": False,
            "model_retrained": False,
            "actions": [item.model_dump(mode="json") for item in records],
            "counts": {
                "structural_actions": len(records),
                "numerically_complete_actions": sum(
                    item.chi_num_possible_if_state_complete for item in records
                ),
                "numerically_partial_actions": sum(
                    bool(item.missing_response_cells) for item in records
                ),
                "missing_response_cells": sum(
                    len(item.missing_response_cells) for item in records
                ),
            },
        }
        payload["artifact_hash"] = content_id(payload)
        return payload

    def write_numerical_readiness(
        self,
        output_path: Path,
        *,
        response_registry=None,
        overwrite: bool = False,
    ) -> Path:
        """Atomically write the readiness payload without implicit overwrites."""
        if output_path.exists() and not overwrite:
            raise RegistryError("M3_ACTION_NUMERICAL_READINESS_EXISTS")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.numerical_readiness_payload(response_registry=response_registry)
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

    def write_manifest(self, output_path: Path, *, overwrite: bool = False) -> Path:
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
    def exact_principal_registry(self):
        ids = tuple(item.template_id for item in self.templates)
        if len(ids) != len(set(ids)):
            raise RegistryError("DUPLICATE_ACTION_ID")
        if self.enforce_principal_ids and ids != PRINCIPAL_IDS:
            raise RegistryError("PRINCIPAL_ACTION_EXACT_SET_MISMATCH")
        if self.enforce_principal_ids:
            for template in self.templates:
                if tuple(template.footprint) != CONSEQUENCE_COMPONENTS:
                    raise RegistryError(
                        f"ACTION_FOOTPRINT_EXACT_SEVEN_COMPONENTS_REQUIRED:{template.template_id}"
                    )
        return self

    @model_validator(mode="after")
    def source_hash_consistent(self):
        if self.registry_hash and self.registry_hash != self.digest():
            raise RegistryError("ACTION_REGISTRY_HASH_MISMATCH")
        if self.source_sha256 and not self.source_sha256.startswith("sha256:"):
            raise RegistryError("ACTION_REGISTRY_SOURCE_HASH_INVALID")
        return self
