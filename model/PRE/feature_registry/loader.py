import json
from hashlib import sha256
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, ConfigDict

from model.common.errors import RegistryError
from model.common.identity import content_id
from .models import (
    DataUsageRule,
    DatasetCapabilityProfile,
    RegistryFileIdentity,
    RegistryManifest,
    ScientificVariableDefinition,
    SourcePriorityEntry,
)


class RegistryBundle(BaseModel):
    model_config = ConfigDict(frozen=True)
    data_usage_rules: tuple[DataUsageRule, ...]
    scientific_variables: tuple[ScientificVariableDefinition, ...]
    capability_profiles: tuple[DatasetCapabilityProfile, ...]
    source_priorities: tuple[SourcePriorityEntry, ...]
    manifest: RegistryManifest


_FILES = (
    "data_usage_rules.yaml",
    "scientific_variables.yaml",
    "dataset_capabilities.yaml",
    "source_priority.yaml",
)


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_registry_bundle(
    root: Path, *, validate_published: bool = True
) -> RegistryBundle:
    try:
        paths = [root / name for name in _FILES]
        if any(not p.is_file() for p in paths):
            raise RegistryError("required registry missing")
        rules = tuple(DataUsageRule.model_validate(x) for x in _yaml(paths[0])["rules"])
        variables = tuple(
            ScientificVariableDefinition.model_validate(x)
            for x in _yaml(paths[1])["variables"]
        )
        profiles = tuple(
            DatasetCapabilityProfile.model_validate(x)
            for x in _yaml(paths[2])["profiles"]
        )
        priorities = tuple(
            SourcePriorityEntry.model_validate(x) for x in _yaml(paths[3])["priorities"]
        )
        ids = tuple(
            RegistryFileIdentity(
                path=f"registries/{p.name}",
                sha256=f"sha256:{sha256(p.read_bytes()).hexdigest()}",
            )
            for p in paths
        )
        manifest = RegistryManifest(
            manifest_version="1.0.0",
            registries=ids,
            combined_sha256=content_id([x.model_dump(mode="json") for x in ids]),
            validation_status="PASS",
        )
        published_path = root / "registry_manifest.json"
        if validate_published and published_path.is_file():
            published = RegistryManifest.model_validate_json(
                published_path.read_text(encoding="utf-8")
            )
            if published != manifest:
                raise RegistryError("published registry manifest mismatch")
        rule_ids = {r.rule_id for r in rules}
        if len(rule_ids) != len(rules):
            raise RegistryError("duplicate rule_id")
        canonical = {r.canonical_variable for r in rules}
        for variable in variables:
            missing = set(variable.canonical_inputs) - canonical
            if missing:
                raise RegistryError(f"missing canonical inputs: {sorted(missing)}")
        for priority in priorities:
            if set(priority.rule_ids) - rule_ids:
                raise RegistryError("priority references unknown rule")
        consumers = {"PRE", "M1", "M2", "M3", "EXP3", "EVALUATION_ONLY"}
        for rule in rules:
            if not set(rule.downstream_consumers) <= consumers:
                raise RegistryError("raw-to-consumer boundary violation")
            if rule.source_rule_id and rule.source_rule_id not in rule_ids:
                raise RegistryError("projection references unknown source rule")
        # A variable may depend only on previously declared variables, preventing cycles.
        declared: set[str] = set()
        for variable in variables:
            dependencies = set(variable.upstream_variables)
            if not dependencies <= declared:
                raise RegistryError(
                    f"unknown or cyclic upstream variable: {sorted(dependencies - declared)}"
                )
            declared.add(variable.scientific_variable)
        return RegistryBundle(
            data_usage_rules=rules,
            scientific_variables=variables,
            capability_profiles=profiles,
            source_priorities=priorities,
            manifest=manifest,
        )
    except RegistryError:
        raise
    except Exception as exc:
        raise RegistryError(str(exc)) from exc


def write_manifest(root: Path) -> RegistryManifest:
    bundle = load_registry_bundle(root, validate_published=False)
    (root / "registry_manifest.json").write_text(
        json.dumps(bundle.manifest.model_dump(mode="json"), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return bundle.manifest
