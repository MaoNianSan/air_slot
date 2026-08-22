"""Feature inventory and encoder semantics for M1 V2 Feature Gate B1."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from model.M1 import data as m1_data


SEMANTIC_GROUPS = (
    "CURRENT_STATE",
    "CURRENT_SCHEDULE",
    "CURRENT_WEATHER",
    "LOCAL_DELTA",
    "AR_SUMMARY",
    "RAW_MISSING_MASK",
    "STALE_MASK",
    "FALLBACK_MASK",
    "DERIVED_MISSING_MASK",
    "CEILING_STATUS",
    "OBSERVATION_AGE",
    "EVIDENCE_ENCODING",
    "SUPPORT_ENCODING",
    "STATIC_REFERENCE",
)


def semantic_group(name: str) -> str:
    if name in m1_data.STATIC_FEATURE_NAMES:
        return "STATIC_REFERENCE"
    if name.endswith(".derived_missing_mask"):
        return "DERIVED_MISSING_MASK"
    if name.endswith(".unlimited_mask"):
        return "CEILING_STATUS"
    if name.endswith(".missing_mask"):
        return "RAW_MISSING_MASK"
    if name.endswith(".stale_mask"):
        return "STALE_MASK"
    if name.endswith(".fallback_mask"):
        return "FALLBACK_MASK"
    if ".evidence." in name:
        return "EVIDENCE_ENCODING"
    if ".support." in name:
        return "SUPPORT_ENCODING"
    if name == "weather.observation_age_minutes":
        return "OBSERVATION_AGE"
    if name.startswith("state."):
        return "CURRENT_STATE"
    if name.startswith("delta."):
        return "LOCAL_DELTA"
    if name.startswith("ar."):
        return "AR_SUMMARY"
    if name.startswith("schedule."):
        return "CURRENT_SCHEDULE"
    if name.startswith("weather."):
        return "CURRENT_WEATHER"
    raise ValueError(f"M1_B1_FEATURE_GROUP_UNKNOWN:{name}")


def feature_inventory() -> dict:
    dynamic = tuple(m1_data.FEATURE_NAMES_V2)
    static = tuple(m1_data.STATIC_FEATURE_NAMES)
    grouped = {group: [] for group in SEMANTIC_GROUPS}
    for index, name in enumerate(dynamic):
        grouped[semantic_group(name)].append(
            {"ordered_index": index, "feature": name, "branch": "dynamic"}
        )
    for offset, name in enumerate(static, start=len(dynamic)):
        grouped[semantic_group(name)].append(
            {"ordered_index": offset, "feature": name, "branch": "static"}
        )
    return {
        "source": "model/M1/data.py",
        "dynamic_count": len(dynamic),
        "static_count": len(static),
        "total_count": len(dynamic) + len(static),
        "ordered_dynamic_features": list(dynamic),
        "ordered_static_features": list(static),
        "ordered_all_features": list(dynamic + static),
        "groups": grouped,
    }


def _weather_field(name: str) -> str:
    for field in m1_data.V2_WEATHER_FIELDS:
        if field in name:
            return field
    return "observation_age_minutes"


def _semantic_row(name: str) -> dict:
    group = semantic_group(name)
    source = "PRE metadata"
    unit = "binary"
    transformation = "ONE_HOT"
    normalization = "BINARY_NO_SCALE"
    validity = "ALWAYS_DEFINED_BY_ENCODER"
    missing = "NOT_APPLICABLE"
    history = "CURRENT_ONLY"
    role = "QUALITY_OR_PROVENANCE_ENCODING"

    if group == "CURRENT_STATE":
        source = "decision_node.operational_stage"
        transformation = "FACTUAL_STAGE_CONTRACTION_TO_REALIZED_FLAG"
        role = "FACTUAL_OPERATIONAL_STATE"
    elif group == "CURRENT_SCHEDULE":
        source = "successor_state.schedule_reference.scheduled_departure_utc"
        unit = "train_standard_deviation"
        transformation = "SIGNED_MINUTES_TO_CRS_DEPARTURE"
        normalization = "TRAIN_STANDARDIZED"
        validity = "SCHEDULED_DEPARTURE_PRESENT"
        missing = "ZERO_NEUTRAL_WITH_RAW_MISSING_MASK"
        role = "CURRENT_SCHEDULE_POSITION"
    elif group == "CURRENT_WEATHER":
        field = _weather_field(name)
        source = f"current_state.current_weather.{field}"
        unit = "unitless" if name.endswith((".sin", ".cos")) else "train_standard_deviation"
        transformation = (
            "CIRCULAR_SIN_COS_PAIR"
            if name.endswith((".sin", ".cos"))
            else "CURRENT_CANONICAL_VALUE"
        )
        normalization = (
            "SIN_COS_NO_SCALE"
            if name.endswith((".sin", ".cos"))
            else "TRAIN_STANDARDIZED"
        )
        validity = (
            "FINITE_CEILING_ONLY"
            if field == "ceiling_base_m"
            else "RAW_FIELD_PRESENT"
        )
        missing = (
            "ZERO_WITH_FINITE_UNLIMITED_MISSING_THREE_STATE"
            if field == "ceiling_base_m"
            else "ZERO_NEUTRAL_WITH_RAW_MISSING_MASK"
        )
        role = "CURRENT_WEATHER_STATE"
    elif group == "LOCAL_DELTA":
        source = name.removeprefix("delta.")
        unit = "train_standard_deviation_difference"
        transformation = "DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES"
        normalization = "DERIVED_FROM_STANDARDIZED"
        validity = "CURRENT_AND_IMMEDIATELY_PREVIOUS_LEGAL_NODE_OBSERVED"
        missing = "ZERO_WITH_DERIVED_MISSING_MASK"
        history = "PREVIOUS_NODE_LOCAL"
        role = "LOCAL_CHANGE"
    elif group == "AR_SUMMARY":
        source = name.removeprefix("ar.")
        unit = "train_standard_deviation"
        transformation = "FULL_PREFIX_CUMULATIVE_MEAN_OF_TRAIN_STANDARDIZED_VALUES"
        normalization = "DERIVED_FROM_STANDARDIZED"
        validity = "EVERY_PREFIX_NODE_OBSERVED"
        missing = "ZERO_WITH_DERIVED_MISSING_MASK"
        history = "FULL_PREFIX_SUMMARY"
        role = "ENGINEERED_LONG_HISTORY_SUMMARY"
    elif group in {"RAW_MISSING_MASK", "STALE_MASK", "FALLBACK_MASK"}:
        source = (
            "variable_lineage.current_weather"
            if name.startswith("current_weather.")
            else name.rsplit(".", 1)[0]
        )
        transformation = group
        role = "FIELD_OR_OBJECT_QUALITY_MASK"
    elif group == "DERIVED_MISSING_MASK":
        source = name.removesuffix(".derived_missing_mask")
        transformation = "DERIVED_VALIDITY_NEGATION"
        history = (
            "FULL_PREFIX_SUMMARY" if name.startswith("ar.") else "PREVIOUS_NODE_LOCAL"
        )
        role = "DERIVED_FEATURE_VALIDITY"
    elif group == "CEILING_STATUS":
        source = "current_state.current_weather.ceiling_status"
        transformation = "CEILING_STATUS_EQUALS_UNLIMITED"
        role = "CEILING_THREE_STATE_ENCODING"
    elif group == "OBSERVATION_AGE":
        source = "variable_lineage.current_weather.age_seconds"
        unit = "train_standard_deviation"
        transformation = "AGE_SECONDS_TO_MINUTES"
        normalization = "TRAIN_STANDARDIZED"
        validity = "CURRENT_WEATHER_LINEAGE_AGE_PRESENT"
        missing = "ZERO_WITHOUT_DEDICATED_AGE_MASK"
        role = "OBSERVATION_FRESHNESS"
    elif group == "EVIDENCE_ENCODING":
        source = name.split(".evidence.", 1)[0] + ".evidence_class"
        role = "SOURCE_PROVENANCE_CLASS"
    elif group == "SUPPORT_ENCODING":
        source = name.split(".support.", 1)[0] + ".support_state"
        role = "OBJECT_SUPPORT_STATE"
    elif group == "STATIC_REFERENCE":
        source = (
            "successor_state.turnaround_reference.value"
            if name.startswith("turnaround")
            else "successor_state.taxi_reference.value"
        )
        if name.endswith(".missing_mask"):
            unit = "binary"
            transformation = "PER_FEATURE_REFERENCE_MISSINGNESS"
            normalization = "BINARY_NO_SCALE"
            validity = "ALWAYS_DEFINED_BY_ENCODER"
            missing = "NOT_APPLICABLE"
            role = "STATIC_REFERENCE_VALIDITY"
        else:
            unit = "train_standard_deviation"
            transformation = "TRAIN_EPISODE_LEVEL_STANDARDIZED_REFERENCE_VALUE"
            normalization = "TRAIN_STANDARDIZED"
            validity = "PUBLISHED_MODEL_FEATURE_WITH_REFERENCE_ID_AND_FREEZE_ID"
            missing = "ZERO_NEUTRAL_WITH_PER_FEATURE_MISSING_MASK"
            role = "STATIC_OPERATIONAL_REFERENCE"
        history = "STATIC_REFERENCE"

    return {
        "FEATURE": name,
        "SOURCE_PRE_VARIABLE": source,
        "SEMANTIC_GROUP": group,
        "UNIT": unit,
        "TRANSFORMATION": transformation,
        "NORMALIZATION": normalization,
        "VALIDITY_RULE": validity,
        "MISSING_ENCODING": missing,
        "HISTORY_SCOPE": history,
        "EXPECTED_INFORMATION_ROLE": role,
        "NUMERIC_OR_METADATA_ROLE": "PRINCIPAL_NUMERIC",
    }


def semantic_table() -> list[dict]:
    return [
        _semantic_row(name)
        for name in (*m1_data.FEATURE_NAMES_V2, *m1_data.STATIC_FEATURE_NAMES)
    ]


def _contains_zero_tuple_extend(node: ast.For) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        if child.func.attr != "extend" or not child.args:
            continue
        value = child.args[0]
        if not isinstance(value, (ast.Tuple, ast.List)) or len(value.elts) != 3:
            continue
        if all(isinstance(item, ast.Constant) and item.value == 0.0 for item in value.elts):
            return True
    return False


def encoder_static_scan() -> dict:
    source_lines, start_line = inspect.getsourcelines(m1_data.encode_pre_sequence)
    tree = ast.parse("".join(source_lines))
    structural_line = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.iter, ast.Name):
            continue
        if node.iter.id == "V2_STATE_FIELDS" and _contains_zero_tuple_extend(node):
            structural_line = start_line + node.lineno - 1
            break
    features = [
        f"state.{field}.{kind}_mask"
        for field in m1_data.V2_STATE_FIELDS
        for kind in ("missing", "stale", "fallback")
    ]
    return {
        "encoder_source": str(Path(inspect.getsourcefile(m1_data.encode_pre_sequence) or "")),
        "ast_structural_zero_loop_found": structural_line is not None,
        "source_line": structural_line,
        "classification": "STRUCTURAL_CONSTANT",
        "features": features if structural_line is not None else [],
        "recommendation": "REMOVE",
    }


def history_semantics() -> dict:
    return {
        "delta": {
            "history_scope": "PREVIOUS_NODE_LOCAL",
            "previous_node_definition": "IMMEDIATELY_PREVIOUS_CONTIGUOUS_FIVE_MINUTE_NODE",
            "transformation": "DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES",
            "schedule_transformation": "DIFFERENCE_OF_TRAIN_STANDARDIZED_VALUES",
        },
        "AR_ACTUAL_SEMANTICS": {
            "classification": "REMOVED_BY_B1_D05",
            "window_start": None,
            "window_end": None,
            "minimum_valid_count": None,
            "missing_propagation": None,
            "full_prefix": False,
            "cumulative_mean": False,
            "true_autoregressive_statistic": False,
            "human_review_required": False,
        },
        "FULL_PREFIX_HISTORY_FEATURE_COUNT": sum(
            _semantic_row(name)["HISTORY_SCOPE"] == "FULL_PREFIX_SUMMARY"
            for name in m1_data.FEATURE_NAMES_V2
        ),
        "EXP1B_HISTORY_SEPARATION_STATUS": "CLEAN",
        "exp1b_reason": (
            "r_fast contains current and previous-node-local features only; "
            "ADAPTIVE history enters the history-conditioned branch through GRU(history)."
        ),
    }


__all__ = [
    "SEMANTIC_GROUPS",
    "encoder_static_scan",
    "feature_inventory",
    "history_semantics",
    "semantic_group",
    "semantic_table",
]
