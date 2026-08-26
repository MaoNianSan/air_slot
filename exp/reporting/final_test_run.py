"""Final Test chain orchestrator (D6 scope, 2026-08-26, HP1=A).

Reruns the record materialization + figures + Table 1 under the frozen spec
(PAPER_OUTPUT_SPEC_V1.json + Exp1 addendum) with the shared T-cal calibration
artifact applied in memory to the frozen STATE_AWARE H32 and CURRENT-only
checkpoints.  Same Development cohort (1,769 nodes; the Final Test split is
never read), same seeds (20260813 scenarios / 20260825 bootstrap),
paper_result=true outputs only in the new roots:
  artifacts/paper_results_v1/            (records + manifests)
  outputs/manuscript_values/section5_secondary_analysis/paper/  (figures/tables)

Boundaries: no retraining, no model/** or configs/** edits, no frozen artifact
rewrites, no Git.  Every stage records input hashes, seeds, the calibration
artifact hash, and safety counters.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from exp.common.official_execution import file_sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
PAPER_ROOT = Path("artifacts/paper_results_v1")
PAPER_OUTPUT_ROOT = Path("outputs/manuscript_values/section5_secondary_analysis/paper")
CALIBRATION_ARTIFACT = Path(
    "artifacts/calibration/m1_v2_calibration_20260826/M1_V2_CALIBRATION_ARTIFACT.json"
)
DEV_INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
FT_SCENARIO_ROOT = PAPER_ROOT / "scenarios"
FT_EXP2_ROOT = PAPER_ROOT / "exp2"
FT_EXP1_ROOT = PAPER_ROOT / "exp1"
FT_EXP2A_ROOT = PAPER_ROOT / "exp2a"
FT_EXP3_ROOT = PAPER_ROOT / "exp3"
FT_EXP2B_ROOT = PAPER_ROOT / "exp2b"
FT_VALUATION_ROOT = PAPER_ROOT / "exp3_valuation"
FT_REFRESH_SYNC_ROOT = PAPER_ROOT / "exp3_refresh_sync"
FT_EXP4_ROOT = PAPER_ROOT / "exp4"
FT_M3M4_ROOT = PAPER_ROOT / "m3m4"
CHAIN_MANIFEST = PAPER_ROOT / "FINAL_TEST_CHAIN_MANIFEST.json"
CALIBRATION_ARTIFACT_REL = CALIBRATION_ARTIFACT
SCENARIO_MANIFEST = FT_SCENARIO_ROOT / "FINAL_TEST_SCENARIO_MANIFEST.json"
FT_SCOPE = "FINAL_TEST_CALIBRATED_REMATERIALIZATION_DEVELOPMENT_COHORT"
FT_SCENARIO_HISTORY = "M1_V2_FINAL_TEST_TYPED_SCENARIOS_HISTORY.parquet"
FT_SCENARIO_CURRENT = "M1_V2_FINAL_TEST_TYPED_SCENARIOS_CURRENT.parquet"
REGISTRY_V2_PATH = Path("registries/m4_eur_mapping_assumption_grounded_v2.json")
REGISTRY_V2_HASH = "sha256:befc10aab3a9b9ca5292ac82331e728f7d28b1546077725ab7cdf5564fcbc072"
PENDING_ABSTAIN_STATUS = "ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY"
SAFETY = {
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "MODEL_RETRAINED": False,
}
SCHEMA_VERSION = "AIR_SLOT_FINAL_TEST_CHAIN_MANIFEST_V1"
FINAL_TEST_ACCESS_NOTE = (
    "FINAL_TEST_ACCESS_COUNT=0 means the Final Test split file was never read; "
    "paper_result=true follows spec D6 (calibrated rematerialization on the frozen "
    "Development cohort of 1,769 nodes with the shared T-cal artifact applied in memory)."
)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _content_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _override(module: Any, mapping: dict[str, Any]) -> Iterator[None]:
    saved = {name: getattr(module, name) for name in mapping}
    try:
        for name, value in mapping.items():
            setattr(module, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(module, name, value)


def _rename_and_patch(
    directory: Path,
    renames: dict[str, str],
    manifest_name: str | None = None,
    manifest_updates: dict[str, Any] | None = None,
    hash_field: str = "manifest_hash",
) -> None:
    """Rename newly written files (DEVELOPMENT_ONLY -> FINAL_TEST) and patch a
    stage manifest so its outputs and scope fields stay truthful.  New FT-root
    files only; no frozen artifact is touched."""
    for old_name, new_name in renames.items():
        source = directory / old_name
        if source.is_file():
            (directory / new_name).write_bytes(source.read_bytes())
            source.unlink()
    if manifest_name is not None:
        path = directory / manifest_name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            for key, value in (manifest_updates or {}).items():
                payload[key] = value
            if hash_field and hash_field in payload:
                payload[hash_field] = _content_hash(payload)
            write_json(path, payload)


def stage_scenarios(root: Path) -> dict[str, Any]:
    from exp.reporting.final_test_scenarios import run as run_scenarios

    paths = run_scenarios(root=root)
    manifest_path = root / SCENARIO_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Patch the FT manifest with the top-level fields consumed by the Exp2/Exp1/Exp2A
    # materialization stages (their dev manifests carry these fields).
    history_entry = manifest["models"]["M1_V2_GRU_H32"]
    manifest["artifact"] = history_entry["artifact"]
    manifest["artifact_hash"] = history_entry["artifact_hash"]
    manifest["model_id"] = "M1_V2_GRU_H32"
    manifest["crn_paired_with_history_scenarios"] = True
    manifest["manifest_hash"] = _content_hash(manifest)
    write_json(manifest_path, manifest)
    # Exp2 materialization reads the scenario manifest under its historical
    # filename; write a byte-identical copy under that name in the FT root.
    write_json(
        root / FT_SCENARIO_ROOT / "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json",
        manifest,
    )
    return {
        "status": "MATERIALIZED",
        "history": str(paths["history"].relative_to(root)).replace("\\", "/"),
        "current": str(paths["current"].relative_to(root)).replace("\\", "/"),
        "manifest_hash": manifest.get("manifest_hash"),
        "artifact_hash": manifest["models"]["M1_V2_GRU_H32"]["artifact_hash"],
    }


def stage_exp2(root: Path) -> dict[str, Any]:
    from exp.exp2.global_development import run as run_exp2
    import exp.exp2.global_development as exp2_module

    output_root = (root / FT_EXP2_ROOT).resolve()
    with _override(exp2_module, {"EUR_MAPPING_REGISTRY": REGISTRY_V2_PATH}):
        result = run_exp2(
            root=root,
            scenario_root=root / FT_SCENARIO_ROOT,
            input_root=root / DEV_INPUT_ROOT,
            output_root=output_root,
        )
    manifest_path = result["manifest"]
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["paper_result"] = True
    payload["scope"] = FT_SCOPE
    payload["registry"] = str(REGISTRY_V2_PATH)
    payload["calibration_artifact_hash"] = _artifact_hash(root)
    payload["safety"] = dict(SAFETY)
    payload["artifact_hash"] = _content_hash(payload)
    write_json(manifest_path, payload)
    return {
        "status": "MATERIALIZED",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "consequences": str(result["consequences"].relative_to(root)).replace("\\", "/"),
    }


def stage_exp1(root: Path) -> dict[str, Any]:
    import exp.exp1.closure as closure

    output_root = (root / FT_EXP1_ROOT).resolve()

    def _ft_preflight(closure_root: Path, closure_output_root: Path) -> dict[str, Any]:
        from exp.common.official_execution import load_official_frozen_binding

        scenario_manifest = closure._load_json(closure_root / closure.SCENARIO_MANIFEST)
        input_manifest = closure._load_json(closure_root / closure.INPUT_MANIFEST)
        _require(
            closure._sha256_file(closure_root / closure.SCENARIOS)
            == scenario_manifest["artifact_hash"],
            "FT_EXP1_SCENARIO_HASH_MISMATCH",
        )
        _require(
            closure._sha256_file(closure_root / closure.CONSEQUENCES)
            == json.loads(
                (closure_root / FT_EXP2_ROOT / "EXP2_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json")
                .read_text(encoding="utf-8")
            )["artifact_hashes"]["consequences"],
            "FT_EXP1_M2_HASH_MISMATCH",
        )
        return {
            "status": "EXP1_FINAL_TEST_PREFLIGHT_READY",
            "scope": "FINAL_TEST_CALIBRATED_REMATERIALIZATION_DEVELOPMENT_COHORT",
            "scenario_artifact_hash": scenario_manifest["artifact_hash"],
            "frozen": load_official_frozen_binding(closure_root).as_dict(),
        }

    overrides = {
        "SCENARIOS": FT_SCENARIO_ROOT / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_HISTORY.parquet",
        "SCENARIO_MANIFEST": SCENARIO_MANIFEST,
        "CURRENT_SCENARIOS": FT_SCENARIO_ROOT / "M1_V2_FINAL_TEST_TYPED_SCENARIOS_CURRENT.parquet",
        "CURRENT_SCENARIO_MANIFEST": SCENARIO_MANIFEST,
        "CONSEQUENCES": FT_EXP2_ROOT / "M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet",
        "LABELS": DEV_INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_LABELS.json",
        "INFERENCE_INPUTS": DEV_INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json",
        "INPUT_MANIFEST": DEV_INPUT_ROOT / "FULL_DEVELOPMENT_INPUT_MANIFEST.json",
        "CURRENT_TRAINING_METRICS": Path(
            "artifacts/experiment/exp1_full_development/exp1_closure_20260825/"
            "EXP1B_CURRENT_ONLY_H32/M1_V2_CURRENT_ONLY_FAST_TRAIN_METRICS.json"
        ),
        "preflight": _ft_preflight,
    }
    with _override(closure, overrides):
        summary = closure.run(root=root, output_root=output_root)

    renames = {
        "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY.csv": "EXP1A_PAPER_FACING_RECORDS_FINAL_TEST.csv",
        "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP1A_PAPER_FACING_RECORDS_FINAL_TEST.parquet",
        "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY.csv": "EXP1B_PREDICTION_RECORDS_FINAL_TEST.csv",
        "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP1B_PREDICTION_RECORDS_FINAL_TEST.parquet",
        "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY.csv": "EXP1A_FROZEN_SORTING_DIAGNOSTIC_FINAL_TEST.csv",
        "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY.parquet": "EXP1A_FROZEN_SORTING_DIAGNOSTIC_FINAL_TEST.parquet",
        "EXP1_DEVELOPMENT_CLOSURE_SUMMARY_DEVELOPMENT_ONLY.json": "EXP1_FINAL_TEST_CLOSURE_SUMMARY.json",
        "EXP1_INTERPRETATION_DEVELOPMENT_ONLY.md": "EXP1_FINAL_TEST_INTERPRETATION.md",
        "EXP1_DEVELOPMENT_CLOSURE_MANIFEST.json": "EXP1_FINAL_TEST_CLOSURE_MANIFEST.json",
    }
    _rename_and_patch(output_root, renames)

    summary_path = output_root / "EXP1_FINAL_TEST_CLOSURE_SUMMARY.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["scope"] = "FINAL_TEST_CALIBRATED_REMATERIALIZATION_DEVELOPMENT_COHORT"
    payload["paper_result"] = True
    payload["calibration_artifact_hash"] = _artifact_hash(root)
    payload["safety"] = dict(SAFETY)
    payload["artifact_hash"] = _content_hash(payload)
    write_json(summary_path, payload)

    manifest_path = output_root / "EXP1_FINAL_TEST_CLOSURE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scope"] = "FINAL_TEST_CALIBRATED_REMATERIALIZATION_DEVELOPMENT_COHORT"
    manifest["paper_result"] = True
    manifest["calibration_artifact_hash"] = _artifact_hash(root)
    manifest["outputs"] = {
        name: {"path": value["path"].replace("_DEVELOPMENT_ONLY", "_FINAL_TEST")
               .replace("EXP1_DEVELOPMENT_CLOSURE_SUMMARY", "EXP1_FINAL_TEST_CLOSURE_SUMMARY")
               .replace("EXP1_INTERPRETATION_DEVELOPMENT_ONLY", "EXP1_FINAL_TEST_INTERPRETATION")
               .replace("EXP1_DEVELOPMENT_CLOSURE_MANIFEST", "EXP1_FINAL_TEST_CLOSURE_MANIFEST")}
        for name, value in manifest["outputs"].items()
    }
    manifest["manifest_hash"] = _content_hash(manifest)
    write_json(manifest_path, manifest)
    return {
        "status": "MATERIALIZED",
        "summary": str(summary_path.relative_to(root)).replace("\\", "/"),
        "exp1a_records": str((output_root / "EXP1A_PAPER_FACING_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "exp1b_records": str((output_root / "EXP1B_PREDICTION_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "sorting_diagnostic": str((output_root / "EXP1A_FROZEN_SORTING_DIAGNOSTIC_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
    }


def _artifact_hash(root: Path) -> str:
    payload = json.loads((root / CALIBRATION_ARTIFACT_REL).read_text(encoding="utf-8"))
    return payload["artifact_hash"]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_manifest(path: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-read, extend, and rewrite a stage manifest with FT scope fields."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["paper_result"] = True
    payload["scope"] = FT_SCOPE
    if extra:
        payload.update(extra)
    payload["safety"] = dict(SAFETY)
    payload["manifest_hash"] = _content_hash(payload)
    write_json(path, payload)
    return payload


def stage_exp4(root: Path) -> dict[str, Any]:
    import exp.exp4.per_node_records as pnr

    output_root = (root / FT_EXP4_ROOT).resolve()
    result = pnr.run(
        root=root, input_root=root / DEV_INPUT_ROOT,
        output_root=output_root,
        calibration_artifact_path=root / CALIBRATION_ARTIFACT,
    )
    renames = {
        "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP4_PER_NODE_RECORDS_FINAL_TEST.parquet",
        "EXP4_PER_NODE_RECORDS_DEVELOPMENT_ONLY.csv": "EXP4_PER_NODE_RECORDS_FINAL_TEST.csv",
        "EXP4_LEAD_TIME_GRID_DEVELOPMENT_ONLY.csv": "EXP4_LEAD_TIME_GRID_FINAL_TEST.csv",
        "EXP4_PER_NODE_MANIFEST_DEVELOPMENT_ONLY.json": "EXP4_PER_NODE_MANIFEST_FINAL_TEST.json",
    }
    _rename_and_patch(output_root, renames)
    manifest_path = output_root / "EXP4_PER_NODE_MANIFEST_FINAL_TEST.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _patch_manifest(manifest_path, {
        "calibration_artifact_hash": _artifact_hash(root),
        "calibration_application": (
            "SHARED_T_CAL_ARTIFACT_20260826_IN_MEMORY_STATE_AWARE_H32_ONLY; "
            "HISTORICAL/LIGHTGBM/RANDOM_FOREST reuse frozen fitted dev artifacts unchanged"
        ),
        "parity_note": (
            "STATE_AWARE_H32 MAE/CRPS may drift vs the saved Development metrics: calibrated "
            "temperatures are applied in memory to the frozen checkpoint (checkpoint file "
            "hash unchanged); HISTORICAL/LIGHTGBM/RANDOM_FOREST parity is unchanged. "
            "Parity drift for H32 is expected Final Test semantics, not an error."
        ),
        "outputs": {
            name: value.replace("DEVELOPMENT_ONLY", "FINAL_TEST")
            for name, value in manifest_payload.get("outputs", {}).items()
        },
    })
    return {
        "status": "MATERIALIZED",
        "records": str((output_root / "EXP4_PER_NODE_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "grid": str((output_root / "EXP4_LEAD_TIME_GRID_FINAL_TEST.csv").relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
    }


def stage_m3m4(root: Path) -> dict[str, Any]:
    import exp.exp3.m3_m4_ranking_records as m3m4

    output_root = (root / FT_M3M4_ROOT).resolve()
    result = m3m4.run(
        root=root, output_root=output_root,
        action_risk=root / FT_EXP3_ROOT / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
    )
    renames = {
        "M3M4_COMPARISON_RANKING_RECORDS_DEVELOPMENT_ONLY.parquet": "M3M4_COMPARISON_RANKING_RECORDS_FINAL_TEST.parquet",
        "M3M4_COMPARISON_RANKING_RECORDS_DEVELOPMENT_ONLY.csv": "M3M4_COMPARISON_RANKING_RECORDS_FINAL_TEST.csv",
        "M3M4_TOP1_SUMMARY_DEVELOPMENT_ONLY.csv": "M3M4_TOP1_SUMMARY_FINAL_TEST.csv",
        "M3M4_AGGREGATE_STATS_DEVELOPMENT_ONLY.json": "M3M4_AGGREGATE_STATS_FINAL_TEST.json",
        "M3M4_MANIFEST_DEVELOPMENT_ONLY.json": "M3M4_MANIFEST_FINAL_TEST.json",
    }
    _rename_and_patch(output_root, renames)
    manifest_path = output_root / "M3M4_MANIFEST_FINAL_TEST.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _patch_manifest(manifest_path, {
        "calibration_artifact_hash": _artifact_hash(root),
        "outputs": {
            name: value.replace("DEVELOPMENT_ONLY", "FINAL_TEST")
            for name, value in manifest_payload.get("outputs", {}).items()
        },
    })
    return {
        "status": "MATERIALIZED",
        "records": str((output_root / "M3M4_COMPARISON_RANKING_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "stats": str((output_root / "M3M4_AGGREGATE_STATS_FINAL_TEST.json").relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
    }


def _ft_write_audit(output_root: Path, coverage: pd.DataFrame) -> None:
    unavailable_nodes = int(coverage["unavailable_nodes"].max())
    audit = f"""# Paper output audit (Final Test calibrated rematerialization)

## 1. Planned main-text panels with real saved-result support

- Figure 5A--C is generated from the Final Test Exp1 closure records (Exp1A 3,538 rows; Exp1B 10,614 rows; frozen sorting diagnostic 1,420/1,765 rows). Exp1A contrasts state-driven vs context-conditioned sorting; Exp1B contrasts the H32 HISTORICAL model with a CURRENT-only comparator under the same architecture, training budget, and calibration path, using each model's own checkpoint. All statistics are computed on the common supported observations; 95% confidence intervals are episode-cluster bootstrap (2,000 replicates, seed 20260825).
- Figure 6A is generated for the Point, Marginal, and Joint predictive representations. Point uses the frozen F1 weighted-medoid variogram records materialized by the Final Test Exp2A closure; Marginal and Joint use the saved scenario-level outputs. Scores are aggregated within aircraft-linked episodes and reported with 2,000 episode-cluster bootstrap replicates.
- Figure 7A is generated from the Final Test Exp3 refresh/sync records (freeze F3): One-Shot executable (aged) vs Rolling refreshed rates anchored at the first-valid-suggestion time t_i^0 (eq:exp_anchor), plus state-sync coverage at exact-vintage deltas of 5 and 10 minutes. Vintage binding requires decision_time exactly equal to t - delta (P2 exact_vintage_bindings); unmatched nodes are typed EXP3B_VINTAGE_NOT_AVAILABLE with no nearest-past fallback. {unavailable_nodes} decision nodes lacked stored comparison results and are not treated as zero coverage.
- Figure 7B is generated as valuation-only: LOW/BASE/HIGH bands move the frozen five-anchor monetary coefficients only (0.5x/1.0x/2.0x), while response parameters stay at the F4-frozen declared values. The panel shows the reference action A00; the materialized records cover all 23 action envelopes. Status: ASSUMPTION_GROUNDED, not authoritative.
- Figure 8 is generated for T_IB_A00 and D_OB as target x lead-time MAE and CRPS curves with episode-cluster confidence intervals. D_TX is not plotted: without a planned wheels-off reference its lead-time bins are NA and no interpolation is applied.
- Table 1 contains target-specific point estimates and episode-cluster 95% confidence intervals reconstructed from the Final Test per-node records.

## 2. Scope

- All outputs in this directory are Final Test calibrated rematerialization outputs (paper_result=true) generated under AIR_SLOT_OVERNIGHT_CHAIN_FINAL_20260826. The shared T-cal artifact (artifacts/calibration/m1_v2_calibration_20260826/M1_V2_CALIBRATION_ARTIFACT.json) is applied in memory to the frozen STATE_AWARE H32 and CURRENT-only checkpoints; checkpoint files are not retrained or rewritten.
- The Development cohort (1,769 nodes, DATA2) is used; the Final Test split is never read (FINAL_TEST_ACCESS_COUNT=0).
- The Exp3 valuation-only records are ASSUMPTION_GROUNDED: the monetary coefficients are assumption-grounded frozen values, not authoritative or causal. P_itinerary/P_service are ABSTAIN (F7); RMB is not instantiated (F8).

## 3. Panels not generated or intentionally removed

- Figure 6B--C: intentionally removed per F2 (PARTIAL_Q_SERIES_NOT_IMPLEMENTED; q-series frozen). No Figure 6B--C code path, caption, or audit entry is kept.
- Figure 8 panel for D_TX: not drawn because D_TX has no planned wheels-off reference; lead-time bins are NA and are never interpolated.
- STATE_AWARE_H32 D_OB/D_TX CRPS cells are blank: M1 does not save those distributional scores; nothing is inferred.
"""
    (output_root / "paper_output_audit.md").write_text(audit, encoding="utf-8")


def _ft_write_scope_marker(output_root: Path) -> None:
    payload = {
        "scope": FT_SCOPE,
        "paper_result": True,
        "final_test_access_count": 0,
        "generated_by": "exp.reporting.final_test_run (AIR_SLOT_OVERNIGHT_CHAIN_FINAL_20260826)",
    }
    (output_root / "OUTPUT_SCOPE_FINAL_TEST.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8",
    )


def stage_figures(root: Path) -> dict[str, Any]:
    import exp.reporting.figure5_exp1_development as f5
    import exp.reporting.section5_secondary_analysis as s5

    output_root = (root / PAPER_OUTPUT_ROOT).resolve()
    with _override(f5, {
        "EXP1_CLOSURE_ROOT": FT_EXP1_ROOT,
        "EXP1_SUMMARY": FT_EXP1_ROOT / "EXP1_FINAL_TEST_CLOSURE_SUMMARY.json",
        "DEFAULT_OUTPUT_ROOT": PAPER_OUTPUT_ROOT,
    }):
        f5.run(root=root)
    _rename_and_patch(output_root, {
        "EXP1_FIGURES_MANIFEST_DEVELOPMENT_ONLY.json": "EXP1_FIGURES_MANIFEST_FINAL_TEST.json",
    })
    _patch_manifest(output_root / "EXP1_FIGURES_MANIFEST_FINAL_TEST.json", {
        "calibration_artifact_hash": _artifact_hash(root),
    })

    s5_overrides = {
        "EXP2_SCENARIOS": FT_SCENARIO_ROOT / FT_SCENARIO_HISTORY,
        "EXP2_LABELS": DEV_INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_LABELS.json",
        "EXP3_ACTION_RISK": FT_EXP3_ROOT / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
        "EXP2A_POINT_RECORDS": FT_EXP2A_ROOT / "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.parquet",
        "EXP2A_VARIOGRAM_SUMMARIES": FT_EXP2A_ROOT / "EXP2A_VARIOGRAM_SUMMARIES_FINAL_TEST.csv",
        "EXP3_VALUATION_RECORDS": FT_VALUATION_ROOT / "EXP3_VALUATION_ONLY_RECORDS_FINAL_TEST.parquet",
        "EXP4_GRID": FT_EXP4_ROOT / "EXP4_LEAD_TIME_GRID_FINAL_TEST.csv",
        "EXP3_FIGURE7A_EPISODE_VALUES": FT_REFRESH_SYNC_ROOT / "EXP3_FIGURE7A_EPISODE_VALUES_FINAL_TEST.csv",
        "EXP3_FIGURE7A_SUMMARY": FT_REFRESH_SYNC_ROOT / "EXP3_FIGURE7A_SUMMARY_FINAL_TEST.csv",
        "_write_audit": _ft_write_audit,
        "_write_scope_marker": _ft_write_scope_marker,
    }
    with _override(s5, s5_overrides):
        paths = s5.run(root=root, output_root=output_root)
    return {
        "status": "MATERIALIZED",
        "figure_5": str((output_root / "figures" / "figure_5_exp1_direct_information.pdf").relative_to(root)).replace("\\", "/"),
        "figure_6": str(paths["figure_6"].relative_to(root)).replace("\\", "/"),
        "figure_7": str(paths["figure_7"].relative_to(root)).replace("\\", "/"),
        "figure_7b": str(paths["figure_7b"].relative_to(root)).replace("\\", "/"),
        "figure_8": str(paths["figure_8"].relative_to(root)).replace("\\", "/"),
        "table_1": str(paths["table_1"].relative_to(root)).replace("\\", "/"),
        "audit": str((output_root / "paper_output_audit.md").relative_to(root)).replace("\\", "/"),
    }


def run_chain(root: Path = ROOT, stages: tuple[str, ...] | None = None) -> dict[str, Any]:
    root = root.resolve()
    chain_path = root / CHAIN_MANIFEST
    results: dict[str, Any] = {}
    if chain_path.is_file():
        results.update(_load_json(chain_path).get("stages", {}))
    order = (
        "scenarios", "exp2", "exp1", "exp2a", "exp3",
        "valuation", "refresh_sync", "exp2b", "exp4", "m3m4", "figures",
    )
    available = {
        "scenarios": stage_scenarios,
        "exp2": stage_exp2,
        "exp1": stage_exp1,
        "exp2a": stage_exp2a,
        "exp3": stage_exp3,
        "valuation": stage_valuation,
        "refresh_sync": stage_refresh_sync,
        "exp2b": stage_exp2b,
        "exp4": stage_exp4,
        "m3m4": stage_m3m4,
        "figures": stage_figures,
    }
    for name in order:
        if stages is not None and name not in stages:
            continue
        if name in results:
            print(f"[FINAL_TEST] stage {name} already recorded; skipping", flush=True)
            continue
        print(f"[FINAL_TEST] stage {name} starting", flush=True)
        results[name] = available[name](root)
        print(f"[FINAL_TEST] stage {name} done", flush=True)
    chain = {
        "schema_version": SCHEMA_VERSION,
        "status": "MATERIALIZED",
        "decision_id": "AIR_SLOT_OVERNIGHT_CHAIN_FINAL_20260826",
        "calibration_artifact_hash": _artifact_hash(root),
        "stages": results,
        "final_test_access_note": FINAL_TEST_ACCESS_NOTE,
        "safety": dict(SAFETY),
    }
    chain["manifest_hash"] = _content_hash(chain)
    write_json(chain_path, chain)
    print(json.dumps(chain, indent=2, sort_keys=True, default=str))
    return chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--stages", type=str, default=None,
        help="comma-separated subset of stage names (default: all)",
    )
    args = parser.parse_args(argv)
    root = (args.root or ROOT).resolve()
    stages = tuple(item.strip() for item in args.stages.split(",")) if args.stages else None
    run_chain(root=root, stages=stages)
    return 0


def stage_exp2a(root: Path) -> dict[str, Any]:
    import exp.exp2.closure as closure

    output_root = (root / FT_EXP2A_ROOT).resolve()
    overrides = {
        "SCENARIOS": FT_SCENARIO_ROOT / FT_SCENARIO_HISTORY,
        "SCENARIO_MANIFEST": SCENARIO_MANIFEST,
        "LABELS": DEV_INPUT_ROOT / "M1_V2_FULL_DEVELOPMENT_LABELS.json",
    }
    with _override(closure, overrides):
        records = closure.materialize_point_records(root=root, output_root=output_root)
        episode_values = closure.exp2_variogram_episode_values(root)
        summary, contrast = closure.exp2_variogram_summaries(
            episode_values, replicates=closure.BOOTSTRAP_REPLICATES,
        )
    summary.to_csv(
        output_root / "EXP2A_VARIOGRAM_SUMMARIES_DEVELOPMENT_ONLY.csv", index=False,
    )
    contrast.to_csv(
        output_root / "EXP2A_VARIOGRAM_CONTRASTS_DEVELOPMENT_ONLY.csv", index=False,
    )
    supported = records.loc[records["support_status"] == "SUPPORTED"]
    manifest = {
        "schema_version": closure.SCHEMA_VERSION,
        "scope": FT_SCOPE,
        "paper_result": True,
        "freeze_refs": {
            "F1": "PRIMITIVE_MEDOID_COORDINATES_R_IB_D_OB_D_TX_D_TO_IDENTITY_ONLY",
            "F2": "PARTIAL_Q_SERIES_NOT_IMPLEMENTED",
        },
        "source_artifact": str(FT_SCENARIO_ROOT / FT_SCENARIO_HISTORY).replace("\\", "/"),
        "source_artifact_hash": file_sha256(root / FT_SCENARIO_ROOT / FT_SCENARIO_HISTORY),
        "scenario_manifest_hash": _load_json(root / SCENARIO_MANIFEST)["manifest_hash"],
        "node_count": len(records),
        "point_supported_nodes": int(len(supported)),
        "point_abstain_nodes": int(len(records) - len(supported)),
        "episode_bootstrap_replicates": closure.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": closure.GLOBAL_SEED,
        "summary_rows": summary.to_dict(orient="records"),
        "contrast_rows": contrast.to_dict(orient="records"),
        "calibration_artifact_hash": _artifact_hash(root),
        "outputs": [
            "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.csv",
            "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.parquet",
            "EXP2A_VARIOGRAM_SUMMARIES_FINAL_TEST.csv",
            "EXP2A_VARIOGRAM_CONTRASTS_FINAL_TEST.csv",
        ],
        "safety": dict(SAFETY),
    }
    manifest["manifest_hash"] = _content_hash(manifest)
    write_json(output_root / "EXP2A_POINT_VARIOGRAM_MANIFEST.json", manifest)
    _rename_and_patch(output_root, {
        "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.csv": "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.csv",
        "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.parquet",
        "EXP2A_VARIOGRAM_SUMMARIES_DEVELOPMENT_ONLY.csv": "EXP2A_VARIOGRAM_SUMMARIES_FINAL_TEST.csv",
        "EXP2A_VARIOGRAM_CONTRASTS_DEVELOPMENT_ONLY.csv": "EXP2A_VARIOGRAM_CONTRASTS_FINAL_TEST.csv",
    })
    return {
        "status": "MATERIALIZED",
        "manifest": str((output_root / "EXP2A_POINT_VARIOGRAM_MANIFEST.json").relative_to(root)).replace("\\", "/"),
        "records": str((output_root / "EXP2A_POINT_VARIOGRAM_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "point_supported_nodes": int(len(supported)),
    }


def stage_exp3(root: Path) -> dict[str, Any]:
    import exp.exp3.global_development as gd

    output_root = (root / FT_EXP3_ROOT).resolve()
    overrides = {
        "MAPPING_REGISTRY": REGISTRY_V2_PATH,
        "EXPECTED_REGISTRY_HASH": REGISTRY_V2_HASH,
        "PENDING_ANCHOR_STATUS": PENDING_ABSTAIN_STATUS,
        "PENDING_ANCHOR_FIELD_REASON": "P_ITINERARY_P_SERVICE_MONETARY_ANCHORS_ABSTAIN_MONETARY_NOT_ANCHORED",
        "PENDING_EXCLUDED_REASON": "MONETARY_ANCHOR_ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY",
        "PENDING_SUPPORT_REASON": "COMPLETE_SEVEN_COMPONENT_MONETARY_ANCHORS_ABSTAIN_MONETARY_NOT_ANCHORED",
        "PENDING_INTERPRETATION_NOTE": (
            "per-event monetary anchors remain ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY "
            "and they never enter the ranking. "
        ),
    }
    with _override(gd, overrides):
        result = gd.run(
            root=root, exp2_root=root / FT_EXP2_ROOT,
            input_root=root / DEV_INPUT_ROOT, output_root=output_root,
        )
    manifest_path = result["manifest"]
    _patch_manifest(manifest_path, {
        "registry": str(REGISTRY_V2_PATH),
        "registry_decision_refs": [
            "F7_P_ITIN_P_SERV_ABSTAIN_MONETARY_NOT_ANCHORED",
            "F8_RMB_SYSTEM_LEVEL_ABSTAIN_NO_BETA_K_RMB",
        ],
        "calibration_artifact_hash": _artifact_hash(root),
    })
    return {
        "status": "MATERIALIZED",
        "action_risk": str(result["action_risk"].relative_to(root)).replace("\\", "/"),
        "metrics": str(result["metrics"].relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
    }


def stage_valuation(root: Path) -> dict[str, Any]:
    import exp.exp3.valuation_only as vo

    output_root = (root / FT_VALUATION_ROOT).resolve()
    if not (output_root / "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet").is_file():
        restored = output_root / "EXP3_VALUATION_ONLY_RECORDS_FINAL_TEST.parquet"
        if restored.is_file():
            (output_root / "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet").write_bytes(
                restored.read_bytes(),
            )
    overrides = {
        "MAPPING_REGISTRY": REGISTRY_V2_PATH,
        "EXPECTED_REGISTRY_HASH": REGISTRY_V2_HASH,
        "EXISTING_ACTION_RISK": Path(
            "artifacts/paper_results_v1/exp3/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
        ),
    }
    with _override(vo, overrides):
        result = vo.run(
            root=root, exp2_root=root / FT_EXP2_ROOT,
            input_root=root / DEV_INPUT_ROOT, output_root=output_root,
        )
    renames = {
        "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP3_VALUATION_ONLY_RECORDS_FINAL_TEST.parquet",
        "EXP3_VALUATION_ONLY_SUMMARY_DEVELOPMENT_ONLY.csv": "EXP3_VALUATION_ONLY_SUMMARY_FINAL_TEST.csv",
        "EXP3_VALUATION_ONLY_MANIFEST_DEVELOPMENT_ONLY.json": "EXP3_VALUATION_ONLY_MANIFEST_FINAL_TEST.json",
    }
    _rename_and_patch(output_root, renames)
    manifest_path = output_root / "EXP3_VALUATION_ONLY_MANIFEST_FINAL_TEST.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _patch_manifest(manifest_path, {
        "registry": str(REGISTRY_V2_PATH),
        "calibration_artifact_hash": _artifact_hash(root),
        "outputs": {
            name: value.replace("DEVELOPMENT_ONLY", "FINAL_TEST")
            for name, value in manifest_payload.get("outputs", {}).items()
        },
    })
    return {
        "status": "MATERIALIZED",
        "records": str((output_root / "EXP3_VALUATION_ONLY_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "row_count": payload.get("output_row_count"),
    }


def stage_refresh_sync(root: Path) -> dict[str, Any]:
    import exp.exp3.refresh_sync_records as rs

    output_root = (root / FT_REFRESH_SYNC_ROOT).resolve()
    result = rs.run(
        root=root, output_root=output_root,
        action_risk=root / FT_EXP3_ROOT / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
    )
    renames = {
        "EXP3_REFRESH_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP3_REFRESH_RECORDS_FINAL_TEST.parquet",
        "EXP3_REFRESH_RECORDS_DEVELOPMENT_ONLY.csv": "EXP3_REFRESH_RECORDS_FINAL_TEST.csv",
        "EXP3_STATE_SYNC_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP3_STATE_SYNC_RECORDS_FINAL_TEST.parquet",
        "EXP3_STATE_SYNC_RECORDS_DEVELOPMENT_ONLY.csv": "EXP3_STATE_SYNC_RECORDS_FINAL_TEST.csv",
        "EXP3_REFRESH_EPISODE_VALUES_DEVELOPMENT_ONLY.csv": "EXP3_REFRESH_EPISODE_VALUES_FINAL_TEST.csv",
        "EXP3_STATE_SYNC_EPISODE_VALUES_DEVELOPMENT_ONLY.csv": "EXP3_STATE_SYNC_EPISODE_VALUES_FINAL_TEST.csv",
        "EXP3_FIGURE7A_EPISODE_VALUES_DEVELOPMENT_ONLY.csv": "EXP3_FIGURE7A_EPISODE_VALUES_FINAL_TEST.csv",
        "EXP3_FIGURE7A_SUMMARY_DEVELOPMENT_ONLY.csv": "EXP3_FIGURE7A_SUMMARY_FINAL_TEST.csv",
        "EXP3_REFRESH_SYNC_SUMMARY_DEVELOPMENT_ONLY.csv": "EXP3_REFRESH_SYNC_SUMMARY_FINAL_TEST.csv",
        "EXP3_REFRESH_SYNC_MANIFEST_DEVELOPMENT_ONLY.json": "EXP3_REFRESH_SYNC_MANIFEST_FINAL_TEST.json",
    }
    _rename_and_patch(output_root, renames)
    manifest_path = output_root / "EXP3_REFRESH_SYNC_MANIFEST_FINAL_TEST.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _patch_manifest(manifest_path, {
        "calibration_artifact_hash": _artifact_hash(root),
        "outputs": {
            name: value.replace("DEVELOPMENT_ONLY", "FINAL_TEST")
            for name, value in manifest_payload.get("outputs", {}).items()
        },
    })
    return {
        "status": "MATERIALIZED",
        "figure_episode": str((output_root / "EXP3_FIGURE7A_EPISODE_VALUES_FINAL_TEST.csv").relative_to(root)).replace("\\", "/"),
        "figure_summary": str((output_root / "EXP3_FIGURE7A_SUMMARY_FINAL_TEST.csv").relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "node_count": payload.get("node_count"),
    }


def stage_exp2b(root: Path) -> dict[str, Any]:
    import exp.exp2.exp2b_consequence_representation as exp2b

    output_root = (root / FT_EXP2B_ROOT).resolve()
    overrides = {
        "EXISTING_ACTION_RISK": Path(
            "artifacts/paper_results_v1/exp3/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
        ),
        "MAPPING_REGISTRY": REGISTRY_V2_PATH,
        "EXPECTED_REGISTRY_HASH": REGISTRY_V2_HASH,
    }
    with _override(exp2b, overrides):
        result = exp2b.materialize(
            root=root, exp2_root=root / FT_EXP2_ROOT,
            input_root=root / DEV_INPUT_ROOT, output_root=output_root,
        )
    renames = {
        "EXP2B_RECORDS_DEVELOPMENT_ONLY.parquet": "EXP2B_RECORDS_FINAL_TEST.parquet",
        "EXP2B_RECORDS_DEVELOPMENT_ONLY.csv": "EXP2B_RECORDS_FINAL_TEST.csv",
        "EXP2B_SUMMARY_DEVELOPMENT_ONLY.csv": "EXP2B_SUMMARY_FINAL_TEST.csv",
        "EXP2B_NODE_SUMMARY_DEVELOPMENT_ONLY.csv": "EXP2B_NODE_SUMMARY_FINAL_TEST.csv",
        "EXP2B_FAMILY_TRANSITIONS_DEVELOPMENT_ONLY.csv": "EXP2B_FAMILY_TRANSITIONS_FINAL_TEST.csv",
        "EXP2B_MATCHED_CASE_DEVELOPMENT_ONLY.csv": "EXP2B_MATCHED_CASE_FINAL_TEST.csv",
        "EXP2B_MANIFEST_DEVELOPMENT_ONLY.json": "EXP2B_MANIFEST_FINAL_TEST.json",
    }
    _rename_and_patch(output_root, renames)
    manifest_path = output_root / "EXP2B_MANIFEST_FINAL_TEST.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _patch_manifest(manifest_path, {
        "registry": str(REGISTRY_V2_PATH),
        "calibration_artifact_hash": _artifact_hash(root),
        "outputs": {
            name: value.replace("DEVELOPMENT_ONLY", "FINAL_TEST")
            for name, value in manifest_payload.get("outputs", {}).items()
        },
    })
    return {
        "status": "MATERIALIZED",
        "records": str((output_root / "EXP2B_RECORDS_FINAL_TEST.parquet").relative_to(root)).replace("\\", "/"),
        "matched_case": str((output_root / "EXP2B_MATCHED_CASE_FINAL_TEST.csv").relative_to(root)).replace("\\", "/"),
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
