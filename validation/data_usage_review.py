"""Format the bounded human-review packet for the Data Usage Contract audit.

This module is deliberately separate from ``data_usage_contract_audit``.  It
only assembles findings for a human gate; it does not edit registries, source,
feature schemas, or scientific configuration.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts" / "diagnostics" / "data_usage_contract_audit" \
    / "AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT.json"
OUTPUT = ROOT / "artifacts" / "diagnostics" / "data_usage_review_packet"
SCHEMA_VERSION = "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET_V1"


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def _audit_rows(audit: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [row for row in audit["raw_column_audit"] if row["status"] == status]


def _raw_review_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "RAW-01",
            "raw_column": "callsign, day",
            "source": "D1-FLIGHTLIST / opensky_flightlist",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "flight identity and offline episode ordering",
            "classification": "MODEL_OR_PRE_USED_NO_RULE",
            "action": "Decide whether D1-OPENSKY-FLIGHT must declare both columns explicitly.",
        },
        {
            "id": "RAW-02",
            "raw_column": "heading, lastposupdate, lastcontact",
            "source": "D1-STATE / opensky_state_vectors",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "predecessor motion canonicalization and observation/contact lineage",
            "classification": "MODEL_OR_PRE_USED_NO_RULE",
            "action": "Decide whether D1-OPENSKY-STATE must declare the projected fields used by the canonicalizer.",
        },
        {
            "id": "RAW-03",
            "raw_column": "station, drct, dwpf, vsby, skyc1..3, skyl1..3, wxcodes, gust",
            "source": "D1-METAR / iem_metar",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "weather units, airport key, cloud/ceiling, present-weather and optional gust decoding",
            "classification": "MODEL_OR_PRE_USED_NO_RULE",
            "action": "Decide whether to expand D1-METAR mapping or split canonical weather rules; gust must remain non-principal unless separately supported.",
        },
        {
            "id": "RAW-04",
            "raw_column": "elevation_ft, type",
            "source": "D1-OURAIRPORTS / ourairports",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "airport reference unit conversion and typed airport metadata",
            "classification": "REFERENCE_BUILD_ONLY",
            "action": "Decide whether these projected reference-build fields should be declared in D1-OURAIRPORTS.",
        },
        {
            "id": "RAW-05",
            "raw_column": "Reporting_Airline, Flight_Number_Reporting_Airline, Cancelled, Diverted",
            "source": "D2-ONTIME / bts_ontime",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "typed carrier/flight identity plus cancellation/diversion filtering",
            "classification": "MODEL_OR_PRE_USED_NO_RULE",
            "action": "Decide whether schedule/actual rules should declare these fields explicitly; no ordinal feature is implied.",
        },
        {
            "id": "RAW-06",
            "raw_column": "ORIGIN, DEST, YEAR, MONTH",
            "source": "D2-T100 / bts_t100",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "segment reference route and month-grain construction",
            "classification": "REFERENCE_BUILD_ONLY",
            "action": "Decide whether these join/period fields should be declared in the T-100 adapter contract.",
        },
        {
            "id": "RAW-07",
            "raw_column": "lat, lon",
            "source": "D2-TIMEZONE / timezone_reference",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "optional typed airport reference metadata carried by timezone canonicalization",
            "classification": "AMBIGUOUS",
            "action": "Decide whether lat/lon belong in the timezone adapter or should be removed from its canonical output.",
        },
        {
            "id": "RAW-08",
            "raw_column": "id, size",
            "source": "D1-EUROSTAT / eurostat JSON-stat",
            "runtime_referenced": True,
            "owner": "PRE",
            "purpose": "JSON-stat dimension decoding for the passenger slice",
            "classification": "AMBIGUOUS",
            "action": "Decide whether these are source-schema metadata that must be declared or a separate payload contract.",
        },
    ]


def _semantic_conflicts() -> list[dict[str, Any]]:
    rows = [
        ("SC-01", "id", "D1-EUROSTAT", "JSON-stat decoder reads dimension metadata.", "Source adapter omits id.", "Contract requires every consumed source field to be declared.", "MISSING_RULE_MISMATCH", "PRE/reference", "Add id to the adapter/payload contract or split the JSON-stat metadata rule.", "HIGH"),
        ("SC-02", "size", "D1-EUROSTAT", "JSON-stat decoder uses dimension sizes for index decoding.", "Source adapter omits size.", "Dimension decoding must be explicit and provenance-linked.", "MISSING_RULE_MISMATCH", "PRE/reference", "Add size to the adapter/payload contract or split the JSON-stat metadata rule.", "HIGH"),
        ("SC-03", "baroaltitude", "D1-STATE", "Canonical predecessor_motion reads baro altitude.", "Primary D1-OPENSKY-STATE rule omits it; only trajectory-event rule lists it.", "Predecessor motion fields require a direct D1 state mapping.", "MISSING_RULE_MISMATCH", "PRE/M1", "Declare the field under D1-OPENSKY-STATE; do not infer it from evaluation-only events.", "HIGH"),
        ("SC-04", "geoaltitude", "D1-STATE", "Canonical predecessor_motion reads geo altitude.", "Primary D1-OPENSKY-STATE rule omits it.", "Predecessor motion fields require a direct D1 state mapping.", "MISSING_RULE_MISMATCH", "PRE/M1", "Declare the field under D1-OPENSKY-STATE.", "HIGH"),
        ("SC-05", "vertrate", "D1-STATE", "Canonical predecessor_motion reads vertical rate.", "Primary D1-OPENSKY-STATE rule omits it.", "Predecessor motion fields require a direct D1 state mapping.", "MISSING_RULE_MISMATCH", "PRE/M1", "Declare the field under D1-OPENSKY-STATE.", "HIGH"),
        ("SC-06", "Tail_Number", "D2-ONTIME", "Schedule canonicalization retains registration and chain construction uses it.", "D2-BTS-SCHEDULE omits Tail_Number; chain/exposure rules mention it separately.", "Aircraft identity is PRE continuity context, never an ordinal feature.", "ROLE_MISMATCH", "PRE/episode", "Confirm one explicit PRE identity/continuity mapping with no numeric M1 encoding.", "HIGH"),
        ("SC-07", "decision_time", "D2-M1-TRAINING-COVERAGE", "Generated M1 training coverage records use decision_time.", "Registry labels it as a raw BTS column.", "Training coverage is a derived artifact, not a raw source field.", "ROLE_MISMATCH", "validation/M1", "Move the fields to a derived coverage-artifact schema; do not add them to the BTS adapter.", "HIGH"),
        ("SC-08", "node_index", "D2-M1-TRAINING-COVERAGE", "Generated decision-node metadata uses node_index.", "Registry labels it as a raw BTS column.", "Node index belongs to PRE decision-node construction.", "ROLE_MISMATCH", "PRE/validation", "Represent node_index as derived PRE lineage, not raw BTS coverage.", "HIGH"),
        ("SC-09", "operational_stage", "D2-M1-TRAINING-COVERAGE", "Stage is derived from cutoff-gated factual replay.", "Registry labels it as a raw BTS column.", "Operational stage is a typed PRE state, not a BTS column.", "ROLE_MISMATCH", "PRE/M1", "Represent stage as derived PRE state and retain the training-coverage rule separately.", "HIGH"),
        ("SC-10", "CLASS", "D2-T100", "T-100 canonicalization reads optional service class.", "D2-T100-CLASS rule uses CLASS but adapter does not declare it.", "Service-class semantics must be explicitly versioned before use.", "MISSING_RULE_MISMATCH", "PRE/reference", "Decide whether CLASS is projected optional metadata or a required T-100 contract field.", "HIGH"),
    ]
    return [
        {"id": item[0], "raw_columns": item[1], "source": item[2],
         "current_code_semantics": item[3], "current_registry_semantics": item[4],
         "data_usage_contract_semantics": item[5], "conflict_type": item[6],
         "affected_module": item[7], "recommended_resolution": item[8],
         "confidence": item[9]}
        for item in rows
    ]


def _registry_conflicts() -> list[dict[str, Any]]:
    return [
        {"id": "REG-01", "rule_id": "D1-EUROSTAT", "current_code_or_contract": "JSON-stat passenger path requires id/size.", "registry_issue": "Source adapter/rule schema omits consumed metadata.", "judgement": "registry stale or incomplete", "recommendation": "Declare id/size in the source/payload contract, or split the payload rule.", "confidence": "HIGH"},
        {"id": "REG-02", "rule_id": "D2-TURNAROUND-REFERENCE", "current_code_or_contract": "PRE static publication writes turnaround_reference in successor_state.", "registry_issue": "pre_family is reference_state.", "judgement": "registry legacy V1 semantics", "recommendation": "Change the registry pre_family to successor_state after human approval; do not patch M1.", "confidence": "HIGH"},
        {"id": "REG-03", "rule_id": "D2-TAXI-REFERENCE", "current_code_or_contract": "PRE static publication writes taxi_reference in successor_state.", "registry_issue": "pre_family is reference_state.", "judgement": "registry legacy V1 semantics", "recommendation": "Change the registry pre_family to successor_state after human approval; preserve train-frozen lineage.", "confidence": "HIGH"},
        {"id": "REG-04", "rule_id": "D2-DOWNSTREAM-EXPOSURE", "current_code_or_contract": "PRE transform rule and M2 typed context consume expected_downstream_exposure.", "registry_issue": "No scientific_variables.yaml definition exists.", "judgement": "registry coverage gap", "recommendation": "Decide whether to add a PRE/reference scientific variable or narrow the rule to the M2 frozen artifact boundary.", "confidence": "MEDIUM"},
        {"id": "REG-05", "rule_id": "D2-M1-TRAINING-COVERAGE", "current_code_or_contract": "Coverage is generated from PRE nodes and labels.", "registry_issue": "raw_columns are synthetic node fields not in the BTS adapter.", "judgement": "registry role error", "recommendation": "Move this to a derived training-coverage artifact contract; do not register synthetic fields as BTS raw columns.", "confidence": "HIGH"},
        {"id": "REG-06", "rule_id": "D2-T100-CLASS", "current_code_or_contract": "Canonicalizer preserves optional service class.", "registry_issue": "CLASS is absent from D2-T100 projected/required columns.", "judgement": "registry adapter gap", "recommendation": "Decide whether CLASS is optional projected metadata or required input, then align adapter and rule.", "confidence": "HIGH"},
    ]


def _pre_output_conflicts() -> list[dict[str, Any]]:
    return [
        {"id": "PRE-01", "pre_variable": "passenger_reference", "current_publication_role": "reference_state via RegistryPREMapper when a legal aggregate record exists", "expected_role": "reference_state / aggregate domain proxy; not flight-level truth", "availability": "REFERENCE_PERIOD", "support_state": "DOMAIN_PROXY or ABSTAIN", "consumer": "M2 and evaluation; Data2 usage docs also list PRE/M1", "first_semantic_divergence": "registry consumer/support alignment between D2 passenger rules and scientific_variables.yaml", "recommended_resolution": "Confirm the intended consumer set before changing publication or M1 usage."},
        {"id": "PRE-02", "pre_variable": "turnaround_reference", "current_publication_role": "successor_state static MODEL_FEATURE with reference lineage", "expected_role": "successor_state static train-frozen reference", "availability": "REFERENCE_PERIOD / post-hoc fit, frozen at use", "support_state": "SUPPORTED or ABSTAIN", "consumer": "M1, M2", "first_semantic_divergence": "D2-TURNAROUND-REFERENCE registry pre_family says reference_state", "recommended_resolution": "Resolve registry pre_family only; retain current PRE publication path."},
        {"id": "PRE-03", "pre_variable": "taxi_reference", "current_publication_role": "successor_state static MODEL_FEATURE with reference lineage", "expected_role": "successor_state static train-frozen reference", "availability": "REFERENCE_PERIOD / post-hoc fit, frozen at use", "support_state": "SUPPORTED or ABSTAIN", "consumer": "M1, M2", "first_semantic_divergence": "D2-TAXI-REFERENCE registry pre_family says reference_state", "recommended_resolution": "Resolve registry pre_family only; preserve zero-coverage ABSTAIN semantics."},
        {"id": "PRE-04", "pre_variable": "segment_reference", "current_publication_role": "reference_state aggregate reference when mapped", "expected_role": "reference_state DEVELOPMENT_FROZEN aggregate proxy", "availability": "REFERENCE_PERIOD", "support_state": "SUPPORTED or ABSTAIN", "consumer": "M2, M3, evaluation only", "first_semantic_divergence": "D2-T100-CLASS adapter/rule schema mismatch before PRE publication", "recommended_resolution": "Align T-100 CLASS schema first; do not patch M2 consumer code."},
    ]


def _decisions() -> list[dict[str, Any]]:
    return [
        {"id": "DUC-01", "question": "M2 timezone handling should be owned by which boundary?", "options": {"A": "PRE produces canonical train rows or a typed timezone-backed artifact; M2 consumes only that artifact.", "B": "M2 may read the shared timezone table through a formally approved adapter.", "C": "Retain the current M2 raw read."}, "recommendation": "A", "reason": "The current read exists only to support PRE HHMM-to-UTC conversion in collect_train_rows; M2 has no independent timezone semantics."},
        {"id": "DUC-02", "question": "How should the declared factual replay projection be represented?", "options": {"A": "Register D2-BTS-FACTUAL-REPLAY as a separate projection rule while preserving D2-BTS-ACTUAL as POSTHOC_ONLY/EVAL_OUTCOME.", "B": "Keep the runtime rule unregistered until after training.", "C": "Rewrite D2-BTS-ACTUAL to be inference evidence."}, "recommendation": "A", "reason": "The projection is already role-separated in code and must not mutate source outcome semantics."},
        {"id": "DUC-03", "question": "How should D1-METAR fields used by the canonicalizer but absent from the rule be handled?", "options": {"A": "Expand or split the PRE-owned D1-METAR mapping, retaining gust as non-principal unless supported.", "B": "Remove the canonical weather parsing for those fields.", "C": "Register every projected field as an M1 feature."}, "recommendation": "A", "reason": "The fields are consumed for canonical weather semantics, but raw mapping coverage does not imply principal feature promotion."},
        {"id": "DUC-04", "question": "What is the T-100 CLASS contract?", "options": {"A": "Optional projected metadata with an explicit rule and adapter declaration.", "B": "Remove D2-T100-CLASS.", "C": "Make CLASS a required field for every T-100 row."}, "recommendation": "A", "reason": "The current canonicalizer treats service class as optional; the schema should say so explicitly."},
        {"id": "DUC-05", "question": "Which PRE family owns train-frozen turnaround and taxi references?", "options": {"A": "successor_state, matching current static publication.", "B": "reference_state, preserving the current registry labels.", "C": "Both, with duplicate publication."}, "recommendation": "A", "reason": "Current PRE publishes both numeric references into successor_state and M1 consumes that typed publication."},
        {"id": "DUC-06", "question": "How should expected_downstream_exposure be represented in the scientific registry?", "options": {"A": "Add a PRE/reference scientific variable with typed M2 lineage.", "B": "Keep it only as an M2 frozen artifact and narrow registry consumers.", "C": "Remove the frozen exposure reference."}, "recommendation": "B", "reason": "Current formal M2 consumption is through a typed frozen reference bundle; no M1 principal feature currently consumes it."},
        {"id": "DUC-07", "question": "How should synthetic M1 training-coverage fields be represented?", "options": {"A": "Derived coverage-artifact schema, separate from raw BTS adapter columns.", "B": "Add the synthetic fields to the BTS source adapter.", "C": "Delete the coverage rule."}, "recommendation": "A", "reason": "decision_time, node_index, and operational_stage are generated PRE/node metadata."},
    ]


def _auto_resolution() -> dict[str, Any]:
    return {
        "NAME_ONLY_MISMATCH": [],
        "STALE_LEGACY_SEMANTICS": [
            "D2-TURNAROUND-REFERENCE pre_family=reference_state",
            "D2-TAXI-REFERENCE pre_family=reference_state",
        ],
        "UNUSED_RAW_COLUMN": [
            "D1-FLIGHTLIST: number, registration, typecode",
            "D1-STATE: callsign",
            "D2-DB1B: MktFare",
            "D2-ISD: CALL_SIGN, SLP",
        ],
        "DIAGNOSTIC_ONLY": [
            "D2-ISD: REPORT_TYPE quality flag",
            "D2-M1-TRAINING-COVERAGE: decision_time, node_index, operational_stage are derived metadata",
        ],
        "REFERENCE_BUILD_ONLY": [
            "D1-OURAIRPORTS: elevation_ft, type",
            "D2-T100: ORIGIN, DEST, YEAR, MONTH",
        ],
        "automatic_action": "NO_REGISTRY_OR_CODE_CHANGE",
    }


def _markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET_V1",
        "",
        f"Status: **{packet['status']}**",
        "",
        "This packet is diagnostic only. It does not freeze a registry, modify the M1 feature contract, authorize training, tuning, Gate B, or Final Test.",
        "",
        "## PRE Bypass",
        "",
        "1. `model/M2/freeze.py:119-124`, `load_timezones(root)` reads `iata` and `timezone` from `data2/refs/us_airport_timezones.csv`. `build_m2_data2_formal_registry()` calls it at line 280, then passes the table into PRE-owned `collect_train_rows()` (`model/PRE/reference/data2_m2_train_fit.py:67-91`).",
        "   - Scientific variable: `airport_timezone`",
        "   - Why M2 needs it: local BTS HHMM to UTC conversion during train-row preparation",
        "   - Current transformation: raw timezone CSV -> dict[IATA, IANA] -> `canonicalize_ontime_row`",
        "   - Current output: canonical train rows, frozen M2 references, train scales, and M2 formal registry",
        "   - Downstream usage: M2 formal artifact construction; no direct M2 timezone feature",
        "   - Classification: **C — local-time conversion only**",
        "   - Recommendation: PRE-owned canonical train artifact or typed timezone-backed preparation artifact; M2 consumes only that artifact.",
        "",
        "## Runtime Rule Registration",
        "",
        "`D2-BTS-FACTUAL-REPLAY` is a candidate separate projection rule. `D2-BTS-ACTUAL` remains `POSTHOC_ONLY` / `EVAL_OUTCOME`.",
        "",
        "```yaml",
        "rule_id: D2-BTS-FACTUAL-REPLAY",
        "dataset_id: data2_2019",
        "source_rule: D2-BTS-ACTUAL",
        "raw_source_role: POSTHOC_COMPLETED_OPERATIONAL_EVENT",
        "projection_role: DECLARED_RETROSPECTIVE_FACTUAL_REPLAY",
        "principal_declared_lag_minutes: 0",
        "availability_semantics: event_time + declared_lag",
        "observed_message_arrival: false",
        "production_availability_claim: false",
        "decision_time_role: INFERENCE_EVIDENCE_UNDER_DECLARED_REPLAY",
        "downstream: [PRE, M1, Exp3]",
        "source_outcome_role_preserved: true",
        "final_test_access_count: 0",
        "```",
        "",
        "## Raw Columns Requiring Human Decision",
        "",
    ]
    for row in packet["raw_columns_requiring_human_decision"]:
        lines.append(f"- **{row['id']}** `{row['source']}` — `{row['raw_column']}`; `{row['classification']}`. {row['action']}")
    lines.extend(["", "## Semantic Conflicts Requiring Human Decision", ""])
    for row in packet["semantic_conflicts_requiring_human_decision"]:
        lines.append(f"- **{row['id']}** `{row['source']}` / `{row['raw_columns']}` — `{row['conflict_type']}`; affected `{row['affected_module']}`. Resolution: {row['recommended_resolution']}")
    lines.extend(["", "## Registry Conflicts Requiring Human Decision", ""])
    for row in packet["registry_conflicts_requiring_human_decision"]:
        lines.append(f"- **{row['id']}** `{row['rule_id']}` — {row['judgement']}. {row['recommendation']}")
    lines.extend(["", "## PRE Output Conflicts Requiring Human Decision", ""])
    for row in packet["pre_output_conflicts_requiring_human_decision"]:
        lines.append(f"- **{row['id']}** `{row['pre_variable']}` — current `{row['current_publication_role']}`; expected `{row['expected_role']}`. First divergence: {row['first_semantic_divergence']}")
    lines.extend(["", "## Automatically Resolvable / No Action", ""])
    for key, values in packet["automatically_resolvable"].items():
        lines.append(f"- **{key}**: {', '.join(values) if isinstance(values, list) and values else 'none'}")
    lines.extend(["", "## Answerable Decisions", ""])
    for decision in packet["decisions"]:
        lines.append(f"### {decision['id']}")
        lines.append(f"Question: {decision['question']}")
        lines.append(f"Recommendation: **{decision['recommendation']}**")
        lines.append(f"Reason: {decision['reason']}")
        lines.append("Options: " + "; ".join(f"{key}={value}" for key, value in decision["options"].items()))
        lines.append("")
    lines.extend([
        "## Safety Boundary",
        "",
        "- `M1_TRAINING_RUNS = 0`",
        "- `TUNING_RUNS = 0`",
        "- `FINAL_TEST_ACCESS_COUNT = 0`",
        "- `PAPER_FULL_RUN = false`",
        "- `GATE_B_ENTERED = false`",
        "",
        "Stop at human review. No automatic batch repair was performed.",
        "",
    ])
    return "\n".join(lines)


def run(audit_path: Path = AUDIT, output_dir: Path = OUTPUT) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "DATA_USAGE_REVIEW_PACKET_READY",
        "authority": "NON_AUTHORITATIVE_HUMAN_REVIEW_PACKET",
        "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_audit_artifact_hash": audit.get("artifact_hash"),
        "source_audit_status": audit.get("status"),
        "pre_bypass": {
            "file": "model/M2/freeze.py",
            "function": "load_timezones",
            "raw_columns": ["iata", "timezone"],
            "scientific_variable": "airport_timezone",
            "why_m2_needs_it": "local BTS HHMM to UTC conversion for PRE train-row preparation",
            "current_transformation": "timezone CSV -> dict[IATA, IANA] -> canonicalize_ontime_row",
            "current_output": "canonical train rows and frozen M2 reference/scale artifacts",
            "downstream_usage": "M2 formal registry construction",
            "classification": "C",
            "recommended_resolution": "PRE-owned typed/canonical preparation artifact; M2 consumes the artifact",
            "locations": ["model/M2/freeze.py:119-124", "model/M2/freeze.py:273-282", "model/PRE/reference/data2_m2_train_fit.py:67-91"],
        },
        "runtime_rule_registration": {
            "candidate_status": "HUMAN_REVIEW_REQUIRED",
            "candidate_entry": {
                "rule_id": "D2-BTS-FACTUAL-REPLAY",
                "dataset_id": "data2_2019",
                "source_rule": "D2-BTS-ACTUAL",
                "raw_source_role": "POSTHOC_COMPLETED_OPERATIONAL_EVENT",
                "projection_role": "DECLARED_RETROSPECTIVE_FACTUAL_REPLAY",
                "principal_declared_lag_minutes": 0,
                "availability_semantics": "event_time + declared_lag",
                "observed_message_arrival": False,
                "production_availability_claim": False,
                "decision_time_role": "INFERENCE_EVIDENCE_UNDER_DECLARED_REPLAY",
                "downstream": ["PRE", "M1", "Exp3"],
                "source_outcome_role_preserved": True,
                "final_test_access_count": 0,
            },
            "preserve_source_rule": {"rule_id": "D2-BTS-ACTUAL", "availability_rule": "posthoc_only", "decision_time_role": "EVAL_OUTCOME"},
        },
        "raw_columns_requiring_human_decision": _raw_review_rows(),
        "semantic_conflicts_requiring_human_decision": _semantic_conflicts(),
        "registry_conflicts_requiring_human_decision": _registry_conflicts(),
        "pre_output_conflicts_requiring_human_decision": _pre_output_conflicts(),
        "automatically_resolvable": _auto_resolution(),
        "decisions": _decisions(),
        "safety": {"M1_TRAINING_RUNS": 0, "TUNING_RUNS": 0, "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "GATE_B_ENTERED": False},
        "artifact_hash_basis": "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH",
    }
    packet["counts"] = {
        "raw_columns_human_review": len(packet["raw_columns_requiring_human_decision"]),
        "semantic_conflicts_human_review": len(packet["semantic_conflicts_requiring_human_decision"]),
        "registry_conflicts_human_review": len(packet["registry_conflicts_requiring_human_decision"]),
        "pre_output_conflicts_human_review": len(packet["pre_output_conflicts_requiring_human_decision"]),
        "decisions": len(packet["decisions"]),
    }
    packet["artifact_hash"] = _hash(packet)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.json"
    md_path = output_dir / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.md"
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(packet), encoding="utf-8")
    packet["artifacts"] = {"json": json_path.relative_to(output_dir).as_posix(), "markdown": md_path.relative_to(output_dir).as_posix()}
    # Re-write JSON once with the stable artifact index included in the payload.
    packet["artifact_hash"] = _hash({key: value for key, value in packet.items() if key != "artifact_hash"})
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.audit, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
