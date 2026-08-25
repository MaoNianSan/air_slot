from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel


class FormalDecisionNodeArtifact(FrozenModel):
    episode_id: str
    decision_node_id: str
    decision_time: str
    information_cutoff: str
    PRE_contract_hash: str
    M1_model_hash: str
    M1_scenario_hash: str
    M2_contract_hash: str
    M3_registry_hash: str
    M4_config_hash: str
    global_seed: int
    pre_state: dict[str, Any] = {}
    m1_scenarios: tuple[dict[str, Any], ...] = ()
    m2_consequences: tuple[dict[str, Any], ...] = ()
    m3_actions: tuple[dict[str, Any], ...] = ()
    m4_decision: dict[str, Any] = {}
    formal_output_hash: str = ""
    artifact_layer: str = "FORMAL"
    immutable: bool = True

    def with_hash(self) -> "FormalDecisionNodeArtifact":
        payload = self.model_dump(mode="json", exclude={"formal_output_hash"})
        return self.model_copy(update={"formal_output_hash": content_id(payload)})


class FormalArtifactBundle(FrozenModel):
    artifact_layer: str = "FORMAL"
    immutable: bool = True
    schema_version: str = "V5.0"
    dataset_instance_id: str = "data2_2019"
    global_seed: int = 0
    nodes: tuple[FormalDecisionNodeArtifact, ...]
    bundle_hash: str = ""

    def with_hash(self) -> "FormalArtifactBundle":
        payload = self.model_dump(mode="json", exclude={"bundle_hash"})
        return self.model_copy(update={"bundle_hash": content_id(payload)})


def write_formal_bundle(
    path: Path, bundle: FormalArtifactBundle, *, overwrite: bool = False
) -> Path:
    """Write once by default; evaluation code must not overwrite formal artifacts."""
    if path.exists() and not overwrite:
        raise ContractError("FORMAL_ARTIFACT_IMMUTABLE_OVERWRITE")
    if bundle.artifact_layer != "FORMAL" or bundle.immutable is not True:
        raise ContractError("FORMAL_ARTIFACT_LAYER_INVALID")
    normalized_nodes = tuple(node.with_hash() for node in bundle.nodes)
    normalized = bundle.model_copy(update={"nodes": normalized_nodes}).with_hash()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_formal_bundle(path: Path) -> FormalArtifactBundle:
    if not path.is_file():
        raise ContractError("FROZEN_FORMAL_ARTIFACT_MISSING")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("artifact_layer") != "FORMAL"
        or payload.get("immutable") is not True
    ):
        raise ContractError("FORMAL_ARTIFACT_NOT_IMMUTABLE")
    bundle = FormalArtifactBundle.model_validate(payload)
    if bundle.with_hash().bundle_hash != bundle.bundle_hash:
        raise ContractError("FORMAL_ARTIFACT_HASH_MISMATCH")
    for node in bundle.nodes:
        if node.with_hash().formal_output_hash != node.formal_output_hash:
            raise ContractError("FORMAL_NODE_HASH_MISMATCH")
    return bundle
