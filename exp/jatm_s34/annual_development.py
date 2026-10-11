"""Bounded annual E1--E4 Development orchestration.

This runner consumes only the annual input adapter and writes versioned
year-specific outputs.  It does not invoke the M5-b consequence battery and
has no Test or Final-Test path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .annual_bridge import load_annual_bridge
from .annual_inputs import validate_year
from .e1_information_gain import run as run_e1
from .e2_e3_exact import run as run_e2_e3


def run_year(*, year: int, output_root: Path, node_limit: int | None = None, bootstrap_replicates: int = 2000) -> dict:
    contract = validate_year(year)
    result = {
        "schema_version": "JATM_ANNUAL_DEVELOPMENT_V1",
        "year": int(year),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_contract": contract.as_dict(),
        "final_test_access_count": 0,
    }
    if not contract.audit.get("annual_m1_main_model_available"):
        result["status"] = "DATA_INSUFFICIENT"
        result["scientific_status"] = "DATA_INSUFFICIENT"
        result["blocking_reason"] = "ANNUAL_M1_MAIN_MODEL_MISSING"
        Path(output_root).mkdir(parents=True, exist_ok=True)
        (Path(output_root) / "ANNUAL_DEVELOPMENT_MANIFEST.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        return result
    context = load_annual_bridge(year=int(year), n=4096, node_limit=node_limit)
    out = Path(output_root).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result["e1"] = run_e1(
        output_root=out / "E1",
        node_limit=node_limit,
        bootstrap_replicates=bootstrap_replicates,
        annual_context=context,
    )
    result["e2_e3"] = run_e2_e3(
        output_root=out / "E2_E3",
        node_limit=node_limit,
        annual_context=context,
    )
    result["status"] = "DEVELOPMENT_COMPLETE"
    result["scientific_status"] = "DEVELOPMENT_OBSERVATION_READY"
    (out / "ANNUAL_DEVELOPMENT_MANIFEST.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return result


__all__ = ["run_year"]
