"""Materialize a transparent, test-only CU -> RMB freeze candidate.

The candidate is deliberately a unit-normalized constructed representation:
``RMB_k = 1.0 * CU_k``.  Literature supports the consequence mechanisms and
recovery domains, not an observed-currency coefficient.  Therefore this
registry is executable for Development sensitivity checks only and cannot
support an authoritative monetary or causal claim.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.identity import content_id
from model.common.rmb_mapping import (
    RMBMappingFunction,
    RMBMappingParameter,
    RMBMappingRegistry,
    RMBMappingRule,
    RMBMappingStatus,
    RMBSourceType,
)


DESIGN = Path("registries/m4_cu_rmb_mapping_design_v2.json")
FREEZE_ID = "M4_RMB_MAPPING_FREEZE_CANDIDATE_20260823"
PARAMETER_VERSION = "RMB_CANDIDATE_UNIT_NORMALIZATION_V1"
SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "EXP3_RUNS": 0,
    "EXP4_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "FULL": False,
    "PAPER_FULL_RUN": False,
}

LITERATURE = {
    "HASSAN_SANTOS_VINK_2021": {
        "citation": "Hassan, Santos, Vink (2021), Computers and Operations Research 127:105137",
        "doi": "10.1016/j.cor.2020.105137",
        "role": "review of aircraft, crew, passenger, and integrated recovery domains",
    },
    "SU_ET_AL_2021": {
        "citation": "Su et al. (2021), Engineering 7(4):435-447",
        "doi": "10.1016/j.eng.2020.08.021",
        "role": "review of disruption-management models and solution methods",
    },
    "HU_SONG_ZHAO_XU_2016": {
        "citation": "Hu, Song, Zhao, Xu (2016), Transportation Research Part E 87:97-112",
        "doi": "10.1016/j.tre.2016.01.002",
        "role": "integrated aircraft/passenger recovery and recovery-cost mechanism",
    },
    "SANTANA_DE_LA_VEGA_MORABITO_PUREZA_2023": {
        "citation": "Santana, De La Vega, Morabito, Pureza (2023), EURO Journal on Transportation and Logistics 12:100117",
        "doi": "10.1016/j.ejtl.2023.100117",
        "role": "systematic review of aircraft-recovery decisions and operational consequences",
    },
}

COMPONENT_EVIDENCE = {
    "F_continuity": {
        "effect_mechanism": "schedule and aircraft continuity disruption/recovery",
        "literature_keys": ["HASSAN_SANTOS_VINK_2021", "SANTANA_DE_LA_VEGA_MORABITO_PUREZA_2023"],
    },
    "F_execution": {
        "effect_mechanism": "feasibility of executing the recovered flight plan under operational constraints",
        "literature_keys": ["SU_ET_AL_2021", "SANTANA_DE_LA_VEGA_MORABITO_PUREZA_2023"],
    },
    "F_propagation": {
        "effect_mechanism": "downstream propagation across linked flights/resources",
        "literature_keys": ["HASSAN_SANTOS_VINK_2021", "SU_ET_AL_2021"],
    },
    "P_time": {
        "effect_mechanism": "passenger delay/exposure associated with disruption and recovery",
        "literature_keys": ["HASSAN_SANTOS_VINK_2021", "HU_SONG_ZHAO_XU_2016"],
    },
    "P_itinerary": {
        "effect_mechanism": "passenger connection and reaccommodation disruption",
        "literature_keys": ["HU_SONG_ZHAO_XU_2016", "HASSAN_SANTOS_VINK_2021"],
    },
    "P_service": {
        "effect_mechanism": "passenger service/recovery burden under irregular operations",
        "literature_keys": ["HASSAN_SANTOS_VINK_2021", "HU_SONG_ZHAO_XU_2016"],
    },
    "R_operating": {
        "effect_mechanism": "operational resource and recovery burden",
        "literature_keys": ["SU_ET_AL_2021", "SANTANA_DE_LA_VEGA_MORABITO_PUREZA_2023"],
    },
}


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"M4_RMB_FREEZE_CANDIDATE_OUTPUT_CONFLICT:{path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def _rule(component: str) -> RMBMappingRule:
    source_refs = tuple(LITERATURE[key]["doi"] for key in COMPONENT_EVIDENCE[component]["literature_keys"])
    return RMBMappingRule.create(
        component_id=component,
        mapping_function=RMBMappingFunction.LINEAR_SCALE,
        parameter_version=PARAMETER_VERSION,
        source_type=RMBSourceType.SCENARIO_ASSUMPTION,
        reference=source_refs + ("SCENARIO_ASSUMPTION_UNIT_NORMALIZATION",),
        freeze_id=FREEZE_ID,
        parameters=(
            RMBMappingParameter(
                parameter_name="rmb_per_cu",
                value=1.0,
                unit="constructed_RMB_per_CU",
                provenance=(
                    "SCENARIO_ASSUMPTION_UNIT_NORMALIZATION",
                    "NO_OBSERVED_CURRENCY_CALIBRATION",
                ),
            ),
        ),
        provenance=(
            "M4_RMB_MAPPING_FREEZE_CANDIDATE_20260823",
            "LITERATURE_SUPPORTS_MECHANISM_NOT_NUMERIC_COEFFICIENT",
            "RMB_IS_CONSTRUCTED_NOT_REAL_CURRENCY",
        ),
        rule_id=f"RMB_CANDIDATE_{component}_V1",
    )


def materialize(*, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    root = Path(root).resolve()
    output_root = (output_root or root / "artifacts/diagnostics/m4_rmb_mapping_freeze_candidate_v1").resolve()
    design_path = root / DESIGN
    if not design_path.is_file():
        raise RuntimeError("M4_RMB_FREEZE_CANDIDATE_DESIGN_MISSING")
    design = _load(design_path)
    if tuple(design.get("component_order", ())) != CONSEQUENCE_COMPONENTS:
        raise RuntimeError("M4_RMB_FREEZE_CANDIDATE_COMPONENT_ORDER_INVALID")
    mappings = {component: _rule(component) for component in CONSEQUENCE_COMPONENTS}
    registry = RMBMappingRegistry(
        registry_id="M4_CU_RMB_MAPPING_CANDIDATE_V1",
        registry_version=PARAMETER_VERSION,
        status=RMBMappingStatus.TEST_ONLY,
        freeze_id=FREEZE_ID,
        reference_period="DEVELOPMENT_SENSITIVITY_ONLY",
        component_mappings=mappings,
        provenance=(
            "M4_RMB_MAPPING_FREEZE_CANDIDATE_20260823",
            "CONSTRUCTED_UNIT_NORMALIZATION",
            "LITERATURE_MECHANISM_SUPPORT_ONLY",
        ),
        monetary_ground_truth_claim=False,
        scenario_dependent=True,
        final_test_access_count=0,
        paper_full_run=False,
    )
    registry_payload = registry.model_dump(mode="json")
    registry_payload["registry_hash"] = registry.digest()
    registry_path = root / "registries/m4_cu_rmb_mapping_candidate_v1.json"
    _write(registry_path, registry_payload)

    component_rows = []
    for component in CONSEQUENCE_COMPONENTS:
        evidence = COMPONENT_EVIDENCE[component]
        component_rows.append(
            {
                "component_id": component,
                "c_to_cu_formula": f"CU_{component} = g_{component}(C_{component})",
                "cu_to_rmb_formula": f"RMB_{component} = 1.0 * CU_{component}",
                "parameter_name": "rmb_per_cu",
                "parameter_value": 1.0,
                "parameter_unit": "constructed_RMB_per_CU",
                "parameter_source": "SCENARIO_ASSUMPTION_UNIT_NORMALIZATION",
                "literature_basis": [LITERATURE[key] for key in evidence["literature_keys"]],
                "effect_mechanism": evidence["effect_mechanism"],
                "assumption_level": "CONSTRUCTED_SCENARIO_SCALE_NOT_EMPIRICALLY_CALIBRATED",
                "sensitivity_plan": {
                    "global_scale_values": [0.5, 1.0, 2.0],
                    "component_one_at_a_time": "0.5x, 1.0x, 2.0x with all other components fixed",
                    "selection_rule": "no Development-based selection; report sensitivity only",
                },
                "support_boundary": "P_itinerary and P_service remain ABSTAIN when upstream CU is unsupported",
            }
        )
    candidate = {
        "schema_version": "M4_RMB_MAPPING_FREEZE_CANDIDATE_V1",
        "status": "RMB_MAPPING_FREEZE_CANDIDATE_MATERIALIZED",
        "freeze_status": "TEST_ONLY",
        "registry_id": registry.registry_id,
        "registry_hash": registry.digest(),
        "freeze_id": FREEZE_ID,
        "chain": "C -> CU -> RMB -> risk",
        "mapping_contract": {
            "c_to_cu": "CU_k = g_k(C_k)",
            "cu_to_rmb": "RMB_k = f_k(CU_k)",
            "candidate_function": "RMB_k = 1.0 * CU_k",
            "aggregation": "RMB = SUM_k RMB_k",
        },
        "component_order": list(CONSEQUENCE_COMPONENTS),
        "components": component_rows,
        "scientific_boundary": {
            "rmb_is_constructed": True,
            "cu_is_not_monetary": True,
            "real_currency_claim": False,
            "monetary_ground_truth_claim": False,
            "causal_action_effect_claim": False,
            "authoritative_ranking_allowed": False,
            "development_sensitivity_use_only": True,
        },
        "literature_scope": "Literature supports disruption/recovery mechanisms and consequence domains; it does not identify these numeric constructed-unit coefficients.",
        "inputs": {"design": {"path": DESIGN.as_posix(), "sha256": _hash(design_path)}},
        "safety": dict(SAFETY),
    }
    candidate["artifact_hash"] = content_id(candidate)
    artifact_path = output_root / "M4_RMB_MAPPING_FREEZE_CANDIDATE.json"
    _write(artifact_path, candidate)
    manifest = {
        "schema_version": "M4_RMB_MAPPING_FREEZE_CANDIDATE_MANIFEST_V1",
        "status": candidate["status"],
        "freeze_status": candidate["freeze_status"],
        "candidate_artifact": str(artifact_path.resolve()),
        "candidate_artifact_hash": candidate["artifact_hash"],
        "registry": str(registry_path.resolve()),
        "registry_hash": registry.digest(),
        "sensitivity_plan": "global 0.5/1.0/2.0 plus one-at-a-time component scaling; no selection",
        "safety": dict(SAFETY),
    }
    manifest_path = output_root / "M4_RMB_MAPPING_FREEZE_CANDIDATE_MANIFEST.json"
    _write(manifest_path, manifest)
    return {"candidate": artifact_path, "registry": registry_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize the transparent test-only RMB mapping freeze candidate.")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    materialize(root=Path(__file__).resolve().parents[1], output_root=args.output_root)
    print("RMB_MAPPING_FREEZE_CANDIDATE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
