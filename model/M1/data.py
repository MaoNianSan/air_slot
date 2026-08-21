from collections import Counter
from collections.abc import Sequence
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

# ---------------------------------------------------------------------------
# V2 principal input groups (Round-2 M1 V2).
#
# Dataset support split:
#   SHARED            current operational/factual state, schedule timing,
#                     NOAA weather (incl. ceiling-base ceiling_base_m), Delta X,
#                     short-term AR summaries, Delta t, missing/stale/fallback
#                     masks (including typed ceiling status and derived-validity),
#                     evidence/support quality.
#   DATA1_SUPPORTED   predecessor_motion trajectory fields (NOT part of the V2
#                     shared principal encoder; Data2 never requires them).
#   UNSUPPORTED       crew / gate / slot / standby aircraft (no raw path).
#   STATIC/REFERENCE route/carrier/aircraft/schedule typed identity/context is
#                     published by PRE and retained without ordinal encoding;
#                     train-frozen turnaround/taxi reference values enter the
#                     separate numeric ``c_static`` branch with full lineage.
#                     The dynamic ``schedule.signed_minutes_to_crs_departure``
#                     countdown is a CURRENT-AR (DYNAMIC) variable and stays in
#                     the recurrent sequence only — it is never duplicated as a
#                     static branch input (Tranche 2.1 false static closure
#                     removed in Round 2.2).
# ---------------------------------------------------------------------------
V2_WEATHER_FIELDS = (
    "temperature_c", "dewpoint_c", "wind_direction_deg", "wind_speed_mps",
    "qnh_hpa", "visibility_m", "ceiling_base_m",
)
V2_STATE_FIELDS = ("ib_realized", "ob_realized", "to_realized")
V2_OBJECTS = ("current_weather", "schedule_reference", "current_state")
V2_STATE_REALIZED_BY_STAGE = {
    "ib_realized": frozenset({"POST_IB_PRE_OB", "POST_OB_PRE_TO", "COMPLETED"}),
    "ob_realized": frozenset({"POST_OB_PRE_TO", "COMPLETED"}),
    "to_realized": frozenset({"COMPLETED"}),
}
V2_DELTA_X_FIELDS = tuple(
    f"delta.weather.{name}" for name in V2_WEATHER_FIELDS
    if name != "wind_direction_deg"
) + (
    "delta.schedule.signed_minutes_to_crs_departure",
)
V2_AR_FIELDS = tuple(
    f"ar.weather.{name}" for name in V2_WEATHER_FIELDS
    if name != "wind_direction_deg"
)
V2_DELTA_T_FIELDS = ("weather.observation_age_minutes",)
V2_DERIVED_FIELDS = V2_DELTA_X_FIELDS + V2_AR_FIELDS


def _v2_x_names() -> tuple[str, ...]:
    result = [f"state.{name}" for name in V2_STATE_FIELDS]
    result.append("schedule.signed_minutes_to_crs_departure")
    for field in V2_WEATHER_FIELDS:
        if field == "wind_direction_deg":
            result.extend(("weather.wind_direction_deg.sin", "weather.wind_direction_deg.cos"))
        else:
            result.append(f"weather.{field}")
    result.extend(V2_DELTA_X_FIELDS)
    result.extend(V2_AR_FIELDS)
    return tuple(result)


X_NAMES_V2 = _v2_x_names()
MASK_FIELDS_V2 = tuple(f"weather.{name}" for name in V2_WEATHER_FIELDS) + (
    "schedule.signed_minutes_to_crs_departure",
) + tuple(f"state.{name}" for name in V2_STATE_FIELDS)
M_NAMES_V2 = (
    tuple(f"{name}.{kind}_mask" for name in MASK_FIELDS_V2
          for kind in ("missing", "stale", "fallback"))
    + ("weather.ceiling_base_m.unlimited_mask",)
    + tuple(f"{name}.derived_missing_mask" for name in V2_DERIVED_FIELDS)
)
DELTA_NAMES_V2 = V2_DELTA_T_FIELDS
E_NAMES_V2 = tuple(f"{obj}.evidence.{level}" for obj in V2_OBJECTS
                   for level in EVIDENCE_LEVELS) + tuple(
                   f"{obj}.support.{level}" for obj in V2_OBJECTS
                   for level in SUPPORT_LEVELS)
S_NAMES_V2 = ()
FEATURE_NAMES_V2 = X_NAMES_V2 + M_NAMES_V2 + DELTA_NAMES_V2 + E_NAMES_V2 + S_NAMES_V2
GROUP_SLICES_V2 = {
    "X": slice(0, len(X_NAMES_V2)),
    "M": slice(len(X_NAMES_V2), len(X_NAMES_V2) + len(M_NAMES_V2)),
    "Delta": slice(len(X_NAMES_V2) + len(M_NAMES_V2),
                   len(X_NAMES_V2) + len(M_NAMES_V2) + len(DELTA_NAMES_V2)),
    "E": slice(len(X_NAMES_V2) + len(M_NAMES_V2) + len(DELTA_NAMES_V2),
               len(FEATURE_NAMES_V2) - len(S_NAMES_V2)),
    "S": slice(len(FEATURE_NAMES_V2) - len(S_NAMES_V2), len(FEATURE_NAMES_V2)),
}
NORMALIZED_NAMES_V2 = tuple(
    name for name in X_NAMES_V2
    if name.startswith(("weather.", "schedule.")) and not name.endswith((".sin", ".cos"))
) + V2_DELTA_T_FIELDS


V2_FAST_FEATURE_COUNT = len(FEATURE_NAMES_V2)

# ---------------------------------------------------------------------------
# Tranche 3 static/reference MODEL_FEATURE block (``c_static``).
#
# Only PRE-published MODEL_FEATURE fields enter the numeric static block.
# RETAINED_IDENTITY fields (route / carrier / aircraft / schedule-reference)
# never become ordinal numeric predictors without a frozen deterministic
# encoding contract (MODEL_FEATURE_PENDING); they stay in the M1 input
# lineage.  The numeric turnaround/taxi references are train-frozen empirical
# artifacts (minutes) and enter directly (deterministic, no search).
# ---------------------------------------------------------------------------
STATIC_FEATURE_NAMES: tuple[str, ...] = (
    "turnaround_reference_minutes",
    "taxi_reference_minutes",
)
STATIC_FEATURE_COUNT: int = len(STATIC_FEATURE_NAMES)

_PUBLISHED_STATIC_REFERENCE_FIELDS = (
    "route_context",
    "carrier_context",
    "aircraft_identity",
    "schedule_reference",
    "turnaround_reference",
    "taxi_reference",
)


def _published_static_value(pre: PREState, field: str):
    value = _find(pre, "successor_state", field)
    if value.support_state is SupportState.ABSTAIN or not isinstance(value.value, dict):
        return None
    return value.value


def static_reference_features_from_pre(
    pre_state: PREState,
    static_context=None,
) -> tuple[torch.Tensor | None, dict[str, object]]:
    """Build ``c_static`` + retained-identity lineage from PRE publication.

    Only MODEL_FEATURE fields that PRE has published (``static_context`` marks
    the field published with ``model_feature_status == MODEL_FEATURE``, the
    published value is SUPPORTED, and the reference carries a legal
    ``reference_id`` / ``freeze_id``) enter the numeric block.  RETAINED_IDENTITY
    / MODEL_FEATURE_PENDING fields are returned in the lineage dict and never
    fabricated as ordinal numeric inputs.
    """
    model_feature_fields: set[str] = set()
    if static_context is not None:
        model_feature_fields = set(static_context.model_feature_fields())
    numeric: list[float | None] = []
    for field, name in (("turnaround_reference", "turnaround_reference_minutes"),
                        ("taxi_reference", "taxi_reference_minutes")):
        if field not in model_feature_fields:
            numeric.append(None)
            continue
        published = _published_static_value(pre_state, field)
        if published is None:
            numeric.append(None)
            continue
        if not published.get("reference_id") or not published.get("freeze_id"):
            # Legal provenance is required for a numeric MODEL_FEATURE; a
            # published-but-unfrozen reference stays MODEL_FEATURE_PENDING.
            numeric.append(None)
            continue
        raw = published.get("value")
        numeric.append(None if raw is None else float(raw))
    lineage: dict[str, object] = {}
    for field in _PUBLISHED_STATIC_REFERENCE_FIELDS:
        published = _published_static_value(pre_state, field)
        if published is not None:
            lineage[field] = published
    if any(item is None for item in numeric):
        return None, lineage
    return torch.tensor([numeric], dtype=torch.float32), lineage


def fast_features_from_sequence(
    values: torch.Tensor, lengths: torch.Tensor | None = None
) -> torch.Tensor:
    """Current / local-change / short-term AR representation ``r_fast``.

    ``r_fast(i, t)`` is the decision-node (last causal row) of the full V2
    feature vector: current state + current weather + decision-node schedule
    countdown + Delta X (declared local changes) + short-term AR summaries +
    missing/stale/fallback masks + evidence/support quality.  This is a
    deterministic feature block (Round 2.2 ``IMPLEMENTATION_CHOICE_NO_SEARCH``),
    NOT a second flattening of the full sequence and NOT a LightGBM prediction.
    It is consumed by the FAST path directly and by the STATE_AWARE path via
    ``projection(r_fast)`` alongside ``GRU(history)``.

    Rows whose length is zero fall back to the leading padded value (never
    fabricated; the sequence contract guarantees length >= 1 for supported
    nodes).
    """
    if lengths is None:
        lengths = torch.full((values.shape[0],), values.shape[1], dtype=torch.long)
    rows = torch.arange(values.shape[0], device=values.device)
    indices = (lengths - 1).clamp_min(0)
    return values[rows, indices]


def fit_train_normalization(rows: list[dict[str, float]], *, split: str,
                                names: Sequence[str] | None = None) -> M1NormalizationArtifact:
    """Train-only normalization over the V2 principal feature names."""
    if split != "train":
        raise ContractError("M1_NORMALIZATION_MUST_BE_TRAIN_ONLY")
    selected = NORMALIZED_NAMES_V2 if names is None else tuple(names)
    values = {}
    for name in selected:
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


def validate_history_sequence(states: list[PREState] | tuple[PREState, ...], *,
                              require_episode_start: bool) -> None:
    """Validate one contiguous causal sequence on the frozen five-minute grid.

    ADAPTIVE history starts at episode node zero. CURRENT and FIXED history are
    legal contiguous suffixes of that same episode grid.
    """
    if not states:
        raise ContractError("M1_EMPTY_PRE_SEQUENCE")
    episode_ids = {state.decision_node.episode_id for state in states}
    if len(episode_ids) != 1:
        raise ContractError("M1_HISTORY_MULTIPLE_EPISODES")
    first = states[0].decision_node
    if require_episode_start and first.node_index != 0:
        raise ContractError("M1_HISTORY_MUST_START_AT_NODE_ZERO")
    for offset, state in enumerate(states):
        node = state.decision_node
        if node.node_index != first.node_index + offset:
            raise ContractError("M1_HISTORY_NONCONTIGUOUS_NODE_INDEX")
        if node.roll_minutes != 5:
            raise ContractError("M1_HISTORY_GRID_MUST_BE_FIVE_MINUTES")
        expected_time = first.decision_time + timedelta(minutes=5 * offset)
        if node.decision_time != expected_time:
            raise ContractError("M1_HISTORY_NONCONTIGUOUS_DECISION_TIME")
        if node.information_cutoff > node.decision_time:
            raise ContractError("M1_HISTORY_FUTURE_INFORMATION")


def validate_full_history_prefix(states: list[PREState] | tuple[PREState, ...]) -> None:
    """Require the complete ADAPTIVE prefix from episode node zero."""
    validate_history_sequence(states, require_episode_start=True)


def _state_support_value() -> SupportedValue:
    """Decision-time operational stage as a supported current-state object."""
    return SupportedValue(
        value=None, unit="canonical",
        evidence_class=EvidenceClass.DIRECT,
        support_ceiling=EvidenceClass.DIRECT,
        support_state=SupportState.SUPPORTED,
        reason_code="STAGE_DERIVED_DECISION_TIME_FACT",
    )


def encode_pre_sequence(states: list[PREState] | tuple[PREState, ...],
                        normalization: M1NormalizationArtifact, *,
                        require_episode_start: bool = True) -> torch.Tensor:
    """Encode the V2 principal feature vector for one causal PRE prefix.

    The V2 encoder never requires predecessor_motion trajectory fields
    (DATA1_SUPPORTED only); Data2 principal inference is fully supported by
    current state, schedule timing, NOAA weather (incl. ceiling-base), Delta X,
    short-term AR summaries, Delta t, masks, and evidence/support quality.
    """
    validate_history_sequence(states, require_episode_start=require_episode_start)
    rows = []
    previous_schedule: float | None = None
    previous_observed: dict[str, bool] = {}
    previous_values: dict[str, float] = {}
    ar_sum = {field: 0.0 for field in V2_WEATHER_FIELDS if field != "wind_direction_deg"}
    ar_count = {field: 0 for field in V2_WEATHER_FIELDS if field != "wind_direction_deg"}
    for row_index, pre in enumerate(states):
        weather = _find(pre, "current_state", "current_weather")
        schedule = _find(pre, "successor_state", "schedule_reference")
        stage = pre.decision_node.operational_stage.value
        x: list[float] = [
            float(stage in V2_STATE_REALIZED_BY_STAGE[name])
            for name in V2_STATE_FIELDS
        ]
        schedule_time = _field(schedule, "scheduled_departure_utc")
        schedule_minutes = (
            None
            if schedule_time is None
            else (schedule_time - pre.decision_node.decision_time).total_seconds() / 60.0
        )
        schedule_scaled = (
            _scaled(normalization, "schedule.signed_minutes_to_crs_departure", schedule_minutes)
            if schedule_minutes is not None else 0.0
        )
        x.append(schedule_scaled)
        current_values: dict[str, float] = {}
        current_observed: dict[str, bool] = {}
        ceiling_status = _field(weather, "ceiling_status")
        for field in V2_WEATHER_FIELDS:
            raw = _field(weather, field)
            observed = raw is not None
            if field == "ceiling_base_m":
                observed = ceiling_status == "FINITE" and raw is not None
            current_observed[field] = observed
            if field == "wind_direction_deg":
                angle = radians(float(raw)) if observed else 0.0
                x.extend((sin(angle), cos(angle)))
                if observed:
                    current_values[field] = float(raw)
                continue
            value = _scaled(normalization, f"weather.{field}", raw) if observed else 0.0
            x.append(value)
            if observed:
                current_values[field] = value
        for field in V2_WEATHER_FIELDS:
            if field == "wind_direction_deg":
                continue
            valid = current_observed[field] and previous_observed.get(field, False)
            if valid:
                x.append(current_values[field] - previous_values[field])
            else:
                x.append(0.0)
        schedule_delta_valid = schedule_minutes is not None and previous_schedule is not None
        x.append(schedule_scaled - previous_schedule if schedule_delta_valid else 0.0)
        for field in V2_WEATHER_FIELDS:
            if field == "wind_direction_deg":
                continue
            if current_observed[field]:
                ar_sum[field] += current_values[field]
                ar_count[field] += 1
            ar_valid = ar_count[field] == row_index + 1
            x.append(ar_sum[field] / ar_count[field] if ar_valid else 0.0)
        weather_lineage = _lineage(pre, "current_weather")
        schedule_lineage = _lineage(pre, "schedule_reference")
        stale_w, fallback_w = _quality_masks(weather, weather_lineage)
        stale_s, fallback_s = _quality_masks(schedule, schedule_lineage)
        masks: list[float] = []
        for field in V2_WEATHER_FIELDS:
            raw = _field(weather, field)
            missing_mask = (
                ceiling_status == "MISSING"
                if field == "ceiling_base_m"
                else not current_observed[field]
            )
            masks.extend((float(missing_mask), stale_w, fallback_w))
        masks.extend((float(schedule_minutes is None), stale_s, fallback_s))
        for _ in V2_STATE_FIELDS:
            masks.extend((0.0, 0.0, 0.0))
        masks.append(float(ceiling_status == "UNLIMITED"))
        for field in V2_DERIVED_FIELDS:
            if field.startswith("delta.weather."):
                source = field.removeprefix("delta.weather.")
                valid = current_observed.get(source, False) and previous_observed.get(source, False)
            elif field.startswith("ar.weather."):
                source = field.removeprefix("ar.weather.")
                valid = ar_count.get(source, 0) == row_index + 1
            else:
                valid = schedule_delta_valid
            masks.append(float(not valid))
        age = (
            None
            if weather_lineage is None or weather_lineage.age_seconds is None
            else weather_lineage.age_seconds / 60.0
        )
        delta = [
            _scaled(normalization, "weather.observation_age_minutes", age)
            if age is not None else 0.0
        ]
        evidence: list[float] = []
        objects = {"current_weather": weather, "schedule_reference": schedule,
                   "current_state": _state_support_value()}
        for name in V2_OBJECTS:
            value = objects[name]
            evidence.extend(float(value.evidence_class.value == level) for level in EVIDENCE_LEVELS)
        for name in V2_OBJECTS:
            value = objects[name]
            evidence.extend(float(value.support_state.value == level) for level in SUPPORT_LEVELS)
        rows.append(x + masks + delta + evidence)
        previous_schedule = schedule_scaled if schedule_minutes is not None else None
        previous_observed = current_observed
        previous_values = current_values
    result = torch.tensor(rows, dtype=torch.float32)
    if result.shape[1] != len(FEATURE_NAMES_V2):
        raise ContractError(
            f"M1_FEATURE_SCHEMA_ENCODER_MISMATCH:{result.shape[1]}:{len(FEATURE_NAMES_V2)}"
        )
    return result
