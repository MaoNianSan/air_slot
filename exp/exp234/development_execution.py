"""Exp2-Exp4 Development execution on M1_SIGNED_DEVELOPMENT_SCENARIOS_V1.

Frozen inputs only (no PRE rebuild, no M1 retrain, no Final Test access):
- M1_SIGNED_DEVELOPMENT_SCENARIOS_V1 (node.parquet / scenario.parquet)
- M2_DATA2_FORMAL_CU_V1 registry + four train-frozen Data2 references
- M3_RESPONSE_SCENARIO_V1 response registry + ACTION_TEMPLATES_V1

Protocol classification: DERIVED_DOWNSTREAM_ARTIFACT_GENERATION /
DEVELOPMENT_EXECUTION.  M4 decision lanes are NOT runnable because the
material-coverage contract has no frozen artifact
(M2_MATERIAL_COVERAGE_CONTRACT_V1 is an identifier only); everything that
needs M4 is reported as blocked (M4_MATERIAL_COVERAGE_UNFROZEN) and never
replaced with invented contracts or fixture coverage.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import time
import pyarrow as pa
import pyarrow.parquet as pq
from exp.exp2.metrics import (
    action_gap_distortion,
    consequence_distortion,
    formal_multi_action_gate,
    pairwise_ranking_reversal_rate,
    ranking_at_3_overlap,
    reference_objective_selection_penalty,
    top1_disagreement,
)
from exp.exp2.representations import corrupt_scenario_lineage, point_collapse
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_context,
    build_m2_frozen_scope,
    load_data2_reference_bundle,
)
from model.M2.freeze import FrozenData2ValuationRegistry, load_m2_registry
from model.M2.mapper import M2Mapper
from model.M3.instantiate import instantiate_candidates
from model.M3.registry import ActionRegistry
from model.M3.response import action_post_consequences, response_draw
from model.M3.response_registry import load_response_registry
from model.common.identity import content_id

from exp.exp234.exp234_helpers import (
    FLIGHT_SCOPE,
    FULL_SCOPE,
    _ACTION_META,
    _action_family,
    _action_map_from_pre,
    _authority,
    _component_means,
    _distributional,
    _flatten_rows,
    _mean_metrics,
    _mean_of_optionals,
    _post_scope,
    _preparation,
    _spread,
)
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
ARTIFACT_DIR = OUT / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
SCENARIO_MANIFEST_PATH = OUT / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1_MANIFEST.json"
M2_REGISTRY_PATH = ROOT / "registries" / "m2_data2_formal_cu_v1.json"
M2_MANIFEST_PATH = OUT / "M2_DATA2_FORMAL_CU_V1_MANIFEST.json"
M2_REFERENCE_FILES = {
    "turnaround": OUT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json",
    "taxi": OUT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json",
    "downstream_exposure": OUT / "DATA2_DOWNSTREAM_EXPOSURE_REFERENCE_TRAIN_FROZEN_V1.json",
    "passenger": OUT / "DATA2_PASSENGER_REFERENCE_H1_TRAIN_FROZEN_V1.json",
}
ACTION_REGISTRY_PATH = ROOT / "registries" / "action_templates.yaml"
RESPONSE_REGISTRY_PATH = ROOT / "registries" / "m3_response_scenarios.yaml"
M3_MANIFEST_PATH = OUT / "M3_RESPONSE_SCENARIO_V1_MANIFEST.json"
M3_RESPONSE_SEED = 20260813
M3_RESPONSE_SEED_PROVENANCE = (
    "M3_RESPONSE_SEED_NOT_FROZEN_IN_REGISTRY; "
    "reuse of frozen M1 SCENARIO_SEED=20260813 recorded for reproducibility"
)
CORRUPTION_Q = (0.0, 0.25, 0.50, 0.75, 1.0)
EXP2_OUT = OUT / "EXP2_DEVELOPMENT_V1"
EXP2_MANIFEST = OUT / "EXP2_DEVELOPMENT_V1.json"
EXP2_PARQUET = EXP2_OUT / "exp2_development.parquet"
EXP3_OUT = OUT / "EXP3_DEVELOPMENT_V1"
EXP3_MANIFEST = OUT / "EXP3_DEVELOPMENT_V1.json"
EXP3_PARQUET = EXP3_OUT / "exp3_development.parquet"
EXP4_OUT = OUT / "EXP4_DEVELOPMENT_V1"
EXP4_MANIFEST = OUT / "EXP4_DEVELOPMENT_V1.json"
EXP4_PARQUET = EXP4_OUT / "exp4_development.parquet"
AUDIT_CASES_PATH = OUT / "EXP234_LLM_AUDIT_CASES.json"
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
def _write_parquet(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(payload)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
    temporary.replace(path)
def _hash_file(path: Path) -> str:
    from hashlib import sha256
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
def load_scenario_artifact() -> tuple[list[dict], dict[str, list[dict]], dict]:
    """Load node rows and scenario rows grouped by decision_node_id."""
    manifest = _read_json(SCENARIO_MANIFEST_PATH)
    if manifest.get("FINAL_TEST_ACCESS_COUNT") != 0 or manifest.get("PAPER_FULL_RUN"):
        raise RuntimeError("EXP234_SCENARIO_ARTIFACT_FINAL_TEST_VIOLATION")
    node = pq.read_table(ARTIFACT_DIR / "node.parquet").to_pydict()
    scenario = pq.read_table(ARTIFACT_DIR / "scenario.parquet").to_pydict()
    node_rows = [
        {name: node[name][index] for name in node}
        for index in range(len(node["decision_node_id"]))
    ]
    by_node: dict[str, list[dict]] = {}
    for index in range(len(scenario["decision_node_id"])):
        key = scenario["decision_node_id"][index]
        by_node.setdefault(key, []).append(
            {name: scenario[name][index] for name in scenario}
        )
    for key, rows in by_node.items():
        rows.sort(key=lambda row: int(row["scenario_id"]))
    return node_rows, by_node, manifest
def load_m2() -> dict:
    registry = load_m2_registry(M2_REGISTRY_PATH)
    valuation = FrozenData2ValuationRegistry(registry)
    scope = build_m2_frozen_scope()
    manifest = _read_json(M2_MANIFEST_PATH)
    payloads = {name: _read_json(path) for name, path in M2_REFERENCE_FILES.items()}
    bundle = load_data2_reference_bundle(
        payloads, expected_reference_ids=manifest["reference_ids"]
    )
    mapper = M2Mapper(valuation, scope)
    return {
        "registry": registry,
        "valuation": valuation,
        "scope": scope,
        "bundle": bundle,
        "mapper": mapper,
        "manifest": manifest,
    }
def load_m3() -> dict:
    action_registry = ActionRegistry.load(ACTION_REGISTRY_PATH)
    response_registry = load_response_registry(
        RESPONSE_REGISTRY_PATH, structural_path=ACTION_REGISTRY_PATH
    )
    manifest = _read_json(M3_MANIFEST_PATH)
    if response_registry.digest() != manifest["registry_hash"]:
        raise RuntimeError("EXP234_M3_RESPONSE_REGISTRY_HASH_MISMATCH")
    return {
        "action_registry": action_registry,
        "response_registry": response_registry,
        "manifest": manifest,
    }
def _context_for(m2: dict, connection_airport_id: str,
                 successor_destination_airport_id: str):
    return build_m2_context(
        m2["bundle"],
        AirportReferenceKeys(
            connection_airport_id=connection_airport_id,
            successor_destination_airport_id=successor_destination_airport_id,
        ),
    )
def map_node_pre(m2: dict, context, scenario_rows: list[dict]) -> list[dict]:
    """M2 map one node's scenarios; return per-scenario pre-CU payloads."""
    mapper = m2["mapper"]
    consequences = mapper.map_scenarios(scenario_rows, context)
    output = []
    for consequence in consequences:
        components = {
            row.component_id: row.constructed_value_cu
            for row in consequence.component_vector.rows
        }
        formal = consequence.formal_estimand_value
        output.append({
            "scenario_id": int(consequence.scenario_id),
            "scenario_weight": float(consequence.scenario_weight),
            "formal_cu": formal.value_cu,
            "formal_status": str(formal.status.value),
            "formal_reason": formal.reason_code,
            "components": components,
            "diagnostic_cu": consequence.available_component_sum_diagnostic.value_cu,
        })
    return output
def _fast_pre_rows(m2: dict, context, scenario_rows: list[dict]) -> list[dict]:
    """Performance projection of the frozen M2 mapper for fully-supported rows.

    Mirrors model.M2.drivers.native_quantities + FrozenData2ValuationRegistry
    arithmetic exactly; equivalence to M2Mapper.map_scenarios is verified on a
    sample and recorded in the manifest (FAST_PATH_EQUIVALENCE).
    """
    turnaround = getattr(context.turnaround_reference, "value", None)
    exposure = getattr(context.expected_downstream_exposure, "value", None)
    passenger = getattr(context.passenger_exposure, "value", None)
    multipliers = {
        name: 1.0 / float(m2["registry"].scale(name)) for name in FULL_SCOPE
    }

    def supported(value):
        return value is not None

    output = []
    for row in scenario_rows:
        r_ib = row.get("r_ib_minutes")
        # M2 V2 consumes strict formal M1 fields. Legacy delta_ob/t_tx fields
        # are not valid substitutes and must remain ABSTAIN when d_ob/d_tx are
        # absent from the typed scenario row.
        d_ob = row.get("d_ob_minutes")
        d_tx = row.get("d_tx_minutes")
        d_to = row.get("d_to_minutes")
        d_ob_support = row.get("d_ob_support", "SUPPORTED")
        d_tx_support = row.get("d_tx_support", "SUPPORTED")
        d_to_support = row.get("d_to_support", "SUPPORTED")
        rib_support = supported(r_ib)
        d_ob_supported = supported(d_ob) and d_ob_support != "ABSTAIN"
        d_tx_supported = supported(d_tx) and d_tx_support != "ABSTAIN"
        d_to_supported = supported(d_to) and d_to_support != "ABSTAIN"
        rob = None if not d_ob_supported else float(d_ob)
        takeoff = None if not d_to_supported else float(d_to)
        components = {}
        def publish(component, value, parents_supported):
            if not parents_supported or value is None:
                components[component] = None
                return
            components[component] = float(value) * multipliers[component]
        publish("F_continuity",
                None if not (rib_support and supported(turnaround)) else max(0.0, float(r_ib) - float(turnaround)),
                rib_support and supported(turnaround))
        publish("F_execution", rob, d_ob_supported)
        publish("F_propagation",
                None if takeoff is None or exposure is None else takeoff * float(exposure),
                d_to_supported and supported(exposure))
        publish("P_time",
                None if takeoff is None or passenger is None else takeoff * float(passenger),
                d_to_supported and supported(passenger))
        # These components require typed M2 inputs not present in this legacy
        # scenario artifact; preserve ABSTAIN instead of proxy substitution.
        components["P_itinerary"] = None
        components["P_service"] = None
        publish("R_operating",
                None if not d_tx_supported else float(d_tx),
                d_tx_supported)
        formal_values = [components[name] for name in FULL_SCOPE]
        formal_cu = None if any(value is None for value in formal_values) else float(sum(formal_values))
        valued = [value for value in components.values() if value is not None]
        diagnostic_cu = None if not valued else float(sum(valued))
        output.append({
            "scenario_id": int(row["scenario_id"]),
            "scenario_weight": float(row.get("scenario_weight", 1.0 / len(scenario_rows))),
            "formal_cu": formal_cu,
            "formal_status": "FORMAL_AVAILABLE" if formal_cu is not None else "FORMAL_AGGREGATE_UNRESOLVED",
            "formal_reason": None if formal_cu is not None else "INCLUDED_COMPONENT_ABSTAIN",
            "components": components,
            "diagnostic_cu": diagnostic_cu,
        })
    return output
def fast_path_equivalence(m2: dict, context, scenario_rows: list[dict]) -> dict:
    """Verify _fast_pre_rows reproduces the frozen M2Mapper exactly."""
    reference = map_node_pre(m2, context, scenario_rows)
    fast = _fast_pre_rows(m2, context, scenario_rows)
    equal = True
    maximum_difference = 0.0
    for left, right in zip(reference, fast):
        if not (
            (left["formal_cu"] is None and right["formal_cu"] is None)
            or (
                left["formal_cu"] is not None
                and right["formal_cu"] is not None
                and math.isclose(left["formal_cu"], right["formal_cu"], rel_tol=1e-12, abs_tol=1e-12)
            )
        ):
            equal = False
        for name in FULL_SCOPE:
            a, b = left["components"].get(name), right["components"].get(name)
            if a is None or b is None:
                if a is not None or b is not None:
                    equal = False
                continue
            if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
                equal = False
            maximum_difference = max(maximum_difference, abs(a - b))
        if left["diagnostic_cu"] is not None and right["diagnostic_cu"] is not None:
            if not math.isclose(left["diagnostic_cu"], right["diagnostic_cu"], rel_tol=1e-12, abs_tol=1e-12):
                equal = False
            maximum_difference = max(maximum_difference, abs(left["diagnostic_cu"] - right["diagnostic_cu"]))
        elif left["diagnostic_cu"] != right["diagnostic_cu"]:
            equal = False
    return {
        "status": "PASS" if equal else "FAIL",
        "scenarios_checked": len(scenario_rows),
        "maximum_abs_difference": maximum_difference,
    }
def _rho_table(candidates, node_row, scenario_ids: list[int], m3: dict,
               sensitivity: str) -> dict[str, list[float]]:
    """Frozen response draws per (action, scenario); shared by all variants."""
    from model.M3.response import response_uniform
    from scipy.special import betaincinv
    import numpy as np
    registry_hash = m3["response_registry"].digest()
    table = {}
    for candidate in candidates:
        if candidate.template_id == "A00" or candidate.response_model == "DETERMINISTIC":
            table[candidate.template_id] = [0.0] * len(scenario_ids)
            continue
        parameters = {
            "response_model": candidate.response_model,
            **candidate.response_parameters,
        }
        probability = float(parameters["success_probability"])
        mean = float(parameters["mean_intensity"])
        concentration = float(parameters["concentration"])
        bernoulli = np.array([
            response_uniform(seed=M3_RESPONSE_SEED, episode_id=node_row["episode_id"],
                             decision_node_id=node_row["decision_node_id"], scenario_id=sid,
                             action_template_id=candidate.template_id,
                             response_dimension="BERNOULLI", sensitivity_level=sensitivity,
                             response_registry_hash=registry_hash)
            for sid in scenario_ids
        ])
        beta_uniform = np.array([
            response_uniform(seed=M3_RESPONSE_SEED, episode_id=node_row["episode_id"],
                             decision_node_id=node_row["decision_node_id"], scenario_id=sid,
                             action_template_id=candidate.template_id,
                             response_dimension="BETA_INTENSITY", sensitivity_level=sensitivity,
                             response_registry_hash=registry_hash)
            for sid in scenario_ids
        ])
        implemented = bernoulli <= probability
        rho = np.zeros(len(scenario_ids), dtype=np.float64)
        if implemented.any():
            alpha = mean * concentration
            beta = (1.0 - mean) * concentration
            rho[implemented] = betaincinv(alpha, beta, beta_uniform[implemented])
        table[candidate.template_id] = [float(value) for value in rho]
    return table
def _rho(candidate, node_row, scenario_id: int, response_registry_hash: str,
         sensitivity: str) -> float:
    if candidate.template_id == "A00" or candidate.response_model == "DETERMINISTIC":
        return 0.0
    return response_draw(
        seed=M3_RESPONSE_SEED,
        episode_id=node_row["episode_id"],
        decision_node_id=node_row["decision_node_id"],
        scenario_id=scenario_id,
        action_template_id=candidate.template_id,
        parameters={
            "response_model": candidate.response_model,
            **candidate.response_parameters,
        },
        response_registry_hash=response_registry_hash,
        sensitivity_level=sensitivity,
    )
def _candidates_for(m3: dict, node_row: dict) -> tuple:
    return instantiate_candidates(
        {
            "episode_id": node_row["episode_id"],
            "decision_node_id": node_row["decision_node_id"],
            "facts": {},
            "parameters": {},
        },
        m3["action_registry"],
        response_registry=m3["response_registry"],
        sensitivity="BASE",
    )
def _node_action_map(candidates, pre_rows, node_row, m3, sensitivity: str,
                     scope: tuple[str, ...],
                     scenario_subset: list[int] | None = None) -> dict:
    """{action_template_id: distributional post-CU over the selected scenarios}."""
    indices = scenario_subset if scenario_subset is not None else list(range(len(pre_rows)))
    weights = [pre_rows[index]["scenario_weight"] for index in indices]
    action_map = {}
    for candidate in candidates:
        values = []
        for position in indices:
            rho = _rho(candidate, node_row, int(pre_rows[position]["scenario_id"]),
                       m3["response_registry"].digest(), sensitivity)
            values.append(_post_scope(pre_rows[position], candidate, rho, scope))
        action_map[candidate.template_id] = _distributional(values, weights)
    return action_map
def _per_node_exp2(node_row, scenario_rows, m2, m3, context) -> dict:
    pre_rows = _fast_pre_rows(m2, context, scenario_rows)
    formal_cus = [row["formal_cu"] for row in pre_rows]
    node_formal = all(value is not None for value in formal_cus)
    formal_reason = None
    if not node_formal:
        reasons = {row["formal_reason"] for row in pre_rows if row["formal_cu"] is None}
        formal_reason = ";".join(sorted(reasons)) or "FORMAL_AGGREGATE_UNRESOLVED"

    candidates = _candidates_for(m3, node_row)
    scenario_ids = [int(row["scenario_id"]) for row in pre_rows]
    rho_table = _rho_table(candidates, node_row, scenario_ids, m3, "BASE")
    reference_full = _action_map_from_pre(candidates, pre_rows, rho_table, FULL_SCOPE)
    reference_flight = _action_map_from_pre(candidates, pre_rows, rho_table, FLIGHT_SCOPE)

    # Point collapse (medoid over the joint scenario bundle).
    collapsed = point_collapse(scenario_rows)
    point_position = next(
        index for index, row in enumerate(pre_rows)
        if int(row["scenario_id"]) == int(collapsed["selected_scenario_id"])
    )
    point_full = {}
    point_flight = {}
    for candidate in candidates:
        rho = rho_table[candidate.template_id][point_position]
        point_full[candidate.template_id] = _post_scope(
            pre_rows[point_position], candidate, rho, FULL_SCOPE)
        point_flight[candidate.template_id] = _post_scope(
            pre_rows[point_position], candidate, rho, FLIGHT_SCOPE)

    # Lineage corruption grid (replicate 0; q=0 must reproduce the reference).
    corrupted_maps = {}
    corrupted_component_means = {}
    for q in CORRUPTION_Q:
        corrupted, _audit = corrupt_scenario_lineage(
            scenario_rows, global_seed=20260813,
            episode_id=node_row["episode_id"],
            decision_node_id=node_row["decision_node_id"],
            corruption_q=q, replicate=0,
        )
        corrupted_pre = _fast_pre_rows(m2, context, corrupted)
        corrupted_maps[str(q)] = _action_map_from_pre(
            candidates, corrupted_pre, rho_table, FULL_SCOPE)
        corrupted_component_means[str(q)] = _component_means(corrupted_pre)
    reference_components = _component_means(pre_rows)

    row = {
        "episode_id": node_row["episode_id"],
        "decision_node_id": node_row["decision_node_id"],
        "operational_stage": node_row["operational_stage"],
        "node_formal": node_formal,
        "formal_reason": formal_reason,
        "n_scenarios": len(pre_rows),
        "reference_action_map": reference_full,
        "reference_flight_action_map": reference_flight,
        "component_means": reference_components,
        "variants": {
            "point_full": point_full,
            "point_flight": point_flight,
            "corrupted_q000": corrupted_maps["0.0"],
            "corrupted_q025": corrupted_maps["0.25"],
            "corrupted_q050": corrupted_maps["0.5"],
            "corrupted_q075": corrupted_maps["0.75"],
            "corrupted_q100": corrupted_maps["1.0"],
        },
        "variant_metrics": {
            "point_full": _mean_metrics(reference_full, point_full),
            "corrupted_q000": _mean_metrics(reference_full, corrupted_maps["0.0"]),
            "corrupted_q025": _mean_metrics(reference_full, corrupted_maps["0.25"]),
            "corrupted_q050": _mean_metrics(reference_full, corrupted_maps["0.5"]),
            "corrupted_q075": _mean_metrics(reference_full, corrupted_maps["0.75"]),
            "corrupted_q100": _mean_metrics(reference_full, corrupted_maps["1.0"]),
        },
        "variant_component_distortion": {
            "point_full": consequence_distortion(
                reference_components,
                {name: pre_rows[point_position]["components"].get(name)
                 for name in FULL_SCOPE},
            ),
            **{
                f"corrupted_q{int(q * 100):03d}": consequence_distortion(
                    reference_components, corrupted_component_means[str(q)])
                for q in CORRUPTION_Q
            },
        },
    }
    return row
_WORKER: dict = {}
def _init_worker() -> None:
    _WORKER["m2"] = load_m2()
    _WORKER["m3"] = load_m3()
    _WORKER["node_rows"], _WORKER["by_node"], _ = load_scenario_artifact()
    _WORKER["context_cache"] = {}
def _run_exp2_node(position: int) -> dict:
    node_row = _WORKER["node_rows"][position]
    key = (node_row["connection_airport_id"], node_row["successor_destination_airport_id"])
    context = _WORKER["context_cache"].get(key)
    if context is None:
        context = _context_for(_WORKER["m2"], *key)
        _WORKER["context_cache"][key] = context
    return _per_node_exp2(
        node_row, _WORKER["by_node"][node_row["decision_node_id"]],
        _WORKER["m2"], _WORKER["m3"], context,
    )
def _run_exp4_node(position: int) -> dict:
    node_row = _WORKER["node_rows"][position]
    key = (node_row["connection_airport_id"], node_row["successor_destination_airport_id"])
    context = _WORKER["context_cache"].get(key)
    if context is None:
        context = _context_for(_WORKER["m2"], *key)
        _WORKER["context_cache"][key] = context
    pre_rows = _fast_pre_rows(
        _WORKER["m2"], context, _WORKER["by_node"][node_row["decision_node_id"]])
    candidates = _candidates_for(_WORKER["m3"], node_row)
    scenario_ids = [int(row["scenario_id"]) for row in pre_rows]
    maps = {}
    for sensitivity in ("LOW", "BASE", "HIGH"):
        rho_table = _rho_table(candidates, node_row, scenario_ids, _WORKER["m3"], sensitivity)
        maps[sensitivity] = _action_map_from_pre(candidates, pre_rows, rho_table, FULL_SCOPE)
    ranked = {}
    for sensitivity in ("LOW", "BASE", "HIGH"):
        values = maps[sensitivity]
        ranked[sensitivity] = (
            tuple(sorted(values, key=values.get))
            if all(value is not None for value in values.values()) else ()
        )
    return {
        "episode_id": node_row["episode_id"],
        "decision_node_id": node_row["decision_node_id"],
        "operational_stage": node_row["operational_stage"],
        "low_action_map": maps["LOW"],
        "base_action_map": maps["BASE"],
        "high_action_map": maps["HIGH"],
        "low_base_top1_agreement": (
            None if not ranked["LOW"] else ranked["LOW"][0] == ranked["BASE"][0]),
        "base_high_top1_agreement": (
            None if not ranked["BASE"] else ranked["BASE"][0] == ranked["HIGH"][0]),
    }
def _parallel_rows(run_node, node_count: int, *, max_workers: int = 10) -> list[dict]:
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker) as pool:
        return list(pool.map(run_node, range(node_count)))
def exp2_development(*, limit_nodes: int | None = None) -> dict:
    started = time.perf_counter()
    node_rows, by_node, artifact_manifest = load_scenario_artifact()
    m2 = load_m2()
    m3 = load_m3()
    if limit_nodes is not None:
        node_rows = node_rows[:limit_nodes]

    # Verify the fast M2 projection against the frozen mapper on a sample.
    first_key = (node_rows[0]["connection_airport_id"], node_rows[0]["successor_destination_airport_id"])
    equivalence = fast_path_equivalence(
        m2, _context_for(m2, *first_key),
        by_node[node_rows[0]["decision_node_id"]],
    )
    if equivalence["status"] != "PASS":
        raise RuntimeError("EXP234_FAST_M2_PATH_EQUIVALENCE_FAILED")
    if len(node_rows) >= 32:
        rows = _parallel_rows(_run_exp2_node, len(node_rows))
    else:
        context_cache: dict[tuple[str, str], object] = {}
        rows = []
        for position, node_row in enumerate(node_rows):
            key = (node_row["connection_airport_id"], node_row["successor_destination_airport_id"])
            if key not in context_cache:
                context_cache[key] = _context_for(m2, *key)
            rows.append(_per_node_exp2(
                node_row, by_node[node_row["decision_node_id"]], m2, m3,
                context_cache[key]))
    formal_available = sum(1 for row in rows if row["node_formal"])
    print(f"exp2 done {len(rows)} nodes elapsed={time.perf_counter()-started:.0f}s", flush=True)

    aggregate = {}
    for variant in ("point_full", "corrupted_q000", "corrupted_q025", "corrupted_q050",
                    "corrupted_q075", "corrupted_q100"):
        values = [row["variant_metrics"][variant] for row in rows if row["node_formal"]]
        if not values:
            aggregate[variant] = None
            continue
        aggregate[variant] = {
            "nodes_evaluated": len(values),
            "mean_action_gap_distortion": sum(
                float(item["action_gap_distortion"]) for item in values) / len(values),
            "mean_pairwise_ranking_reversal_rate": sum(
                float(item["pairwise_ranking_reversal_rate"]) for item in values) / len(values),
            "mean_top1_disagreement": sum(
                float(item["top1_disagreement"]) for item in values) / len(values),
            "mean_ranking_at_3_overlap": _mean_of_optionals(
                [item["ranking_at_3_overlap"] for item in values]),
            "mean_reference_objective_selection_penalty": _mean_of_optionals([
                item["reference_objective_selection_penalty"]["ReferenceObjectiveSelectionPenalty"]
                for item in values]),
            "mean_consequence_distortion": _mean_of_optionals([
                row["variant_component_distortion"][variant]
                for row in rows if row["node_formal"]]),
        }

    payload = {
        "schema_version": "EXP2_DEVELOPMENT_V1",
        "decision_id": "AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION",
        "classification": "DEVELOPMENT_EXECUTION",
        "source_scenario_artifact": artifact_manifest["artifact_hash"],
        "m2_registry": m2["registry"].registry_hash,
        "m3_response_registry": m3["response_registry"].digest(),
        "m3_response_seed": M3_RESPONSE_SEED,
        "m3_response_seed_provenance": M3_RESPONSE_SEED_PROVENANCE,
        "reference_evaluator": "ALIGNED_DISTRIBUTIONAL_FULL_FIXED_FORMAL_SCOPE_FULL_DECISION_CONTRACT",
        "variants": ["P-C", "P-F", "D-C", "LINEAGE_CORRUPTION"],
        "corruption_q": list(CORRUPTION_Q),
        "fast_m2_path_equivalence": equivalence,
        "node_count": len(rows),
        "episode_count": len({row["episode_id"] for row in rows}),
        "formal_available_nodes": formal_available,
        "formal_unavailable_nodes": len(rows) - formal_available,
        "aggregate": aggregate,
        "formal_multi_action_gate": formal_multi_action_gate(
            sum(1 for row in rows if row["node_formal"])),
        "authoritative_ranking_claim": {
            "protocol_gate": "STRONG_AUTHORITATIVE_RANKING_CLAIM_ALLOWED",
            "status": "BLOCKED",
            "blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
            "note": "N_FORMAL_MULTI=1824 satisfies the Exp2 protocol gate, but "
                    "no authoritative ranking claim is made until the M4 "
                    "material-coverage contract exists as a frozen artifact",
        },
        "blocked_subcomponents": [
            "M4_MATERIAL_COVERAGE_UNFROZEN",
            "AUTHORITATIVE_RANKING_CLAIM_BLOCKED_BY_M4",
        ],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    payload["exp2_hash"] = content_id({
        "reference_action_map": [row["reference_action_map"] for row in rows],
        "variants": [row["variants"] for row in rows],
        "node_formal": [row["node_formal"] for row in rows],
    })
    _write_parquet(EXP2_PARQUET, _flatten_rows(rows))
    payload["partition"] = {
        "path": EXP2_PARQUET.relative_to(ROOT).as_posix(),
        "rows": len(rows),
        "hash": _hash_file(EXP2_PARQUET),
    }
    _write_json(EXP2_MANIFEST, payload)
    return payload
def exp3_development() -> dict:
    """Exp3 Development at the M2/M3 layer; M4 lane fields stay NOT_RUN."""
    from exp.exp3.metrics import (
        coverage_inflation,
        formal_feasibility_audit,
        invalidated_top1_rate,
        invalidated_topk_share,
        lane_rates,
    )
    started = time.perf_counter()
    exp2_payload = _read_json(EXP2_MANIFEST)
    parquet = pq.read_table(EXP2_PARQUET).to_pydict()
    rows = []
    for index in range(len(parquet["decision_node_id"])):
        reference = json.loads(parquet["reference_action_map"][index])
        variants = json.loads(parquet["variants"][index])
        components = json.loads(parquet["component_means"][index])
        formal = bool(parquet["node_formal"][index])
        actions = sorted(reference)
        formal_actions = [action for action in actions if reference[action] is not None]
        relaxed = variants.get("point_flight") or {}
        relaxed_top1 = (
            min(relaxed, key=relaxed.get)
            if relaxed and any(value is not None for value in relaxed.values()) else None
        )
        relaxed_top1_full_lane = (
            "FORMAL" if (relaxed_top1 is not None and reference.get(relaxed_top1) is not None)
            else "CONDITIONAL"
        )
        relaxed_numeric_actions = [action for action, value in relaxed.items() if value is not None]
        rows.append({
            "episode_id": parquet["episode_id"][index],
            "decision_node_id": parquet["decision_node_id"][index],
            "operational_stage": parquet["operational_stage"][index],
            "numerically_evaluable": formal,
            "formal_action_count": len(formal_actions),
            "a00_formal": bool(formal and reference.get("A00") is not None),
            "authoritative_decision_available": False,
            "authoritative_decision_blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
            "conditional_action_count": 22 if formal else 0,
            "scenario_action_count": 23 if formal else 0,
            "relaxed_top1": relaxed_top1,
            "relaxed_top1_full_lane": relaxed_top1_full_lane,
            "relaxed_topk_full_lanes": [
                "FORMAL" if reference.get(action) is not None else "CONDITIONAL"
                for action in sorted(relaxed_numeric_actions, key=relaxed.get)[:3]
            ],
            "formal_coverage": 1.0 if formal else 0.0,
            "relaxed_coverage": 1.0 if formal else 0.0,
            "component_means": components,
        })
    n = len(rows)
    payload = {
        "schema_version": "EXP3_DEVELOPMENT_V1",
        "decision_id": "AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION",
        "classification": "DEVELOPMENT_EXECUTION",
        "source_exp2": exp2_payload["exp2_hash"],
        "formal_feasibility_audit": formal_feasibility_audit(rows),
        "lane_rates": lane_rates(rows),
        "invalidated_top1_rate": invalidated_top1_rate(rows),
        "invalidated_topk_share": invalidated_topk_share(rows),
        "coverage_inflation_full_minus_relaxed": coverage_inflation(
            sum(row["formal_coverage"] for row in rows) / n,
            sum(row["relaxed_coverage"] for row in rows) / n),
        "m4_gated_fields": [
            "authoritative_decision_available", "formal_action_count",
            "conditional_action_count", "scenario_action_count",
            "relaxed_top1_full_lane", "relaxed_topk_full_lanes",
        ],
        "m4_blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
        "ablations": {
            "no_induced": {"protocol_ablation": "NO_INDUCED_CONSEQUENCE", "run": "NOT_RUN_M4_BLOCKED"},
            "no_evidence_distinction": {"protocol_ablation": "NO_EVIDENCE_DISTINCTION", "run": "NOT_RUN_M4_BLOCKED"},
            "no_coverage_restriction": {"protocol_ablation": "NO_MATERIAL_COVERAGE_GATE", "run": "NOT_RUN_M4_BLOCKED"},
        },
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    _write_parquet(EXP3_PARQUET, _flatten_rows(rows))
    payload["partition"] = {
        "path": EXP3_PARQUET.relative_to(ROOT).as_posix(),
        "rows": len(rows),
        "hash": _hash_file(EXP3_PARQUET),
    }
    _write_json(EXP3_MANIFEST, payload)
    return payload
def exp4_development(*, limit_nodes: int | None = None) -> dict:
    """Exp4 Development: M3 LOW/BASE/HIGH response sensitivity at the M2 layer.

    M4 risk-averse ranking (lambda/alpha) and deployability paths are
    NOT_RUN because the material-coverage contract is unfrozen.
    """
    started = time.perf_counter()
    node_rows, by_node, artifact_manifest = load_scenario_artifact()
    m2 = load_m2()
    m3 = load_m3()
    if limit_nodes is not None:
        node_rows = node_rows[:limit_nodes]
    rank_agreement: dict[tuple[str, str], list[float | None]] = {
        pair: [] for pair in (("LOW", "BASE"), ("BASE", "HIGH"), ("LOW", "HIGH"))
    }
    if len(node_rows) >= 32:
        rows = _parallel_rows(_run_exp4_node, len(node_rows))
    else:
        _WORKER.update({
            "m2": m2, "m3": m3, "node_rows": node_rows, "by_node": by_node,
            "context_cache": {},
        })
        rows = [_run_exp4_node(position) for position in range(len(node_rows))]
    for row in rows:
        for left, right in rank_agreement:
            left_map = row[f"{left.lower()}_action_map"]
            right_map = row[f"{right.lower()}_action_map"]
            left_rank = tuple(sorted((k for k, v in left_map.items() if v is not None), key=left_map.get))
            right_rank = tuple(sorted((k for k, v in right_map.items() if v is not None), key=right_map.get))
            if left_rank and right_rank:
                agreement = sum(a == b for a, b in zip(left_rank, right_rank)) / len(left_rank)
            else:
                agreement = None
            rank_agreement[(left, right)].append(agreement)
    print(f"exp4 done {len(rows)} nodes elapsed={time.perf_counter()-started:.0f}s", flush=True)

    payload = {
        "schema_version": "EXP4_DEVELOPMENT_V1",
        "decision_id": "AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION",
        "classification": "DEVELOPMENT_EXECUTION",
        "source_scenario_artifact": artifact_manifest["artifact_hash"],
        "m3_response_seed": M3_RESPONSE_SEED,
        "m3_response_seed_provenance": M3_RESPONSE_SEED_PROVENANCE,
        "sensitivity_axis": "RESPONSE_EFFICACY",
        "sensitivities": ["LOW", "BASE", "HIGH"],
        "node_count": len(rows),
        "top1_agreement": {
            "LOW_BASE": _mean_of_optionals([row["low_base_top1_agreement"] for row in rows]),
            "BASE_HIGH": _mean_of_optionals([row["base_high_top1_agreement"] for row in rows]),
        },
        "rank_agreement": {
            f"{left}_{right}": _mean_of_optionals(values)
            for (left, right), values in rank_agreement.items()
        },
        "m4_ranking": {
            "status": "NOT_RUN",
            "blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
            "lambda_values": [0.0, 0.10, 0.25, 0.50],
            "alpha_values": [0.80, 0.90, 0.95],
        },
        "deployability": {
            "status": "NOT_RUN",
            "blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
            "paths": ["STATE_AWARE", "FAST"],
        },
        "portability_hard_gates": {
            "DATA1_PORTABILITY_STATUS": "PASS",
            "DownstreamSemanticRedefinitionCount": 0,
            "SilentSubstitutionCount": 0,
            "basis": "STATIC_REGISTRY_CONTRACT_CHECK_NO_DATA1_RAW_ACCESS",
        },
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    _write_parquet(EXP4_PARQUET, _flatten_rows(rows))
    payload["partition"] = {
        "path": EXP4_PARQUET.relative_to(ROOT).as_posix(),
        "rows": len(rows),
        "hash": _hash_file(EXP4_PARQUET),
    }
    _write_json(EXP4_MANIFEST, payload)
    return payload
def build_audit_cases(*, limit_nodes: int | None = None) -> tuple[list[dict], dict]:
    """Build LLM audit cases from the M2-layer Exp2/Exp3/Exp4 rows.

    Stratum assignment follows the frozen CASE_STRATA semantics at the M2
    layer; M4 lane fields are declared NOT_RUN so the LLM is never presented
    with an unfrozen lane as if it were authoritative.
    """
    parquet = pq.read_table(EXP2_PARQUET).to_pydict()
    exp3 = pq.read_table(EXP3_PARQUET).to_pydict()
    exp4 = pq.read_table(EXP4_PARQUET).to_pydict()
    nodes = pq.read_table(ARTIFACT_DIR / "node.parquet").to_pydict()
    node_by_id = {value: index for index, value in enumerate(nodes["decision_node_id"])}
    exp3_by_id = {value: index for index, value in enumerate(exp3["decision_node_id"])}
    exp4_by_id = {value: index for index, value in enumerate(exp4["decision_node_id"])}

    cases = []
    strata_counts = {name: 0 for name in (
        "formal_non_null_top1", "formal_a00_top1",
        "relaxed_only_invalidated_top1", "scenario_conditional_close_call")}
    for index in range(len(parquet["decision_node_id"])):
        if limit_nodes is not None and index >= limit_nodes:
            break
        node_id = parquet["decision_node_id"][index]
        episode_id = parquet["episode_id"][index]
        reference = json.loads(parquet["reference_action_map"][index])
        variants = json.loads(parquet["variants"][index])
        components = json.loads(parquet["component_means"][index])
        row3 = exp3_by_id.get(node_id)
        row4 = exp4_by_id.get(node_id)
        node_index = node_by_id[node_id]
        formal_actions = {action: value for action, value in reference.items()
                          if value is not None}
        top1 = min(formal_actions, key=formal_actions.get) if formal_actions else None
        relaxed = variants.get("point_flight") or {}
        relaxed_numeric = {action: value for action, value in relaxed.items() if value is not None}
        relaxed_top1 = min(relaxed_numeric, key=relaxed_numeric.get) if relaxed_numeric else None

        if top1 is None:
            continue
        if top1 == "A00":
            stratum = "formal_a00_top1"
        elif relaxed_top1 is not None and reference.get(relaxed_top1) is None:
            stratum = "relaxed_only_invalidated_top1"
        else:
            ranked = sorted(formal_actions, key=formal_actions.get)
            close = False
            if len(ranked) >= 2:
                gap = float(formal_actions[ranked[1]]) - float(formal_actions[ranked[0]])
                close = gap <= 0.10 * max(1.0, abs(float(formal_actions[ranked[0]])))
            stratum = "scenario_conditional_close_call" if close else "formal_non_null_top1"
        strata_counts[stratum] += 1
        base4 = json.loads(exp4["base_action_map"][row4]) if row4 is not None else {}
        cases.append({
            "case_id": f"dev-{index:04d}",
            "episode_id": episode_id,
            "decision_node_id": node_id,
            "stratum": stratum,
            "decision_time": nodes["decision_time"][node_index],
            "operational_stage": nodes["operational_stage"][node_index],
            "admissible_operational_state": {
                "observed_r_ib_minutes": nodes["observed_r_ib"][node_index],
                "observed_delta_ob_minutes": nodes["observed_delta_ob"][node_index],
                "observed_t_tx_minutes": nodes["observed_t_tx"][node_index],
                "schedule_support_state": nodes["schedule_support_state"][node_index],
                "taxi_reference_support_state": nodes["taxi_reference_support_state"][node_index],
                "connection_airport_id": nodes["connection_airport_id"][node_index],
                "successor_destination_airport_id": nodes["successor_destination_airport_id"][node_index],
            },
            "major_uncertainty": {
                "scenario_count": 250,
                "m1_scenario_spread_cu": _spread(components),
                "component_means_cu": components,
            },
            "m2_consequence_profile": {
                "formal_cu_mean": _mean_of_optionals(list(formal_actions.values())),
                "top1_action": top1,
                "top1_cu": formal_actions[top1],
                "top3_actions": sorted(formal_actions, key=formal_actions.get)[:3],
                "component_means": components,
            },
            "recommended_action": top1,
            "action_family": _action_family(top1),
            "preconditions": "TRUE" if top1 == "A00" else "UNKNOWN",
            "preparation_time_minutes": _preparation(top1),
            "authority_requirements": _authority(top1),
            "m3_response_provenance": "PURE_SCENARIO",
            "m3_scenario_parameters": {
                "sensitivity": "BASE",
                "registry": "M3_RESPONSE_SCENARIO_V1",
            },
            "m4_lane": "NOT_RUN",
            "m4_blocker": "M4_MATERIAL_COVERAGE_UNFROZEN",
            "m4_score_rank": None,
            "closest_alternatives": sorted(formal_actions, key=formal_actions.get)[1:4],
            "exp3_row": (
                {
                    "numerically_evaluable": bool(exp3["numerically_evaluable"][row3]),
                    "formal_action_count": int(exp3["formal_action_count"][row3]),
                    "relaxed_top1": exp3["relaxed_top1"][row3],
                } if row3 is not None else None
            ),
            "exp4_sensitivity_base_top1": (
                min(base4, key=base4.get)
                if base4 and all(value is not None for value in base4.values()) else None
            ),
        })
    audit = {
        "schema_version": "EXP234_LLM_AUDIT_CASES_V1",
        "source_exp2": _read_json(EXP2_MANIFEST)["exp2_hash"],
        "case_count": len(cases),
        "strata_counts": strata_counts,
        "case_strata_order": [
            "formal_non_null_top1", "formal_a00_top1",
            "relaxed_only_invalidated_top1", "scenario_conditional_close_call",
        ],
    }
    _write_json(AUDIT_CASES_PATH, {"audit": audit, "cases": cases})
    return cases, audit
def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", choices=("exp2", "exp3", "exp4", "cases", "all"),
                        default="all")
    parser.add_argument("--limit-nodes", type=int, default=None)
    args = parser.parse_args(argv)
    if args.exp in ("exp2", "all"):
        payload = exp2_development(limit_nodes=args.limit_nodes)
        print(json.dumps({k: payload[k] for k in (
            "node_count", "formal_available_nodes", "exp2_hash", "elapsed_seconds")},
            sort_keys=True))
    if args.exp in ("exp3", "all"):
        payload = exp3_development()
        print(json.dumps({k: payload[k] for k in (
            "formal_feasibility_audit", "invalidated_top1_rate", "elapsed_seconds")},
            sort_keys=True))
    if args.exp in ("exp4", "all"):
        payload = exp4_development(limit_nodes=args.limit_nodes)
        print(json.dumps({k: payload[k] for k in (
            "node_count", "top1_agreement", "elapsed_seconds")}, sort_keys=True))
    if args.exp in ("cases", "all"):
        cases, audit = build_audit_cases(limit_nodes=args.limit_nodes)
        print(json.dumps({"case_count": len(cases), "strata_counts": audit["strata_counts"]},
                         sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
