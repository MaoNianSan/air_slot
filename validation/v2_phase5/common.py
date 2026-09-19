"""Phase 5 authorities, guard rails and paper-primary adapters.

Authority chain for Phase 5:

- manuscript ZIP ``Rolling_Airline_Recovery (20).zip`` (body text authoritative);
- instruction ``docs/AirSlot_V2_Instruction_rev2_20260918.md`` (unique engineering
  instruction, exact enumeration is the formal Stage-II path);
- ``artifacts/models/m1/M1_H16_HISTORY_PRIMARY`` History+Joint reference model;
- ``M2_DATA2_FORMAL_CU_V5`` consequence-unit registry.

Nothing in this module reads ``artifacts/experiment/final_test``; every path is
checked by :func:`assert_development_path` before use.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.M1.cache import M1DevelopmentBaseCache
from model.M1.development_training import _load_references
from model.M2.comparison_support import (
    ComparisonSupport,
    ComparisonSupportRule,
    build_comparison_support,
    expected_cu_vector,
)
from model.M2.consequence_service import (
    ConsequenceReferenceBinding,
    M2ConsequenceService,
)
from model.M2.context import (
    AirportReferenceKeys,
    M2ReferenceBundle,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
)
from model.M2.cu.registry import M2Data2FormalCuRegistry
from model.M2.scientific_registry import load_active_v2_cu_registry
from model.common.decision_contracts import (
    ConsequenceScenario,
    ConsequenceScenarioSet,
    HistoryScope,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE_DIR = PROJECT_ROOT / "artifacts" / "diagnostics" / "v2_phase5_development"
MODEL_ROOT = PROJECT_ROOT / "artifacts" / "models" / "m1"
H16_ROOT = MODEL_ROOT / "M1_H16_HISTORY_PRIMARY"
H16_MANIFEST = H16_ROOT / "M1_H16_HISTORY_PRIMARY_MANIFEST.json"
H16_CHECKPOINT = H16_ROOT / "M1_H16_HISTORY_PRIMARY.pt"
CURRENT_ROOT = MODEL_ROOT / "M1_H16_CURRENT_COMPARATOR"
CURRENT_MANIFEST = CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR_MANIFEST.json"
CURRENT_CHECKPOINT = CURRENT_ROOT / "M1_H16_CURRENT_COMPARATOR.pt"
H8_ROOT = MODEL_ROOT / "M1_V2_PHASE5_H8_SENSITIVITY"
H8_MANIFEST = H8_ROOT / "M1_V2_PHASE5_H8_SENSITIVITY_MANIFEST.json"
H8_CHECKPOINT = H8_ROOT / "M1_V2_PHASE5_H8_SENSITIVITY.pt"
COHORT_PATH = MODEL_ROOT / "M1_FORMAL_TRAINING_COHORT_V1.json"
SOURCE_CACHE_ROOT = MODEL_ROOT / "M1_FROZEN_H16"
SOURCE_CACHE = SOURCE_CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
SOURCE_CACHE_MANIFEST = (
    SOURCE_CACHE_ROOT / "DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
)
TAIL_MANIFEST = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_positive_tail_continuation_v1"
    / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
)
REGISTRY_V5_PATH = PROJECT_ROOT / "registries" / "m2_data2_formal_cu_v5.json"
INSTRUCTION_PATH = PROJECT_ROOT / "docs" / "AirSlot_V2_Instruction_rev2_20260918.md"
CORRECTED_TURNAROUND_REFERENCE_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "m1_v2_data_gate_a2"
    / "DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
)
SUPERSEDED_TURNAROUND_REFERENCE_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "v5_development_freeze"
    / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json"
)
PASSENGER_DESIGN_V5_PATH = (
    PROJECT_ROOT / "registries" / "m2_v5_passenger_consequence_design.json"
)

EXP2_DEVELOPMENT_ROOT = (
    PROJECT_ROOT / "artifacts" / "experiment" / "exp2" / "development"
)
JOINT_SOURCE_PATH = EXP2_DEVELOPMENT_ROOT / "data" / "EXP2_COMMON_SUPPORT.parquet"
NODE_INPUT_PATH = (
    EXP2_DEVELOPMENT_ROOT / "data" / "EXP2_H16_M2_V4_NODE_INPUT.parquet"
)

FINAL_TEST_ROOT = PROJECT_ROOT / "artifacts" / "experiment" / "final_test"

SCENARIO_COUNT = 64
DEVELOPMENT_NODE_COUNT = 1769
DEVELOPMENT_EPISODES = 128
COMMON_SUPPORT_THRESHOLD = 0.90
ITINERARY_THRESHOLD_MINUTES = 45.0
SERVICE_THRESHOLD_MINUTES = 180.0
TRAIN_MONTHS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
PRIMARY_TRAINING_SEED = 20260813

MISSING = "MISSING"
UNSUPPORTED = "UNSUPPORTED"

#: Fields carried by the binding contract but never used by the seven frozen
#: native formulas. Recorded so that a "0.0" default is never read as evidence.
INERT_BINDING_FIELDS: tuple[str, ...] = ("taxi_reference_minutes",)


class Phase5GuardError(RuntimeError):
    """Raised when a Phase 5 guard rail would be violated."""


def file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    target = assert_development_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def assert_development_path(path: Path) -> Path:
    """Fail closed on any Final-Test path, resolving symlinks first."""

    resolved = Path(path).resolve()
    final_test = FINAL_TEST_ROOT.resolve()
    if resolved == final_test or final_test in resolved.parents:
        raise Phase5GuardError(f"PHASE5_FINAL_TEST_PATH_FORBIDDEN:{resolved}")
    return resolved


def support_of(*supports: str | SupportState) -> SupportState:
    """Combine coordinate supports: any ABSTAIN wins, then DEGRADED."""

    resolved = {as_support_state(value) for value in supports}
    if SupportState.ABSTAIN in resolved:
        return SupportState.ABSTAIN
    if SupportState.DEGRADED in resolved:
        return SupportState.DEGRADED
    return SupportState.SUPPORTED


def as_support_state(value: Any) -> SupportState:
    """Coerce enum, enum-repr and plain-string supports to ``SupportState``."""

    if isinstance(value, SupportState):
        return value
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return SupportState(text)
def representation_spec(
    temporal: TemporalKind,
    uncertainty: UncertaintyKind,
    *,
    history_capacity: int | None = 16,
    history_scope: HistoryScope | None = HistoryScope.FULL_PREFIX,
) -> StateRepresentationSpec:
    if temporal is TemporalKind.CURRENT:
        return StateRepresentationSpec(
            temporal=temporal,
            uncertainty=uncertainty,
            history_capacity=None,
            history_scope=None,
        )
    return StateRepresentationSpec(
        temporal=temporal,
        uncertainty=uncertainty,
        history_capacity=history_capacity,
        history_scope=history_scope,
    )


def chain_id_for_episode(episode: Any) -> str:
    """Engineering chain identity: one aircraft on one service date.

    No Phase 5 scientific aggregate depends on this key; it only satisfies the
    shared contract's chain grouping requirement and is recorded for audit.
    """

    return content_id(
        {
            "chain_identity": [
                str(getattr(episode, "dataset_instance_id", "data2_2019")),
                str(getattr(episode, "aircraft_id_namespace", "UNKNOWN")),
                str(getattr(episode, "aircraft_id", "UNKNOWN")),
                str(getattr(episode, "episode_start_time", ""))[:10],
            ]
        }
    )


def state_scenario_from_coordinates(
    *,
    scenario_id: int,
    scenario_weight: float,
    stage: OperationalStage,
    t_ib_minutes: float | None,
    d_ob_minutes: float | None,
    d_tx_minutes: float | None,
    d_to_minutes: float | None,
    support: SupportState,
    tx_reference_minutes: float | None = None,
    ib_observed: bool = False,
    ob_observed: bool = False,
    tx_observed: bool = False,
) -> StateScenario:
    return StateScenario(
        scenario_id=int(scenario_id),
        scenario_weight=float(scenario_weight),
        stage=stage,
        t_ib_minutes=t_ib_minutes,
        d_ob_minutes=d_ob_minutes,
        d_tx_minutes=d_tx_minutes,
        d_to_minutes=d_to_minutes,
        tx_reference_minutes=tx_reference_minutes,
        support=support,
        ib_observed=ib_observed,
        ob_observed=ob_observed,
        tx_observed=tx_observed,
    )


def state_set_from_m1_scenarios(
    scenarios: Sequence[Any],
    *,
    episode_id: str,
    chain_id: str,
    node_id: str,
    stage: OperationalStage,
    representation: StateRepresentationSpec,
) -> StateScenarioSet:
    """Adapt frozen ``M1V2Scenario`` draws to the shared state contract."""

    rows: list[StateScenario] = []
    for scenario in scenarios:
        scenario_stage = OperationalStage(str(scenario.operational_stage))
        support = support_of(
            str(scenario.t_ib_support),
            str(scenario.d_ob_support),
            str(scenario.d_tx_support),
        )
        t_ib = scenario.r_ib_minutes
        d_ob = scenario.d_ob_minutes
        d_tx = scenario.d_tx_minutes
        d_to = scenario.d_to_minutes
        rows.append(
            state_scenario_from_coordinates(
                scenario_id=scenario.scenario_id,
                scenario_weight=scenario.scenario_weight,
                stage=scenario_stage,
                t_ib_minutes=None if support is SupportState.ABSTAIN else t_ib,
                d_ob_minutes=None if support is SupportState.ABSTAIN else d_ob,
                d_tx_minutes=None if support is SupportState.ABSTAIN else d_tx,
                d_to_minutes=None if support is SupportState.ABSTAIN else d_to,
                support=support,
                tx_reference_minutes=scenario.tx_reference_minutes,
                ib_observed=bool(scenario.t_ib_observed),
                ob_observed=bool(scenario.d_ob_observed),
                tx_observed=bool(scenario.d_tx_observed),
            )
        )
    return StateScenarioSet(
        episode_id=episode_id,
        chain_id=chain_id,
        node_id=node_id,
        stage=stage,
        representation=representation,
        scenarios=tuple(rows),
    )


def state_set_from_source_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    episode_id: str,
    chain_id: str,
    node_id: str,
    stage: OperationalStage,
    representation: StateRepresentationSpec,
) -> StateScenarioSet:
    """Rebuild the frozen H16 Joint source from the Development parquet rows."""

    resolved: list[StateScenario] = []
    for row in rows:
        support = support_of(
            str(row["R_IB_support"]),
            str(row["D_OB_support"]),
            str(row["D_TX_support"]),
        )
        ib_unsupported = str(row["R_IB_support"]) == SupportState.ABSTAIN.value
        ob_unsupported = str(row["D_OB_support"]) == SupportState.ABSTAIN.value
        tx_unsupported = str(row["D_TX_support"]) == SupportState.ABSTAIN.value
        d_ob = None if ob_unsupported else float(row["D_OB"])
        d_tx = None if tx_unsupported else float(row["D_TX"])
        resolved.append(
            state_scenario_from_coordinates(
                scenario_id=int(row["scenario_id"]),
                scenario_weight=float(row["scenario_weight"]),
                stage=stage,
                t_ib_minutes=(
                    None if ib_unsupported else float(row["R_IB"])
                ),
                d_ob_minutes=d_ob,
                d_tx_minutes=d_tx,
                d_to_minutes=(
                    None if d_ob is None or d_tx is None else d_ob + d_tx
                ),
                support=support,
                tx_observed=stage is OperationalStage.COMPLETED,
            )
        )
    return StateScenarioSet(
        episode_id=episode_id,
        chain_id=chain_id,
        node_id=node_id,
        stage=stage,
        representation=representation,
        scenarios=tuple(resolved),
    )


def consequence_set(
    service: M2ConsequenceService, state_set: StateScenarioSet
) -> ConsequenceScenarioSet:
    """Map a state set through the paper-primary M2 consequence callback."""

    rows: list[ConsequenceScenario] = []
    for scenario in state_set.scenarios:
        unusable = (
            scenario.support is SupportState.ABSTAIN
            or scenario.t_ib_minutes is None
            or scenario.d_ob_minutes is None
            or scenario.d_tx_minutes is None
        )
        if unusable:
            # No admissible source for at least one required coordinate: the
            # scenario keeps its weight and stays typed instead of becoming a
            # zero-consequence draw. Comparison support then excludes it.
            rows.append(
                ConsequenceScenario(
                    scenario_id=scenario.scenario_id,
                    scenario_weight=scenario.scenario_weight,
                    support=SupportState.ABSTAIN,
                )
            )
            continue
        rows.append(
            service.consequence_scenario(
                scenario, node_id=state_set.node_id, support=scenario.support
            )
        )
    return ConsequenceScenarioSet(
        episode_id=state_set.episode_id,
        chain_id=state_set.chain_id,
        node_id=state_set.node_id,
        stage=state_set.stage,
        representation=state_set.representation,
        registry_id=service.registry_id,
        registry_hash=service.registry_hash,
        scenarios=tuple(rows),
        support=SupportState.SUPPORTED,
    )


def comparison_support_for(
    state_set: StateScenarioSet,
    consequence_scenarios,
    *,
    threshold: float = COMMON_SUPPORT_THRESHOLD,
) -> ComparisonSupport:
    rule = ComparisonSupportRule(threshold=float(threshold))
    return build_comparison_support(state_set, consequence_scenarios, rule=rule)


@dataclass(frozen=True)
class NodeBinding:
    """Per-node consequence reference binding plus its audit record."""

    node_id: str
    episode_id: str
    chain_id: str
    binding: ConsequenceReferenceBinding | None
    audit: Mapping[str, Any]


def build_node_binding(
    *,
    node_id: str,
    episode_id: str,
    chain_id: str,
    connection_airport_id: str,
    destination_airport_id: str,
    decision_time: Any,
    bundle: M2ReferenceBundle,
) -> NodeBinding:
    """Resolve the seven-formula reference binding for one Development node.

    Reference resolution reuses the frozen Exp2 Development context builder
    (airport exposure level); it introduces no new scientific choice. Any
    ABSTAIN reference is recorded and leaves the node without a binding, so its
    consequences stay typed instead of being zero-filled.
    """

    keys = AirportReferenceKeys(
        connection_airport_id=connection_airport_id,
        successor_destination_airport_id=destination_airport_id,
        carrier_id=None,
        month=int(decision_time.month),
        quarter=(int(decision_time.month) - 1) // 3 + 1,
    )
    references = build_node_exposure_references(bundle, keys)
    context = build_m2_v4_context(
        bundle, keys, node_specific_exposure=references.airport
    )
    resolved = {
        "turnaround_reference_minutes": context.turnaround_reference,
        "taxi_reference_minutes": context.taxi_reference,
        "expected_pax": context.expected_passengers_per_flight,
        "connection_share": context.connection_share_reference,
        "downstream_exposure": context.expected_downstream_exposure,
    }
    audit: dict[str, Any] = {
        "node_id": node_id,
        "exposure_support_level": str(
            getattr(references.airport, "support_level", "")
        ),
        "reference_values": {},
        "reference_support": {},
        "inert_binding_fields": list(INERT_BINDING_FIELDS),
    }
    for name, value in resolved.items():
        support = getattr(value, "support_state", SupportState.ABSTAIN)
        audit["reference_support"][name] = as_support_state(support).value
        audit["reference_values"][name] = (
            None if value is None else getattr(value, "value", None)
        )
    abstaining = [
        name
        for name, support in audit["reference_support"].items()
        if support == SupportState.ABSTAIN.value
        and name not in INERT_BINDING_FIELDS
    ]
    if abstaining:
        audit["status"] = "UNSUPPORTED_REFERENCE"
        audit["reason_codes"] = [
            f"PHASE5_REFERENCE_ABSTAIN:{name}" for name in sorted(abstaining)
        ]
        return NodeBinding(node_id, episode_id, chain_id, None, audit)

    taxi_value = audit["reference_values"]["taxi_reference_minutes"]
    audit["inert_placeholder_filled"] = taxi_value is None
    binding = ConsequenceReferenceBinding(
        reference_id=node_id,
        turnaround_reference_minutes=float(
            audit["reference_values"]["turnaround_reference_minutes"]
        ),
        taxi_reference_minutes=0.0 if taxi_value is None else float(taxi_value),
        expected_pax=float(audit["reference_values"]["expected_pax"]),
        connection_share=float(audit["reference_values"]["connection_share"]),
        downstream_exposure=float(audit["reference_values"]["downstream_exposure"]),
        itinerary_threshold_minutes=ITINERARY_THRESHOLD_MINUTES,
        service_threshold_minutes=SERVICE_THRESHOLD_MINUTES,
    )
    audit["status"] = "SUPPORTED"
    audit["reason_codes"] = []
    return NodeBinding(node_id, episode_id, chain_id, binding, audit)


@dataclass(frozen=True)
class Authorities:
    """Validated Phase 5 input authorities (Development-only)."""

    cache: M1DevelopmentBaseCache
    cohort: Mapping[str, Any]
    h16_manifest: Mapping[str, Any]
    current_manifest: Mapping[str, Any]
    registry: M2Data2FormalCuRegistry
    reference_bundle: M2ReferenceBundle
    taxi_reference: Any
    audit: Mapping[str, Any]


def _require_file(path: Path) -> Path:
    resolved = assert_development_path(path)
    if not resolved.is_file():
        raise Phase5GuardError(f"PHASE5_REQUIRED_INPUT_MISSING:{resolved}")
    return resolved


def _guard_access_count(payload: Mapping[str, Any], label: str) -> None:
    if int(payload.get("final_test_access_count", -1)) != 0:
        raise Phase5GuardError(f"PHASE5_FINAL_TEST_ACCESS_VIOLATION:{label}")


def load_authorities() -> Authorities:
    """Load and validate every Phase 5 input authority."""

    manifest_path = _require_file(H16_MANIFEST)
    checkpoint_path = _require_file(H16_CHECKPOINT)
    current_manifest_path = _require_file(CURRENT_MANIFEST)
    current_checkpoint_path = _require_file(CURRENT_CHECKPOINT)
    cohort_path = _require_file(COHORT_PATH)
    cache_path = _require_file(SOURCE_CACHE)
    cache_manifest_path = _require_file(SOURCE_CACHE_MANIFEST)
    tail_path = _require_file(TAIL_MANIFEST)
    instruction_path = _require_file(INSTRUCTION_PATH)
    registry_path = _require_file(REGISTRY_V5_PATH)
    passenger_design_path = _require_file(PASSENGER_DESIGN_V5_PATH)
    joint_source = _require_file(JOINT_SOURCE_PATH)
    node_input = _require_file(NODE_INPUT_PATH)

    h16_manifest = read_json(manifest_path)
    current_manifest = read_json(current_manifest_path)
    cohort = read_json(cohort_path)
    cache_manifest = read_json(cache_manifest_path)
    for label, payload in (
        ("h16_manifest", h16_manifest),
        ("h16_cohort", cohort),
        ("current_manifest", current_manifest),
    ):
        _guard_access_count(payload, label)

    if file_hash(checkpoint_path) != h16_manifest.get("checkpoint_hash"):
        raise Phase5GuardError("PHASE5_H16_CHECKPOINT_HASH_MISMATCH")
    if file_hash(current_checkpoint_path) != current_manifest.get("checkpoint_hash"):
        raise Phase5GuardError("PHASE5_CURRENT_CHECKPOINT_HASH_MISMATCH")
    if h16_manifest.get("history_mode") != "FULL_ADAPTIVE_CAUSAL_PREFIX":
        raise Phase5GuardError("PHASE5_H16_NOT_HISTORY_PRIMARY")
    if current_manifest.get("history_mode") != "NO_HISTORY_CURRENT_OBSERVATION":
        raise Phase5GuardError("PHASE5_CURRENT_COMPARATOR_MODE_MISMATCH")

    cache = M1DevelopmentBaseCache.load(
        cache_path,
        cache_manifest_path,
        expected_cache_key=cache_manifest["cache_key"],
        allow_legacy_schema=True,
    )
    registry = load_active_v2_cu_registry(registry_path)
    if registry.final_test_access_count != 0:
        raise Phase5GuardError("PHASE5_REGISTRY_FINAL_TEST_ACCESS_VIOLATION")
    taxi_reference, _, reference_audit = _load_references(PROJECT_ROOT)

    from exp.exp2.development_inputs import _reference_payloads

    bundle = load_data2_reference_bundle(_reference_payloads())
    corrected_turnaround = read_json(CORRECTED_TURNAROUND_REFERENCE_PATH)
    reference_lineage = dict(reference_audit)
    reference_lineage.update(
        {
            "legacy_turnaround_reference_id": reference_audit.get(
                "turnaround_reference_id"
            ),
            "legacy_turnaround_reference_hash": reference_audit.get(
                "turnaround_reference_hash"
            ),
            "legacy_turnaround_artifact_hash": reference_audit.get(
                "turnaround_artifact_hash"
            ),
            "turnaround_reference_id": bundle.turnaround.reference_id,
            "turnaround_reference_hash": bundle.turnaround.manifest_freeze_id,
            "turnaround_artifact_hash": corrected_turnaround.get("artifact_hash"),
            "turnaround_reference_path": str(CORRECTED_TURNAROUND_REFERENCE_PATH),
            "turnaround_reference_file_hash": file_hash(
                CORRECTED_TURNAROUND_REFERENCE_PATH
            ),
            "turnaround_reference_status": "CORRECTED_A2_ACTIVE",
            "turnaround_semantic_correction": corrected_turnaround.get(
                "semantic_correction"
            ),
            "superseded_turnaround_reference_path": str(
                SUPERSEDED_TURNAROUND_REFERENCE_PATH
            ),
            "superseded_turnaround_reference_file_hash": file_hash(
                SUPERSEDED_TURNAROUND_REFERENCE_PATH
            ),
        }
    )
    audit = {
        "final_test_access_count": 0,
        "final_test_paths_read": [],
        "instruction_path": str(instruction_path),
        "instruction_hash": file_hash(instruction_path),
        "registry_id": registry.registry_id,
        "registry_hash": registry.registry_hash,
        "registry_scientific_status": registry.scientific_status,
        "registry_implementation_status": registry.implementation_status,
        "registry_source_hash": file_hash(registry_path),
        "passenger_design_path": str(passenger_design_path),
        "passenger_design_hash": file_hash(passenger_design_path),
        "h16_manifest_path": str(manifest_path),
        "h16_manifest_hash": file_hash(manifest_path),
        "h16_checkpoint_hash": h16_manifest.get("checkpoint_hash"),
        "h16_artifact_hash": h16_manifest.get("artifact_hash"),
        "h16_training_seed": h16_manifest.get("training_seed"),
        "h16_epochs": h16_manifest.get("epochs"),
        "current_manifest_path": str(current_manifest_path),
        "current_manifest_hash": file_hash(current_manifest_path),
        "current_checkpoint_hash": current_manifest.get("checkpoint_hash"),
        "cohort_path": str(cohort_path),
        "cohort_hash": file_hash(cohort_path),
        "cache_path": str(cache_path),
        "cache_hash": cache_manifest.get("cache_hash"),
        "cache_key": cache_manifest.get("cache_key"),
        "tail_manifest_path": str(tail_path),
        "tail_manifest_hash": file_hash(tail_path),
        "joint_source_path": str(joint_source),
        "joint_source_hash": file_hash(joint_source),
        "node_input_path": str(node_input),
        "node_input_hash": file_hash(node_input),
        "reference_lineage": reference_lineage,
        "reference_bundle_ids": dict(bundle.reference_ids),
    }
    return Authorities(
        cache=cache,
        cohort=cohort,
        h16_manifest=h16_manifest,
        current_manifest=current_manifest,
        registry=registry,
        reference_bundle=bundle,
        taxi_reference=taxi_reference,
        audit=audit,
    )


def load_development_bridge():
    """Load the exact Development PRE bridge (expensive: about 100 seconds).

    Callers must reuse the returned objects for every family instead of
    reloading per model.
    """

    from exp.exp1.formal_inputs import load_exact_inputs

    cache, rows, mapping, taxi_reference, manifest = load_exact_inputs()
    if len(rows) != DEVELOPMENT_NODE_COUNT:
        raise Phase5GuardError(
            f"PHASE5_DEVELOPMENT_NODE_COUNT_MISMATCH:{len(rows)}"
        )
    return {
        "cache": cache,
        "rows": tuple(rows),
        "mapping": mapping,
        "taxi_reference": taxi_reference,
        "manifest": manifest,
    }


def load_tail_continuations() -> dict[str, Any]:
    from model.M1.tail import load_tail_continuations as _load

    return _load(assert_development_path(TAIL_MANIFEST))


def expected_cu_for_support(
    consequence_scenarios, support: ComparisonSupport
) -> dict[str, float]:
    return expected_cu_vector(consequence_scenarios, support)


def node_consequence_summary(
    state_set: StateScenarioSet,
    service: M2ConsequenceService,
) -> dict[str, Any]:
    """Common-support expected CU plus typed support diagnostics for one node."""

    consequences = consequence_set(service, state_set)
    support = comparison_support_for(state_set, consequences)
    summary: dict[str, Any] = {
        "node_id": state_set.node_id,
        "episode_id": state_set.episode_id,
        "chain_id": state_set.chain_id,
        "stage": state_set.stage.value,
        "representation_id": state_set.representation.representation_id,
        "supported_mass": support.supported_mass,
        "included": support.included,
        "status": support.status.value,
        "reason_codes": list(support.reason_codes),
        "scenario_count_supported": len(support.supported_scenario_ids),
        "scenario_count_total": support.scenario_count_total,
        "expected_cu": None,
    }
    if support.included:
        summary["expected_cu"] = expected_cu_for_support(consequences, support)
    return summary


def aggregate_component_table(
    rows: Iterable[Mapping[str, Any]], components: Sequence[str]
) -> dict[str, Any]:
    """Mean/SD of node-level expected CU per component, skipping abstentions."""

    resolved = [row for row in rows if row.get("expected_cu") is not None]
    table: dict[str, Any] = {"node_count": len(resolved)}
    for component in components:
        values = [float(row["expected_cu"][component]) for row in resolved]
        table[component] = {
            "mean": None if not values else sum(values) / len(values),
            "sd": None if len(values) < 2 else _population_sd(values),
            "n": len(values),
        }
    return table


def _population_sd(values: Sequence[float]) -> float:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return float(variance**0.5)


__all__ = [
    "COMMON_SUPPORT_THRESHOLD",
    "CURRENT_CHECKPOINT",
    "DEVELOPMENT_EPISODES",
    "DEVELOPMENT_NODE_COUNT",
    "EXP2_DEVELOPMENT_ROOT",
    "FINAL_TEST_ROOT",
    "H16_CHECKPOINT",
    "H8_CHECKPOINT",
    "H8_MANIFEST",
    "H8_ROOT",
    "INERT_BINDING_FIELDS",
    "INSTRUCTION_PATH",
    "JOINT_SOURCE_PATH",
    "MISSING",
    "NODE_INPUT_PATH",
    "PHASE_DIR",
    "PRIMARY_TRAINING_SEED",
    "PROJECT_ROOT",
    "SCENARIO_COUNT",
    "TAIL_MANIFEST",
    "TRAIN_MONTHS",
    "UNSUPPORTED",
    "Authorities",
    "NodeBinding",
    "Phase5GuardError",
    "aggregate_component_table",
    "assert_development_path",
    "as_support_state",
    "build_node_binding",
    "chain_id_for_episode",
    "comparison_support_for",
    "consequence_set",
    "expected_cu_for_support",
    "file_hash",
    "load_authorities",
    "load_development_bridge",
    "load_tail_continuations",
    "node_consequence_summary",
    "read_json",
    "representation_spec",
    "state_set_from_m1_scenarios",
    "state_set_from_source_rows",
    "support_of",
    "write_json",
]
