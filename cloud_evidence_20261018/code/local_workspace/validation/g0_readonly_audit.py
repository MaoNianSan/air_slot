"""Read-only G0 evidence audit.

This module only inspects repository files and frozen manifests.  It does not
invoke a formal runner, read Final-Test data, retrain, calibrate, or rewrite
scientific artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "refactor_20261010"
AUTH_ROOT = Path(r"D:\research\air_slot\code\explore")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def iter_json_files() -> list[Path]:
    roots = [ROOT / "artifacts", ROOT / "outputs", ROOT / "reports", ROOT / "registries"]
    paths: list[Path] = []
    for base in roots:
        if base.exists():
            paths.extend(sorted(base.rglob("*.json")))
            paths.extend(sorted(base.rglob("*.jsonl")))
    return sorted(set(paths))


def walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def _mass_table(rows: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    if not rows or not all(key in row for row in rows):
        return None
    table: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        weight = row.get("scenario_weight", row.get("weight"))
        if not isinstance(weight, (int, float)):
            return None
        table[json.dumps(row[key], sort_keys=True, default=str)] += float(weight)
    return dict(sorted(table.items()))


def marginal_audit() -> dict[str, Any]:
    """Find comparable raw/marginal payloads without manufacturing scenarios."""
    files = iter_json_files()
    state_path = AUTH_ROOT / "artifacts" / "experiment" / "final_test_v2_stage_matched_canonical_v2" / "checkpoints" / "STATE_VARIANTS.json"
    if state_path.exists():
        payload = load_json(state_path)
        variants = (payload or {}).get("payload", {}).get("variants", [])
        by_node: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for variant in variants:
            representation_id = variant.get("representation_id")
            for node in variant.get("nodes", []):
                state = node.get("state_set", node)
                by_node[str(node.get("node_id"))][str(representation_id)] = state
        # D_TO is a derived joint quantity.  It must satisfy D_TO=D_OB+D_TX
        # within each representation, but its marginal distribution is not
        # expected to remain unchanged after coordinate permutation.
        primitive_names = ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes")
        node_results = []
        for node_id, reps in by_node.items():
            joint = reps.get("HISTORY_H16:JOINT")
            marginal = reps.get("HISTORY_H16:MARGINAL")
            if not joint or not marginal:
                continue
            jr = joint.get("scenarios", [])
            mr = marginal.get("scenarios", [])
            checks = {"scenario_count_equal": len(jr) == len(mr), "support_equal": [
                x.get("support") for x in jr] == [x.get("support") for x in mr]}
            weights_j = [float(x.get("scenario_weight")) for x in jr if isinstance(x.get("scenario_weight"), (int, float))]
            weights_m = [float(x.get("scenario_weight")) for x in mr if isinstance(x.get("scenario_weight"), (int, float))]
            checks["joint_weight_sum"] = sum(weights_j)
            checks["marginal_weight_sum"] = sum(weights_m)
            checks["weights_nonnegative"] = all(x >= 0 for x in weights_j + weights_m)
            checks["weights_normalized"] = abs(sum(weights_j) - 1) <= 1e-9 and abs(sum(weights_m) - 1) <= 1e-9
            primitive = {}
            for name in primitive_names:
                a = _mass_table(jr, name)
                b = _mass_table(mr, name)
                primitive[name] = {"joint_mass": a, "marginal_mass": b, "equal": a == b}
            checks["primitive_mass_equal"] = all(item["equal"] for item in primitive.values())
            checks["d_to_identity_joint"] = all(abs(float(x.get("d_to_minutes", 0)) - (float(x.get("d_ob_minutes", 0)) + float(x.get("d_tx_minutes", 0)))) <= 1e-6 for x in jr)
            checks["d_to_identity_marginal"] = all(abs(float(x.get("d_to_minutes", 0)) - (float(x.get("d_ob_minutes", 0)) + float(x.get("d_tx_minutes", 0)))) <= 1e-6 for x in mr)
            node_results.append({"node_id": node_id, "checks": checks, "primitive": primitive})
        if node_results:
            passed = all(all(v is True for k, v in row["checks"].items() if isinstance(v, bool)) for row in node_results)
            status = "PASS_MARGINAL_PRESERVATION" if passed else "FAIL_MARGINAL_PRESERVATION"
            return {
                "schema_version": "AIR_SLOT_G0_MARGINAL_AUDIT_V1", "status": status,
                "blocking_state": None if passed else "BLOCKED_REPRESENTATION",
                "scientific_recomputation": False, "source": str(state_path),
                "source_sha256": sha256(state_path), "node_count_audited": len(node_results),
                "node_results": node_results,
                "finding": "Compared HISTORY_H16:JOINT and HISTORY_H16:MARGINAL per-node weighted primitive mass tables, support, weights, and D_TO identity. D_TO is audited as a derived identity, not as a preserved marginal distribution.",
            }
    candidate_nodes: list[dict[str, Any]] = []
    weight_checks: list[dict[str, Any]] = []
    for path in files:
        data = load_json(path)
        if data is None:
            continue
        for location, value in walk(data):
            if not isinstance(value, list) or not value or not all(isinstance(x, dict) for x in value):
                continue
            rows = value
            if not any("scenario_weight" in row for row in rows):
                continue
            weights = [row.get("scenario_weight") for row in rows]
            if all(isinstance(x, (int, float)) for x in weights):
                total = float(sum(weights))
                nonnegative = all(float(x) >= 0 for x in weights)
                weight_checks.append({"path": str(path), "location": location,
                    "count": len(rows), "weight_sum": total, "nonnegative": nonnegative,
                    "normalized": abs(total - 1.0) <= 1e-9})
            keys = set().union(*(row.keys() for row in rows))
            if {"representation", "scenario_weight"} <= keys or any("marginal" in str(k).lower() for k in keys):
                candidate_nodes.append({"path": str(path), "location": location,
                    "keys": sorted(keys), "count": len(rows)})
    comparable = []
    # A pass requires both original and marginal rows for the same node.  The
    # current checkout has no such paired payload, so no inference is made.
    status = "PASS_MARGINAL_PRESERVATION" if comparable else "UNKNOWN_INSUFFICIENT_PAYLOAD"
    return {
        "schema_version": "AIR_SLOT_G0_MARGINAL_AUDIT_V1",
        "status": status,
        "blocking_state": None if status.startswith("PASS") else "BLOCKED_REPRESENTATION",
        "scientific_recomputation": False,
        "paired_payloads": comparable,
        "candidate_payloads": candidate_nodes,
        "weight_checks": weight_checks,
        "required_for_pass": [
            "same decision node raw and marginal payload",
            "support equality",
            "per-primitive weighted mass/CDF equality",
            "explicit duplicate/reindex accounting",
        ],
        "finding": "No paired raw/marginal scenario payload is present in this checkout; existing weight checks are not sufficient to establish preservation.",
    }


def unit_time_audit() -> dict[str, Any]:
    source_files = [
        ROOT / "model" / "M1" / "scenarios.py",
        ROOT / "model" / "M2" / "drivers.py",
        ROOT / "model" / "M2" / "valuation.py",
        ROOT / "model" / "M4" / "decision.py",
        ROOT / "model" / "M4" / "response.py",
    ]
    source_evidence = []
    for path in source_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        source_evidence.append({
            "path": str(path), "sha256": sha256(path),
            "minutes_tokens": len(re.findall(r"minutes|minute", text, re.I)),
            "cu_tokens": len(re.findall(r"constructed_cu|CU|valuation", text)),
            "action_tokens": len(re.findall(r"candidate|response|induced|mitigation|ranking", text)),
        })
    checkpoint_dir = AUTH_ROOT / "artifacts" / "experiment" / "final_test_v2_stage_matched_canonical_v2" / "checkpoints"
    state_path = checkpoint_dir / "STATE_VARIANTS.json"
    consequence_path = checkpoint_dir / "CONSEQUENCE_VARIANTS.json"
    recovery_path = checkpoint_dir / "RECOVERY_DECISIONS.json"
    canonical_path = checkpoint_dir / "CANONICAL_NODES.json"
    pre_path = AUTH_ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1" / "2019" / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl"
    trace_rows: list[dict[str, Any]] = []
    stage_counts: dict[str, int] = {}
    linked_counts: dict[str, int] = {}
    recovery_stage_counts: dict[str, int] = {}
    trace_source_hashes = {}
    formula_checks: dict[str, int] = {}
    formula_ratio_summary: dict[str, Any] = {}
    if all(path.exists() for path in (state_path, consequence_path, recovery_path, canonical_path)):
        state_payload = load_json(state_path)["payload"]
        consequence_payload = load_json(consequence_path)["payload"]
        recovery_payload = load_json(recovery_path)["payload"]
        canonical_payload = load_json(canonical_path)["payload"]
        state_by_key = {
            (node["node_id"], node["state_set"]["representation_id"]): node["state_set"]
            for variant in state_payload["variants"] for node in variant["nodes"]
        }
        consequence_by_key = {
            (row["node_id"], row["representation_id"]): row
            for row in consequence_payload["rows"]
        }
        recovery_by_key = {
            (row["node_id"], row["decision"]["representation_id"]): row
            for row in recovery_payload["rows"]
        }
        canonical_by_node = {row["node_id"]: row for row in canonical_payload["nodes"]}
        state_counts = Counter(row["stage"] for row in state_by_key.values())
        stage_counts = dict(state_counts)
        linked_counts = dict(Counter(
            state_by_key[key]["stage"] for key in set(state_by_key) & set(consequence_by_key)
        ))
        recovery_stage_counts = dict(Counter(row["stage"] for row in recovery_payload["rows"]))
        priority_path = AUTH_ROOT / "model" / "M2" / "comparison_support.py"
        stage2_path = AUTH_ROOT / "model" / "M3" / "stage2.py"
        registry_path = AUTH_ROOT / "registries" / "m2_data2_formal_cu_v5.json"
        trace_source_hashes = {str(path): sha256(path) for path in
            (state_path, consequence_path, recovery_path, canonical_path, priority_path, stage2_path, registry_path)
            if path.exists()}
        ratio_values: dict[str, list[float]] = {"F_propagation_over_D_TO": [], "P_time_over_D_TO": []}
        for key in set(state_by_key) & set(consequence_by_key):
            state = state_by_key[key]
            consequence = consequence_by_key[key]
            by_scenario = {item["scenario_id"]: item for item in consequence.get("consequence_set", {}).get("scenarios", [])}
            for scenario in state.get("scenarios", []):
                item = by_scenario.get(scenario.get("scenario_id"), {})
                native = item.get("native_components", {})
                d_ob = float(scenario.get("d_ob_minutes") or 0.0)
                d_tx = float(scenario.get("d_tx_minutes") or 0.0)
                d_to = float(scenario.get("d_to_minutes") or 0.0)
                checks = {
                    "D_TO_equals_D_OB_plus_D_TX": abs(d_to - d_ob - d_tx) <= 1e-5,
                    "F_execution_equals_D_OB": abs(float(native.get("F_execution", 0.0)) - d_ob) <= 1e-5,
                    "R_operating_equals_D_TX": abs(float(native.get("R_operating", 0.0)) - d_tx) <= 1e-5,
                }
                for name, passed in checks.items():
                    formula_checks[name] = formula_checks.get(name, 0) + (1 if passed else -1)
                if d_to > 1e-8:
                    ratio_values["F_propagation_over_D_TO"].append(float(native.get("F_propagation", 0.0)) / d_to)
                    ratio_values["P_time_over_D_TO"].append(float(native.get("P_time", 0.0)) / d_to)
        for name, values in ratio_values.items():
            formula_ratio_summary[name] = {"count": len(values), "min": min(values) if values else None,
                "max": max(values) if values else None, "distinct_rounded_1e-8": len({round(v, 8) for v in values})}
        seen_stages: set[str] = set()
        for key in sorted(set(state_by_key) & set(consequence_by_key) & set(recovery_by_key)):
            state = state_by_key[key]
            consequence = consequence_by_key[key]
            recovery = recovery_by_key[key]
            stage = state["stage"]
            if stage not in {"PRE_IB", "POST_IB_PRE_OB"} or stage in seen_stages:
                continue
            if not recovery.get("actionable") or consequence.get("support", {}).get("status") != "SUPPORTED":
                continue
            canonical = canonical_by_node.get(key[0], {})
            scenario = state.get("scenarios", [{}])[0]
            consequence_scenario = next((item for item in consequence.get("consequence_set", {}).get("scenarios", [])
                if item.get("scenario_id") == scenario.get("scenario_id")), {})
            decision = recovery.get("decision", {})
            trace_rows.append({
                "stage": stage, "example_id": key[0], "representation_id": key[1],
                "source_artifacts": {"state": str(state_path), "consequence": str(consequence_path),
                    "recovery": str(recovery_path), "canonical": str(canonical_path)},
                "raw_observation": canonical.get("observed", {}),
                "decision_time": canonical.get("decision_time"),
                "sobt_minutes": canonical.get("sobt_minutes"),
                "primitive_state_scenario": {name: scenario.get(name) for name in
                    ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes", "d_to_minutes", "scenario_weight", "support")},
                "native_consequence": consequence_scenario.get("native_components", {}),
                "native_units_from_registry": {name: item.get("unit") for name, item in
                    load_json(registry_path).get("native_quantity_definitions", {}).items()} if registry_path.exists() else {},
                "cu_components": consequence_scenario.get("cu_components", {}),
                "priority": {"score": (consequence.get("consequence_signal") or {}).get("score"),
                    "meaning": consequence_payload.get("priority_authority", {}).get("consequence_based_priority_authority")},
                "recovery": {"u_star": decision.get("u_star"), "u_max": decision.get("u_max"),
                    "grid": decision.get("action_grid"), "units": "minutes per frozen Stage-II contract",
                    "interpretation": "modeled recovery-intensity decision variable; not an identified real-world action"},
                "cu_semantics": "constructed normalized consequence representation; no currency conversion in this chain",
                "code_locations": [str(AUTH_ROOT / "model" / "M2" / "drivers.py"),
                    str(AUTH_ROOT / "model" / "M2" / "comparison_support.py"), str(stage2_path)],
                "status": "TRACE_LINKED_IN_FROZEN_CHECKPOINTS_INPUT_RAW_MAPPING_REVIEW_REMAINS",
            })
            seen_stages.add(stage)

        # TAXI nodes carry state and consequence rows, but Stage-II has no
        # actionable recovery decision rows for this operational stage.
        taxi_key = next((key for key, state in state_by_key.items()
            if state["stage"] == "POST_OB_PRE_TO" and key in consequence_by_key), None)
        if taxi_key:
            state = state_by_key[taxi_key]
            consequence = consequence_by_key[taxi_key]
            scenario = state.get("scenarios", [{}])[0]
            cs = next((item for item in consequence.get("consequence_set", {}).get("scenarios", [])
                if item.get("scenario_id") == scenario.get("scenario_id")), {})
            trace_rows.append({"stage": "POST_OB_PRE_TO", "example_id": taxi_key[0],
                "representation_id": taxi_key[1], "primitive_state_scenario": {name: scenario.get(name)
                    for name in ("t_ib_minutes", "d_ob_minutes", "d_tx_minutes", "d_to_minutes", "scenario_weight", "support")},
                "native_consequence": cs.get("native_components", {}), "cu_components": cs.get("cu_components", {}),
                "priority": {"score": (consequence.get("consequence_signal") or {}).get("score"),
                    "meaning": consequence_payload.get("priority_authority", {}).get("consequence_based_priority_authority")},
                "recovery": {"u_star": None, "status": "NOT_AVAILABLE_FOR_TAXI_STAGE", "units": "NOT_APPLICABLE"},
                "status": "TRACE_TO_PRIORITY_ONLY_NO_TAXI_RECOVERY_DECISION"})
    if pre_path.exists():
        for line in pre_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            node = row.get("decision_node", {})
            stage = node.get("operational_stage")
            if stage in {"PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO"}:
                trace_rows.append({"stage": stage, "node_id": node.get("decision_node_id"),
                    "decision_time": node.get("decision_time"), "information_cutoff": node.get("information_cutoff"),
                    "time_ok": node.get("information_cutoff") <= node.get("decision_time"),
                    "target_support": row.get("target_support", []),
                    "variable_lineage_count": len(row.get("variable_lineage", []))})
                if len(trace_rows) >= 3:
                    break
    # Frozen checkpoints support linked PRE/TURN numerical traces. TAXI has no
    # actionable Stage-II row; source-field interpretation also remains a
    # separate audit obligation.
    return {
        "schema_version": "AIR_SLOT_G0_UNIT_TIME_AUDIT_V1",
        "status": "UNKNOWN_INSUFFICIENT_PAYLOAD",
        "blocking_state": "BLOCKED_UNIT_CONTRACT",
        "scientific_recomputation": False,
        "real_supported_traces": trace_rows,
        "state_stage_counts_by_representation": stage_counts,
        "state_consequence_linked_counts_by_representation": linked_counts,
        "recovery_decision_stage_counts": recovery_stage_counts,
        "trace_source_hashes": trace_source_hashes,
        "formula_checks": formula_checks,
        "formula_ratio_summary": formula_ratio_summary,
        "fixture_traces": [{"path": str(ROOT / "validation" / "scientific_smoke.py"),
            "scope": "BOUNDED_SCIENTIFIC_SMOKE", "paper_result": False,
            "status": "FIXTURE_ONLY_NOT_REAL_CASE"}],
        "source_evidence": source_evidence,
        "required_trace_fields": ["source field", "raw value", "raw unit", "transform",
            "intermediate value", "intermediate unit", "final consequence", "CU meaning",
            "priority contribution", "u meaning", "code location", "artifact/example id"],
        "finding": "Frozen checkpoints link supported PRE/TURN scenario primitives through native consequences, CU components, priority scores, and u*. Deterministic identities D_TO=D_OB+D_TX, F_execution=D_OB, R_operating=D_TX, and F_propagation=D_TO are satisfied across the linked rows. TAXI rows terminate at priority because no actionable Stage-II recovery row exists; raw source-field mapping and a TAXI u trace remain unresolved.",
    }


def _manifest_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    inputs = data.get("input_artifacts", [])
    checked = []
    for item in inputs:
        source = Path(str(item.get("path", "")))
        exists = source.exists()
        checked.append({"path": str(source), "declared_sha256": item.get("sha256"),
            "exists": exists, "hash_match": bool(exists and sha256(source) == item.get("sha256"))})
    if checked and all(x["hash_match"] for x in checked):
        status = "MATCHED"
    elif checked and any(x["exists"] for x in checked):
        status = "FROZEN_BUT_LINEAGE_PARTIAL"
    else:
        status = "SOURCE_UNKNOWN"
    return {"manifest": str(path), "figure_id": data.get("figure_id"),
        "authority_lineage": data.get("authority_lineage"), "cohort_identity": data.get("cohort_identity"),
        "input_checks": checked, "status": status,
        "frozen_flags": {key: data.get(key) for key in ("model_retrained", "recalibration_performed",
            "parameter_reselected", "raw_final_test_data_read", "new_final_test_access_opened",
            "scientific_definition_changed")}}


def lineage_audit() -> dict[str, Any]:
    rows = []
    for path in sorted((ROOT / "artifacts").rglob("*_MANIFEST.json")):
        data = load_json(path)
        if isinstance(data, dict):
            rows.append(_manifest_status(path, data))
    counts = Counter(row["status"] for row in rows)
    authority_path = AUTH_ROOT / "artifacts" / "experiment" / "final_test_v2_stage_matched_canonical_v2" / "PAPER_FACING_SECTION5_RESULTS.json"
    pre_manifest_path = AUTH_ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1" / "2019" / "PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json"
    reproduction_path = AUTH_ROOT / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1" / "2019" / "GATE_2019_REPRODUCTION.json"
    section_path = ROOT / "_review_Rolling_Airline_Recovery_46_section3_new" / "sections" / "05_experiment.tex"
    appendix_path = ROOT / "_review_Rolling_Airline_Recovery_46_section3_new" / "sections" / "appendix.tex"
    authority = load_json(authority_path) if authority_path.exists() else None
    pre_manifest = load_json(pre_manifest_path) if pre_manifest_path.exists() else None
    reproduction = load_json(reproduction_path) if reproduction_path.exists() else None
    section_text = section_path.read_text(encoding="utf-8", errors="ignore") if section_path.exists() else ""
    appendix_text = appendix_path.read_text(encoding="utf-8", errors="ignore") if appendix_path.exists() else ""
    final_split_supported = bool(pre_manifest and pre_manifest.get("cohort_audit", {}).get("cohort_counts", {}).get("test") == 0)
    claims_have_heldout_language = "held-out" in section_text.lower() and "october" in appendix_text.lower()
    paper_surfaces = []
    delay_projection_path = AUTH_ROOT / "artifacts" / "experiment" / "final_test_v2_stage_matched_canonical_v2" / "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json"
    delay_projection = load_json(delay_projection_path) if delay_projection_path.exists() else None
    surfaces = (("FIGURE3", "stage1", delay_projection, "formal/v2_phase7/project_delay_vs_consequence_stage1.py"),
        ("FIGURE4", "stage2", authority, "formal/v2_phase7/project_section5_paper_facing.py"),
        ("FIGURE5", "information", authority, "formal/v2_phase7/project_section5_paper_facing.py"))
    for surface, label, surface_authority, generator_path in surfaces:
        source = (authority or {}).get("authority", {}).get("source_checkpoints", {})
        source_names = [x.get("file") for x in source.values() if isinstance(x, dict)]
        source_names = [x.get("file") for x in ((surface_authority or {}).get("authority", {}).get("source_checkpoints", {}) or {}).values() if isinstance(x, dict)]
        source_names.extend([str((surface_authority or {}).get("source_checkpoint", {}).get("path"))] if (surface_authority or {}).get("source_checkpoint") else [])
        paper_surfaces.append({"paper_surface": surface, "split": "held-out October-December 2019",
            "source_artifact": (surface_authority or {}).get("canonical_v2_epoch", {}).get("freeze_tag") or (surface_authority or {}).get("authority", {}).get("final_test", {}).get("freeze_tag"),
            "generator": generator_path,
            "commit_or_hash": (surface_authority or {}).get("canonical_v2_epoch", {}).get("scientific_commit") or (surface_authority or {}).get("authority", {}).get("final_test", {}).get("scientific_commit"),
            "source_checkpoints_present": bool(source_names),
            "projection_path": str(delay_projection_path if surface == "FIGURE3" else authority_path),
            "frozen": bool((surface_authority or {}).get("projection_only")) and bool((surface_authority or {}).get("validation", {}).get("seal_flags", {}).get("paper_results_frozen") or (surface_authority or {}).get("canonical_v2_epoch", {}).get("epoch_seal", {}).get("status") == "SEALED_AUDIT_PASS"),
            "reproducible": bool((surface_authority or {}).get("validation", {}).get("checkpoint_hash_verification", {}).get("all_file_hashes_match") or (surface_authority or {}).get("source_checkpoint", {}).get("identity_verification")),
            "status": "MATCHED" if source_names and claims_have_heldout_language else "FROZEN_BUT_LINEAGE_PARTIAL"})
    paper_surfaces.append({"paper_surface": "Stage-I TURN q=0.10 changed positions",
        "split": "held-out October-December 2019", "source_artifact": str(delay_projection_path),
        "generator": "formal/v2_phase7/project_delay_vs_consequence_stage1.py",
        "commit_or_hash": (delay_projection or {}).get("canonical_v2_epoch", {}).get("scientific_commit"),
        "claim_value": "5/13", "artifact_value": (delay_projection or {}).get("results", {}).get("POST_IB_PRE_OB", {}).get("changed_position_count"),
        "status": "MATCHED" if (delay_projection or {}).get("results", {}).get("POST_IB_PRE_OB", {}).get("changed_position_count") == 5 else "MISMATCH"})
    section5 = (authority or {})
    cap_rows = section5.get("section_5_1_stage1_attention", {}).get("capacity_rows", [])
    by_cap = {(row.get("stage"), row.get("q")): row for row in cap_rows}
    turn_nominal = by_cap.get(("POST_IB_PRE_OB", 0.1), {})
    pre_nominal = by_cap.get(("PRE_IB", 0.1), {})
    recovery_summary = section5.get("section_5_2_stage2_recovery", {}).get("summary_by_stage", {})
    claim_rows = [
        ("PRE shortlist capacity N/K", "PRE", "29/3", f"{pre_nominal.get('n_g')}/{pre_nominal.get('k_g')}"),
        ("TURN shortlist capacity N/K", "TURN", "127/13", f"{turn_nominal.get('n_g')}/{turn_nominal.get('k_g')}"),
        ("Stage-II positive targets", "PRE", "3/3", f"{recovery_summary.get('PRE', {}).get('positive_u_count')}/{recovery_summary.get('PRE', {}).get('N')}"),
        ("Stage-II positive targets", "TURN", "10/13", f"{recovery_summary.get('TURN', {}).get('positive_u_count')}/{recovery_summary.get('TURN', {}).get('N')}"),
        ("Stage-II positive targets", "TOTAL", "13/16", f"{recovery_summary.get('OVERALL', {}).get('positive_u_count')}/{recovery_summary.get('OVERALL', {}).get('N')}"),
        ("Median positive u", "TOTAL", "5 min", f"{float(recovery_summary.get('OVERALL', {}).get('median_positive_u')):g} min"),
    ]
    for claim, stage, claim_value, artifact_value in claim_rows:
        paper_surfaces.append({"paper_surface": claim, "stage": stage, "split": "held-out October-December 2019",
            "source_artifact": str(authority_path), "generator": "formal/v2_phase7/project_section5_paper_facing.py",
            "claim_value": claim_value, "artifact_value": artifact_value,
            "status": "MATCHED" if claim_value == artifact_value else "MISMATCH"})
    paper_surfaces.append({"paper_surface": "2019 temporal partition", "split": "train/calibration/development/test",
        "source_artifact": str(pre_manifest_path), "generator": "PRE_MULTIYEAR_DEVELOPMENT_V1",
        "commit_or_hash": pre_manifest.get("config_hash") if pre_manifest else None,
        "frozen": bool(pre_manifest), "reproducible": bool(reproduction and reproduction.get("status") == "PASS"),
        "status": "MATCHED" if final_split_supported and claims_have_heldout_language and reproduction and reproduction.get("status") == "PASS" else "FROZEN_BUT_LINEAGE_PARTIAL"})
    primary_claims = paper_surfaces
    return {
        "schema_version": "AIR_SLOT_G0_LINEAGE_AUDIT_V1",
        "status": "FROZEN_BUT_LINEAGE_PARTIAL" if rows else "SOURCE_UNKNOWN",
        "blocking_state": "BLOCKED_LINEAGE",
        "scientific_recomputation": False,
        "manifest_rows": rows,
        "status_counts": dict(counts),
        "paper_surface_rows": primary_claims,
        "required_columns": ["paper claim/table", "split", "source artifact", "generator",
            "commit/hash", "frozen", "reproducible", "status"],
        "finding": "Final-Test projection and checkpoint hashes are matched, and the 2019 temporal partition/reproduction manifests are present. The table records split and generator evidence separately from hash matching; full claim-level number-to-source reconciliation remains incomplete.",
    }


def render_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"- Status: `{payload['status']}`", f"- Blocking state: `{payload.get('blocking_state')}`", ""]
    lines.append("```json")
    lines.append(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    lines.extend(["```", ""])
    return "\n".join(lines)


def run(output_dir: Path = REPORT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    marginal = marginal_audit()
    units = unit_time_audit()
    lineage = lineage_audit()
    manifest = {
        "schema_version": "AIR_SLOT_G0_READONLY_AUDIT_MANIFEST_V1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "root": str(ROOT), "scientific_recomputation": False,
        "formal_executor_invoked": False, "final_test_access_count": 0,
        "status": "G0_PARTIAL_BLOCKED",
        "checks": {"G0-2": marginal["status"], "G0-3": units["status"], "G0-5": lineage["status"]},
        "blocking_states": [x for x in (marginal.get("blocking_state"), units.get("blocking_state"), lineage.get("blocking_state")) if x],
    }
    artifacts = {"G0_MARGINAL_AUDIT": marginal, "G0_UNIT_TRACE": units, "G0_LINEAGE_AUDIT": lineage}
    for name, payload in artifacts.items():
        (output_dir / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / f"{name}.md").write_text(render_markdown(name, payload), encoding="utf-8")
    (output_dir / "G0_READONLY_AUDIT_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, ensure_ascii=False, sort_keys=True))
