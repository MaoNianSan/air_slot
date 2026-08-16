from __future__ import annotations

from collections import Counter

from model.common.errors import ContractError


SUPPORT_TRANSITIONS = {"PRESERVED", "DEGRADED", "ABSTAIN", "UNSUPPORTED"}
RAW_SCHEMA_TOKENS = {
    "icao24", "firstseen", "lastseen", "metar", "callsign", "tail_number",
    "crsdeptime", "depdelayminutes", "taxiout",
}


def classify_support_transition(data2_state: str, data1_state: str) -> str:
    if data1_state == "UNSUPPORTED":
        return "UNSUPPORTED"
    if data1_state == "ABSTAIN":
        return "ABSTAIN"
    if data1_state == data2_state:
        return "PRESERVED"
    return "DEGRADED"


def support_transition_metrics(rows) -> dict:
    transitions = [classify_support_transition(row["data2_support"], row["data1_support"])
                   for row in rows]
    counts = Counter(transitions)
    n = len(transitions)
    return {
        "SupportTransitionRate": {name: (counts[name] / n if n else None)
                                  for name in sorted(SUPPORT_TRANSITIONS)},
        "DowngradeRate": None if not n else sum(name != "PRESERVED" for name in transitions) / n,
        "episode_denominator": n,
    }


def portability_hard_gates(*, substitutions=(), downstream_names=()) -> dict:
    silent = tuple(item for item in substitutions if not item.get("declared", False))
    redefinitions = tuple(item for item in downstream_names
                          if str(item).lower() in {"schedule_like", "turnaround_like", "proxy_as_schedule"})
    return {
        "SilentSubstitutionCount": len(silent),
        "DownstreamSemanticRedefinitionCount": len(redefinitions),
        "DATA1_PORTABILITY_STATUS": "PASS" if not silent and not redefinitions else "FAIL",
    }


def assert_downstream_schema_localization(source_text_by_path: dict[str, str]) -> None:
    leaked = []
    for path, source in source_text_by_path.items():
        lower = source.lower()
        for token in RAW_SCHEMA_TOKENS:
            if token in lower:
                leaked.append(f"{path}:{token}")
    if leaked:
        raise ContractError("DATASET_RAW_SCHEMA_LEAK:" + ",".join(sorted(leaked)))
