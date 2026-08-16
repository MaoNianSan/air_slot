from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from model.common.identity import content_id

from .artifacts import FormalArtifactBundle, FormalDecisionNodeArtifact


def _text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def run_formal_pipeline(nodes: Iterable[Mapping[str, Any]], *, dataset_instance_id: str = "data2_2019",
                        global_seed: int = 0, contract_hashes: Mapping[str, str] | None = None,
                        output_path=None) -> FormalArtifactBundle:
    """Materialize one frozen formal PRE-M4 bundle from already-typed node outputs.

    The function deliberately accepts prepared typed boundaries rather than raw rows. It is a
    reusable artifactization boundary for the real PRE-M4 runner and for tiny contract fixtures.
    """
    hashes = dict(contract_hashes or {})
    artifacts = []
    for row in nodes:
        node = FormalDecisionNodeArtifact(
            episode_id=str(row["episode_id"]),
            decision_node_id=str(row["decision_node_id"]),
            decision_time=_text(row["decision_time"]),
            information_cutoff=_text(row["information_cutoff"]),
            PRE_contract_hash=hashes.get("PRE_contract_hash", content_id(row.get("pre_state", {}))),
            M1_model_hash=hashes.get("M1_model_hash", content_id(row.get("m1_model", {}))),
            M1_scenario_hash=hashes.get("M1_scenario_hash", content_id(row.get("m1_scenarios", ()))),
            M2_contract_hash=hashes.get("M2_contract_hash", content_id(row.get("m2_contract", {}))),
            M3_registry_hash=hashes.get("M3_registry_hash", content_id(row.get("m3_registry", {}))),
            M4_config_hash=hashes.get("M4_config_hash", content_id(row.get("m4_config", {}))),
            global_seed=int(row.get("global_seed", global_seed)),
            pre_state=dict(row.get("pre_state", {})),
            m1_scenarios=tuple(row.get("m1_scenarios", ())),
            m2_consequences=tuple(row.get("m2_consequences", ())),
            m3_actions=tuple(row.get("m3_actions", ())),
            m4_decision=dict(row.get("m4_decision", {})),
        ).with_hash()
        artifacts.append(node)
    bundle = FormalArtifactBundle(
        dataset_instance_id=dataset_instance_id,
        global_seed=global_seed,
        nodes=tuple(artifacts),
    ).with_hash()
    if output_path is not None:
        from .artifacts import write_formal_bundle
        write_formal_bundle(output_path, bundle)
    return bundle
