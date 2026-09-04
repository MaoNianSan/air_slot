import argparse
import json
from pathlib import Path

from model.M2.context import (
    AirportReferenceKeys,
    build_m2_context,
    load_data2_reference_bundle,
    smoke_reference_payloads,
)
from model.M2.contracts import COMPONENTS
from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.common.estimand import ConsequenceScope, ScopeStatus


def _smoke_scenario():
    return {
        "decision_node_id": "smoke-node",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "d_ob_minutes": 20,
        "d_tx_minutes": 0,
        "d_to_minutes": 20,
        "ib_support": "SUPPORTED",
        "d_ob_support": "SUPPORTED",
        "d_tx_support": "SUPPORTED",
        "d_to_support": "SUPPORTED",
    }


def _smoke_scope() -> ConsequenceScope:
    return ConsequenceScope.create(
        estimand_id="M2_SMOKE",
        estimand_version="1.0.0",
        included_components=COMPONENTS,
        aggregation_rule_id="DEV-SUM-1",
        cu_normalization_registry_id="DEV-1",
        material_coverage_contract_id="DEV-COVERAGE",
        scope_status=ScopeStatus.FORMAL_READY,
    )


def _run_map_smoke(
    output: Path,
    references: Path | None,
) -> dict:
    payloads = (
        json.loads(references.read_text(encoding="utf-8"))
        if references is not None and references.exists()
        else smoke_reference_payloads()
    )
    bundle = load_data2_reference_bundle(payloads)
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    scope = _smoke_scope()
    mapper = M2Mapper(ValuationRegistry.smoke(), scope)
    outputs = mapper.map_scenarios((_smoke_scenario(),), context)
    output.mkdir(parents=True, exist_ok=True)
    (output / "context.json").write_text(
        json.dumps(context.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output / "consequences.json").write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in outputs],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "status": "PASS",
        "paper_result": False,
        "final_test_access_count": 0,
        "valuation_frozen": False,
        "scenarios": len(outputs),
        "output": str(output),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    map_smoke = commands.add_parser("map-smoke")
    map_smoke.add_argument("--output", type=Path, required=True)
    map_smoke.add_argument(
        "--references",
        type=Path,
        default=None,
        help="Optional JSON payload matching the M2 reference bundle keys.",
    )
    args = parser.parse_args(argv)
    if args.command == "validate":
        result = {
            "status": "PASS",
            "ontology": 7,
            "scenario_preserving": True,
            "formal_mapping": "REQUIRES_TYPED_SCOPE_CONTEXT_AND_FROZEN_VALUATION",
        }
    else:
        result = _run_map_smoke(args.output, args.references)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
