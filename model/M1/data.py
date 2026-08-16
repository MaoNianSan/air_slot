from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from math import cos, radians, sin

import torch

from model.common.enums import EvidenceClass, OperationalStage, SupportState
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel, SupportedValue
from model.PRE.contracts.pre_state import PREState


@dataclass(frozen=True)
class M1SequenceBatch:
    values: torch.Tensor
    lengths: torch.Tensor
    episode_weights: torch.Tensor
    episode_ids: tuple[str, ...]


class NormalizationValue(FrozenModel):
    mean: float
    std: float


class M1NormalizationArtifact(FrozenModel):
    fitted_split: str
    values: dict[str, NormalizationValue]

    def normalize(self, name: str, value: float) -> float:
        if self.fitted_split != "train":
            raise ContractError("M1_NORMALIZATION_MUST_BE_TRAIN_ONLY")
        item = self.values.get(name)
        if item is None:
            raise ContractError(f"M1_NORMALIZATION_MISSING:{name}")
        return (value - item.mean) / item.std


MOTION_FIELDS = (
    "latitude_deg", "longitude_deg", "velocity_mps", "on_ground",
    "baro_altitude_m", "geo_altitude_m", "heading_deg", "vertical_rate_mps",
)
WEATHER_FIELDS = (
    "temperature_c", "dewpoint_c", "wind_direction_deg", "wind_speed_mps",
    "wind_gust_mps", "qnh_hpa", "visibility_m",
)
SCIENTIFIC_OBJECTS = ("predecessor_motion", "current_weather", "schedule_reference")
EVIDENCE_LEVELS = tuple(item.value for item in EvidenceClass)
SUPPORT_LEVELS = tuple(item.value for item in SupportState)
STAGE_LEVELS = tuple(item.value for item in OperationalStage)


def _x_names() -> tuple[str, ...]:
    result = []
    for field in MOTION_FIELDS:
        result.extend((f"motion.{field}.sin", f"motion.{field}.cos")) if field == "heading_deg" \
            else result.append(f"motion.{field}")
    for field in WEATHER_FIELDS:
        result.extend((f"weather.{field}.sin", f"weather.{field}.cos")) \
            if field == "wind_direction_deg" else result.append(f"weather.{field}")
    result.append("schedule.signed_minutes_to_crs_departure")
    return tuple(result)


X_NAMES = _x_names()
MASK_FIELDS = tuple([f"motion.{name}" for name in MOTION_FIELDS]
                    + [f"weather.{name}" for name in WEATHER_FIELDS]
                    + ["schedule.signed_minutes_to_crs_departure"])
M_NAMES = tuple(f"{name}.{kind}_mask" for name in MASK_FIELDS
                for kind in ("missing", "stale", "fallback"))
DELTA_NAMES = ("motion.observation_age_minutes", "weather.observation_age_minutes",
               "node.spacing_minutes")
E_NAMES = tuple(f"{obj}.evidence.{level}" for obj in SCIENTIFIC_OBJECTS
                for level in EVIDENCE_LEVELS) + tuple(
                f"{obj}.support.{level}" for obj in SCIENTIFIC_OBJECTS
                for level in SUPPORT_LEVELS)
S_NAMES = tuple(f"stage.{name}" for name in STAGE_LEVELS)
FEATURE_NAMES = X_NAMES + M_NAMES + DELTA_NAMES + E_NAMES + S_NAMES
GROUP_SLICES = {
    "X": slice(0, len(X_NAMES)),
    "M": slice(len(X_NAMES), len(X_NAMES) + len(M_NAMES)),
    "Delta": slice(len(X_NAMES) + len(M_NAMES), len(X_NAMES) + len(M_NAMES) + len(DELTA_NAMES)),
    "E": slice(len(X_NAMES) + len(M_NAMES) + len(DELTA_NAMES),
               len(X_NAMES) + len(M_NAMES) + len(DELTA_NAMES) + len(E_NAMES)),
    "S": slice(len(FEATURE_NAMES) - len(S_NAMES), len(FEATURE_NAMES)),
}
NORMALIZED_NAMES = tuple(name for name in X_NAMES if not name.endswith((".sin", ".cos"))
                         and name != "motion.on_ground") + DELTA_NAMES


def fit_train_normalization(rows: list[dict[str, float]], *, split: str) -> M1NormalizationArtifact:
    if split != "train":
        raise ContractError("M1_NORMALIZATION_MUST_BE_TRAIN_ONLY")
    values = {}
    for name in NORMALIZED_NAMES:
        observed = [float(row[name]) for row in rows if name in row]
        if not observed:
            values[name] = NormalizationValue(mean=0.0, std=1.0)
            continue
        mean = sum(observed) / len(observed)
        variance = sum((value - mean) ** 2 for value in observed) / len(observed)
        values[name] = NormalizationValue(mean=mean, std=max(variance ** .5, 1e-12))
    return M1NormalizationArtifact(fitted_split="train", values=values)


def episode_normalized_weights(episode_ids: list[str]) -> torch.Tensor:
    counts = Counter(episode_ids)
    return torch.tensor([1.0 / counts[item] for item in episode_ids], dtype=torch.float32)


def _find(pre: PREState, family: str, variable: str) -> SupportedValue:
    container = getattr(pre, family)
    value = container.get(variable)
    if value is not None:
        return value
    return SupportedValue(value=None, unit="canonical",
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_ceiling=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN, reason_code=f"MISSING_{variable.upper()}")


def _lineage(pre: PREState, variable: str):
    return next((item for item in pre.variable_lineage
                 if item.scientific_variable == variable), None)


def _field(value: SupportedValue, field: str):
    if value.support_state is SupportState.ABSTAIN or not isinstance(value.value, dict):
        return None
    return value.value.get(field)


def _quality_masks(value: SupportedValue, lineage) -> tuple[float, float]:
    flags = set(value.quality_flags) | (set(lineage.quality_flags) if lineage else set())
    stale = float(any(flag.startswith("STALE") for flag in flags))
    fallback = float(bool(lineage and lineage.fallback_used))
    return stale, fallback


def _scaled(normalization: M1NormalizationArtifact, name: str, value) -> float:
    return normalization.normalize(name, float(value))


def validate_full_history_prefix(states: list[PREState]) -> None:
    """Require the complete frozen five-minute prefix from episode node zero.

    M1 has no scientific lookback or truncation parameter.  A caller therefore
    may end a sequence at any current decision node, but may not omit earlier
    legal nodes from that episode's rolling grid.
    """
    if not states:
        raise ContractError("M1_EMPTY_PRE_SEQUENCE")
    episode_ids = {state.decision_node.episode_id for state in states}
    if len(episode_ids) != 1:
        raise ContractError("M1_HISTORY_MULTIPLE_EPISODES")
    first = states[0].decision_node
    if first.node_index != 0:
        raise ContractError("M1_HISTORY_MUST_START_AT_NODE_ZERO")
    for expected_index, state in enumerate(states):
        node = state.decision_node
        if node.node_index != expected_index:
            raise ContractError("M1_HISTORY_NONCONTIGUOUS_NODE_INDEX")
        if node.roll_minutes != 5:
            raise ContractError("M1_HISTORY_GRID_MUST_BE_FIVE_MINUTES")
        expected_time = first.decision_time + timedelta(minutes=5 * expected_index)
        if node.decision_time != expected_time:
            raise ContractError("M1_HISTORY_NONCONTIGUOUS_DECISION_TIME")


def encode_pre_sequence(states: list[PREState],
                        normalization: M1NormalizationArtifact) -> torch.Tensor:
    validate_full_history_prefix(states)
    rows = []
    previous_time = None
    for pre in states:
        motion = _find(pre, "predecessor_state", "predecessor_motion")
        weather = _find(pre, "current_state", "current_weather")
        schedule = _find(pre, "successor_state", "schedule_reference")
        objects = {"predecessor_motion": motion, "current_weather": weather,
                   "schedule_reference": schedule}
        lineages = {name: _lineage(pre, name) for name in objects}
        x, masks = [], []
        for prefix, value, fields in (("motion", motion, MOTION_FIELDS),
                                      ("weather", weather, WEATHER_FIELDS)):
            lineage = lineages["predecessor_motion" if prefix == "motion" else "current_weather"]
            stale, fallback = _quality_masks(value, lineage)
            for field in fields:
                raw = _field(value, field)
                missing = float(raw is None)
                masks.extend((missing, stale, fallback))
                if field in {"heading_deg", "wind_direction_deg"}:
                    angle = radians(float(raw)) if raw is not None else 0.0
                    x.extend((sin(angle) if raw is not None else 0.0,
                              cos(angle) if raw is not None else 0.0))
                elif field == "on_ground":
                    x.append(float(bool(raw)) if raw is not None else 0.0)
                else:
                    name = f"{prefix}.{field}"
                    x.append(_scaled(normalization, name, raw) if raw is not None else 0.0)
        schedule_time = _field(schedule, "scheduled_departure_utc")
        schedule_minutes = None if schedule_time is None else \
            (schedule_time - pre.decision_node.decision_time).total_seconds() / 60.0
        stale, fallback = _quality_masks(schedule, lineages["schedule_reference"])
        masks.extend((float(schedule_minutes is None), stale, fallback))
        x.append(_scaled(normalization, "schedule.signed_minutes_to_crs_departure", schedule_minutes)
                 if schedule_minutes is not None else 0.0)
        delta = []
        for variable in ("predecessor_motion", "current_weather"):
            lineage = lineages[variable]
            age = None if lineage is None or lineage.age_seconds is None else lineage.age_seconds / 60.0
            delta.append(_scaled(normalization,
                "motion.observation_age_minutes" if variable == "predecessor_motion"
                else "weather.observation_age_minutes", age) if age is not None else 0.0)
        spacing = 0.0 if previous_time is None else \
            (pre.decision_node.decision_time - previous_time).total_seconds() / 60.0
        delta.append(_scaled(normalization, "node.spacing_minutes", spacing))
        previous_time = pre.decision_node.decision_time
        evidence = []
        for name in SCIENTIFIC_OBJECTS:
            value = objects[name]
            evidence.extend(float(value.evidence_class.value == level) for level in EVIDENCE_LEVELS)
        for name in SCIENTIFIC_OBJECTS:
            value = objects[name]
            evidence.extend(float(value.support_state.value == level) for level in SUPPORT_LEVELS)
        stage = pre.decision_node.operational_stage.value
        stages = [float(stage == name) for name in STAGE_LEVELS]
        rows.append(x + masks + delta + evidence + stages)
    return torch.tensor(rows, dtype=torch.float32)
