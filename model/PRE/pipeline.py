from datetime import datetime
from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.value_objects import FrozenModel
from model.PRE.contracts.pre_state import PREState, ReferenceState, TargetSupportState
from model.PRE.episode.node_builder import build_decision_node
from model.common.paths import project_path
from model.common.config import load_config_layers
from model.PRE.contracts.canonical import CanonicalSourceRecord
from model.PRE.factual.availability import Data2FactualReplayAvailabilityPolicy
from model.PRE.factual.replay import publish_factual_replay
from model.PRE.feature_registry.loader import RegistryBundle, load_registry_bundle
from model.PRE.mapping import RegistryPREMapper, publish_mapped
from model.PRE.publication.static_reference import publish_static_reference
from model.PRE.foundation import PREBuildResult


def _target_support(dataset_instance_id: str, bundle: RegistryBundle):
    schedule = next(item for item in bundle.scientific_variables
                    if item.scientific_variable == "schedule_reference")
    schedule_support = schedule.dataset_support[dataset_instance_id]
    r_ob_supported = schedule_support.formal_input_support is not EvidenceClass.UNSUPPORTED
    return (
        TargetSupportState(target_name="R_IB", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="R_IB_V1", dataset_ceiling=EvidenceClass.DERIVED,
            formal_input_support=EvidenceClass.DERIVED, realized_outcome_support=EvidenceClass.DERIVED),
        TargetSupportState(target_name="DELTA_OB", active=r_ob_supported,
            support_state=SupportState.SUPPORTED if r_ob_supported else SupportState.ABSTAIN,
            target_definition_id="DELTA_OB_V1",
            dataset_ceiling=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            formal_input_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.UNSUPPORTED,
            realized_outcome_support=EvidenceClass.DIRECT if r_ob_supported else EvidenceClass.DERIVED,
            abstention_reason=None if r_ob_supported else "TARGET_SEMANTICS_UNSUPPORTED"),
        TargetSupportState(target_name="T_TX", active=True, support_state=SupportState.SUPPORTED,
            target_definition_id="T_TX_V1", dataset_ceiling=EvidenceClass.DERIVED,
            formal_input_support=EvidenceClass.DERIVED, realized_outcome_support=EvidenceClass.DERIVED),
    )


class ProductionPRERequest(FrozenModel):
    episode_id: str
    predecessor_id: str
    successor_id: str
    dataset_instance_id: str
    decision_time: datetime
    information_cutoff: datetime
    records: tuple[CanonicalSourceRecord, ...]
    config_hash: str
    registry_hash: str
    connection_airport_id: str | None = None
    operational_stage: OperationalStage = OperationalStage.PRE_IB
    node_index: int = 0
    roll_minutes: int = 5
    factual_availability_policy: str | None = None
    factual_replay_declared_lag_minutes: float | None = None
    taxi_reference: object | None = None
    turnaround_reference: object | None = None


class ProductionPREPublisher:
    """Reuse immutable registry/config state across a preparation run."""

    def __init__(self, bundle: RegistryBundle, *, weather_max_age_minutes: int,
                 factual_availability_policy: str = "UNRESOLVED",
                 factual_replay_declared_lag_minutes: float | None = None):
        self.bundle = bundle
        self.weather_max_age_minutes = weather_max_age_minutes
        self.factual_availability_policy = factual_availability_policy
        self.factual_replay_declared_lag_minutes = factual_replay_declared_lag_minutes
        self.mapper = RegistryPREMapper(bundle)
        self._target_support_cache: dict[str, tuple[TargetSupportState, ...]] = {}

    @classmethod
    def from_project(cls) -> "ProductionPREPublisher":
        bundle = load_registry_bundle(project_path("registries"))
        scientific = load_config_layers(project_path("configs")).scientific
        policy = scientific.parameters["data2_factual_replay_availability"].value
        return cls(bundle, weather_max_age_minutes=int(
            scientific.parameters["weather_max_age_minutes"].value),
            factual_availability_policy=policy or "UNRESOLVED",
            factual_replay_declared_lag_minutes=0.0 if policy else None)

    def target_support(self, dataset_instance_id: str) -> tuple[TargetSupportState, ...]:
        support = self._target_support_cache.get(dataset_instance_id)
        if support is None:
            support = _target_support(dataset_instance_id, self.bundle)
            self._target_support_cache[dataset_instance_id] = support
        return support

    def publish(self, request: ProductionPRERequest) -> PREBuildResult:
        mapper = self.mapper
        provisional = build_decision_node(
            episode_id=request.episode_id, predecessor_id=request.predecessor_id,
            successor_id=request.successor_id, decision_time=request.decision_time,
            information_cutoff=request.information_cutoff, config_hash=request.config_hash,
            registry_hash=request.registry_hash, legal_record_ids=(),
            operational_stage=request.operational_stage, node_index=request.node_index,
            roll_minutes=request.roll_minutes)
        mapped_records = tuple(
            item for item in (mapper.map_record(record) for record in request.records)
            if item is not None)
        mapped = mapped_records + mapper.complete_missing(
            request.dataset_instance_id,
            {item.scientific_variable for item in mapped_records})
        schedule = next((item.value.value for item in mapped_records
                         if item.scientific_variable == "schedule_reference"), None)
        airport_roles = None if schedule is None else {
            "origin": schedule.get("origin_airport_id"),
            "destination": schedule.get("destination_airport_id"),
            "connection": request.connection_airport_id or schedule.get("origin_airport_id"),
        }
        families, ledger, lineage, ids = publish_mapped(
            mapped, cutoff=request.information_cutoff,
            decision_node_id=provisional.decision_node_id,
            airport_roles=airport_roles,
            weather_max_age_minutes=self.weather_max_age_minutes)
        node = build_decision_node(
            episode_id=request.episode_id, predecessor_id=request.predecessor_id,
            successor_id=request.successor_id, decision_time=request.decision_time,
            information_cutoff=request.information_cutoff, config_hash=request.config_hash,
            registry_hash=request.registry_hash, legal_record_ids=ids,
            operational_stage=request.operational_stage, node_index=request.node_index,
            roll_minutes=request.roll_minutes)
        # Re-key entries to final deterministic node identity.
        ledger = tuple(item.model_copy(update={"decision_node_id": node.decision_node_id})
                       for item in ledger)
        lineage = tuple(item.model_copy(update={"decision_node_id": node.decision_node_id})
                        for item in lineage)
        target_support = self.target_support(request.dataset_instance_id)
        successor_state = dict(families["successor_state"])
        current_state = dict(families["current_state"])
        # --- Tranche 3 factual replay (role-aware, cutoff-gated) ---
        policy = Data2FactualReplayAvailabilityPolicy(
            request.factual_availability_policy or self.factual_availability_policy)
        predecessor_fact, successor_fact = publish_factual_replay(
            request.records, predecessor_id=request.predecessor_id,
            successor_id=request.successor_id, policy=policy,
            information_cutoff=request.information_cutoff,
            declared_lag_minutes=(
                request.factual_replay_declared_lag_minutes
                if request.factual_replay_declared_lag_minutes is not None
                else self.factual_replay_declared_lag_minutes
            ))
        if predecessor_fact is not None:
            current_state["predecessor_operational_fact"] = predecessor_fact
        if successor_fact is not None:
            successor_state["successor_operational_fact"] = successor_fact
        # --- Tranche 3 static/reference publication ---
        provisional_pre = PREState(
            decision_node=node, predecessor_state=families["predecessor_state"],
            current_state=current_state, successor_state=successor_state,
            evidence_ledger=ledger, variable_lineage=lineage,
            reference_state=ReferenceState(entries=families["reference_state"]),
            target_support=target_support)
        published, publication_meta = publish_static_reference(
            provisional_pre, taxi_reference=request.taxi_reference,
            turnaround_reference=request.turnaround_reference,
            connection_airport_id=request.connection_airport_id)
        successor_state.update(published)
        return PREBuildResult(pre_state=PREState(
            decision_node=node, predecessor_state=families["predecessor_state"],
            current_state=current_state, successor_state=successor_state,
            evidence_ledger=ledger, variable_lineage=lineage,
            reference_state=ReferenceState(entries=families["reference_state"]),
            target_support=target_support,
            static_reference_publication=publication_meta), FIXTURE_ONLY=False,
            evaluation_scope="PRODUCTION")


def publish_production_pre(request: ProductionPRERequest) -> PREBuildResult:
    return ProductionPREPublisher.from_project().publish(request)
