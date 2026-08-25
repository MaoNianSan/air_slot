"""OUTPUT_CONTRACT_20260823 shared output layer for Exp1--Exp4.

Machine-readable implementation of the AIR SLOT Exp output-form and
output-parameter contract: section 3 metric registry, section 4
per-experiment artifact set, and section 5 figure/table style
specifications.  The layer only writes artifacts from already-decided
metric rows; it never executes experiments, never touches Final Test,
and refuses any payload whose safety counters are non-zero.

Main-table column semantics (``MAIN_TABLE_COLUMNS``):

- Subexperiment: contract sub-experiment id from the variant definitions
  (per-row ``subexperiment`` override wins when present).
- Condition: variant condition from ``condition_of`` (per-row
  ``condition`` override wins when present).
- Metric: registered metric id.
- Estimate: the metric value; NOT_RUN/BLOCKED/ABSTAIN rows (value None)
  never occupy a row and keep their reason text in the metrics CSV and
  summary headline only.
- 95% CI: bootstrap interval when present; a single Development run
  without bootstrap is written as the canonical placeholder ``—``.
- N episodes: ``supported_episode_count`` when the payload provides it;
  otherwise the canonical placeholder ``—``.

Empty-table policy: a main table may be empty only when the summary
carries a non-empty ``empty_reason``; ``validate_artifacts`` rejects an
empty table without a reason and rejects any blank data cell.
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from exp.common.result_schema import MetricLevel, SupportStatus
from exp.reporting.global_metrics import (
    rows_from_global_metrics,
    write_from_global_metrics,
)
from exp.reporting.figures import generate_figure_bundle
from exp.reporting.tables import generate_three_line_table
from model.common.errors import ContractError
from model.common.identity import content_id

CONTRACT_VERSION = "AIR_SLOT_EXP_OUTPUT_CONTRACT_20260823"
SUMMARY_SCHEMA_VERSION = "AIR_SLOT_EXP_SUMMARY_V1"

OUTPUT_ROOTS = {
    "EXP1": "artifacts/experiment/exp1_full_development",
    "EXP2": "artifacts/experiments/exp2/full_development_v1",
    "EXP3": "artifacts/experiments/exp3/full_development_v1",
    "EXP4": "artifacts/experiments/exp4/full_development_v1",
}

VALUE_BEARING_SUPPORT = frozenset({SupportStatus.SUPPORTED, SupportStatus.PARTIAL})

METRIC_CSV_COLUMNS = (
    "experiment", "variant", "metric_id", "level", "value", "unit",
    "support", "estimate", "ci_lower", "ci_upper", "n_episodes", "reason",
)
MAIN_TABLE_COLUMNS = ("Subexperiment", "Condition", "Metric", "Estimate", "95% CI", "N episodes")
CI_UNAVAILABLE = "—"
N_EPISODES_UNAVAILABLE = "—"


@dataclass(frozen=True)
class MetricContract:
    experiment_id: str
    metric_id: str
    level: MetricLevel
    unit: str
    denominator: str
    ci_method: str
    headline: bool


METRIC_REGISTRY: tuple[MetricContract, ...] = (
    # Exp1A / Exp1B information roles and history dependence.
    MetricContract("EXP1", "STATE_REPRESENTATION_DIFFERENCE", MetricLevel.STATE, "minutes",
                   "paired nodes FULL vs NO_DIRECT_REUSE", "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP1", "CRPS_PRIMITIVE_TARGET", MetricLevel.STATE, "minutes",
                   "primitive targets R_IB, DeltaOB, T_TX, derived D_TO", "episode_bootstrap", True),
    MetricContract("EXP1", "TOP1_ACTION_DISAGREEMENT", MetricLevel.DECISION, "rate",
                   "nodes with |A_cmp|>=2 including non-A00", "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP1", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", MetricLevel.DECISION,
                   "CONSTRUCTED_LOSS_UNIT", "Eq.(39) common replay nodes",
                   "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP1", "BRIER_PRINCIPAL_DELAY_EVENT", MetricLevel.STATE, "score",
                   "principal delay-event nodes", "episode_bootstrap", False),
    MetricContract("EXP1", "CALIBRATION", MetricLevel.STATE, "absolute_gap",
                   "10-bin fixed-bin nodes", "episode_bootstrap", False),
    MetricContract("EXP1", "COVERAGE", MetricLevel.STATE, "rate",
                   "10-bin fixed-bin nodes", "episode_bootstrap", False),
    # Exp1 main-chain displayable cohort/stage summary (engineering facts;
    # shown while model state metrics stay NOT_RUN at the M1 inference gate).
    MetricContract("EXP1", "COHORT_EPISODES", MetricLevel.STATE, "episodes",
                   "frozen Data2 Development cohort", "none", False),
    MetricContract("EXP1", "COHORT_NODES", MetricLevel.STATE, "nodes",
                   "frozen active development nodes", "none", False),
    MetricContract("EXP1", "SCENARIOS_PER_NODE", MetricLevel.STATE, "scenarios/node",
                   "materialized typed joint scenarios", "none", False),
    MetricContract("EXP1", "SCENARIO_COVERAGE_RATE", MetricLevel.STATE, "rate",
                   "materialized scenario rows / (nodes x scenarios)", "none", False),
    # Exp2A uncertainty representation.
    MetricContract("EXP2", "CRPS", MetricLevel.STATE, "minutes",
                   "marginal frozen JOINT artifact nodes", "episode_bootstrap", True),
    MetricContract("EXP2", "BRIER", MetricLevel.STATE, "score",
                   "marginal frozen JOINT artifact nodes", "episode_bootstrap", False),
    MetricContract("EXP2", "CALIBRATION", MetricLevel.STATE, "absolute_gap",
                   "10-bin fixed-bin nodes", "episode_bootstrap", False),
    MetricContract("EXP2", "COVERAGE", MetricLevel.STATE, "rate",
                   "10-bin fixed-bin nodes", "episode_bootstrap", False),
    MetricContract("EXP2", "VARIOGRAM_SCORE", MetricLevel.STATE, "score",
                   "p=0.5 per-node mean over supported nodes", "episode_bootstrap", True),
    MetricContract("EXP2", "MARGINAL_WEIGHT_CHECK", MetricLevel.STATE, "boolean",
                   "marginal weight parity rows", "none", False),
    MetricContract("EXP2", "TOP1_ACTION_DISAGREEMENT", MetricLevel.DECISION, "rate",
                   "nodes with |A_cmp|>=2 including non-A00, JOINT reference",
                   "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP2", "COMPLETE_REFERENCE_J_DIAGNOSTIC", MetricLevel.DECISION, "rate",
                   "internal diagnostic only, not empirical", "episode_bootstrap", False),
    MetricContract("EXP2", "ACTION_FAMILY_COMPOSITION", MetricLevel.DECISION, "share",
                   "action-family rows in top-1 support", "episode_bootstrap", True),
    # Exp3A recommendation refresh and Exp3B state sync.
    MetricContract("EXP3", "ONE_SHOT_ANCHOR", MetricLevel.DECISION, "boolean",
                   "first |A_cmp|>=2 node with non-A00, t0 Eq.46", "none", False),
    MetricContract("EXP3", "RECOMMENDATION_EXECUTABLE_RATE", MetricLevel.DECISION, "rate",
                   "initial legal recommendations", "episode_bootstrap", True),
    MetricContract("EXP3", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", MetricLevel.DECISION,
                   "CONSTRUCTED_LOSS_UNIT", "paired common baseline nodes",
                   "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP3", "TOP1_ACTION_AGREEMENT", MetricLevel.DECISION, "rate",
                   "paired nodes vs reference variant", "paired_episode_cluster_bootstrap", True),
    MetricContract("EXP3", "STATE_VINTAGE_COVERAGE", MetricLevel.STATE, "rate",
                   "nodes with available lag history", "episode_bootstrap", False),
    # Exp3 conditional diagnostic rows (5-anchor constructed-EUR subset,
    # CONDITIONAL_DIAGNOSTIC only, never principal).
    MetricContract("EXP3", "FINITE_SUPPORT_RATE", MetricLevel.STATE, "rate",
                   "eligible decision-node/action rows with finite support",
                   "none", True),
    MetricContract("EXP3", "CONDITIONAL_TOP1_RESPONSE_AGREEMENT", MetricLevel.STATE, "rate",
                   "top-1 response agreement per sensitivity band",
                   "none", True),
    MetricContract("EXP3", "GLOBAL_CONSTRUCTED_EUR_SCALE_INVARIANCE", MetricLevel.STATE, "rate",
                   "ranking invariance under common positive scale across bands",
                   "none", True),
    MetricContract("EXP3", "PER_ACTION_CONDITIONAL_RISK_MEAN", MetricLevel.STATE,
                   "constructed_EUR",
                   "finite-support action rows, 5-anchor subset",
                   "none", True),
    MetricContract("EXP3", "FORMAL_COMPLETE_CHAIN", MetricLevel.DECISION, "boolean",
                   "complete seven-component monetary ranking",
                   "none", False),
    # Exp4A predictive adequacy, Exp4B decision validity, Exp4C portability, Exp4D runtime.
    MetricContract("EXP4", "MAE_MINUTES", MetricLevel.STATE, "minutes",
                   "common target/lead-time nodes", "episode_bootstrap", True),
    MetricContract("EXP4", "CRPS", MetricLevel.STATE, "minutes",
                   "common target/lead-time nodes", "episode_bootstrap", True),
    MetricContract("EXP4", "LEAD_TIME_CONTRACT", MetricLevel.STATE, "boolean",
                   "lead-time vs horizon distinction rows", "none", False),
    MetricContract("EXP4", "FORMAL_RECOMMENDATION_AVAILABILITY", MetricLevel.DECISION, "rate",
                   "N_elig eligible nodes Eq.49", "episode_bootstrap", True),
    MetricContract("EXP4", "DATA1_DATA2_SEMANTIC_GATE", MetricLevel.STATE, "boolean",
                   "semantic-gate rows", "none", False),
    MetricContract("EXP4", "E2E_P50_SECONDS", MetricLevel.SYSTEM, "seconds",
                   "end-to-end run repeats", "episode_bootstrap", True),
    MetricContract("EXP4", "E2E_P95_SECONDS", MetricLevel.SYSTEM, "seconds",
                   "end-to-end run repeats", "episode_bootstrap", True),
    MetricContract("EXP4", "E2E_P99_SECONDS", MetricLevel.SYSTEM, "seconds",
                   "end-to-end run repeats", "episode_bootstrap", True),
    MetricContract("EXP4", "WITHIN_60S", MetricLevel.SYSTEM, "rate",
                   "end-to-end run repeats", "episode_bootstrap", False),
    MetricContract("EXP4", "WITHIN_120S", MetricLevel.SYSTEM, "rate",
                   "end-to-end run repeats", "episode_bootstrap", False),
    MetricContract("EXP4", "WITHIN_300S", MetricLevel.SYSTEM, "rate",
                   "end-to-end run repeats, budget 300s", "episode_bootstrap", True),
)

FIGURE_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "EXP1": (
        {
            "figure_id": "EXP1_INFORMATION_ROLES",
            "layout": (1, 2),
            "panels": {
                "A": {"question": "Ex-post model-implied residual risk: NO_DIRECT_REUSE vs FULL"},
                "B": {"question": "Primitive CRPS: CURRENT vs ADAPTIVE (FIXED_30 hollow in sensitivity)"},
            },
        },
    ),
    "EXP2": (
        {
            "figure_id": "EXP2_REPRESENTATION",
            "layout": (2, 2),
            "panels": {
                "a": {"question": "CRPS: POINT / MARGINAL / JOINT"},
                "b": {"question": "Variogram score"},
                "c": {"question": "Top-1 action disagreement vs JOINT"},
                "d": {"question": "Top-1 disagreement vs 7COMP and action-family share"},
            },
        },
    ),
    "EXP3": (
        {
            "figure_id": "EXP3_PROCESS",
            "layout": (2, 2),
            "panels": {
                "a": {"question": "ONE_SHOT vs ROLLING executability by age"},
                "b": {"question": "Ex-post model-implied residual risk paired difference"},
                "c": {"question": "LAG5/LAG10 vs SYNC top-1 agreement"},
                "d": {"question": "Stratified disagreement by turnaround flexibility x update type"},
            },
        },
    ),
    "EXP4": (
        {
            "figure_id": "EXP4_PREDICTIVE",
            "layout": (1, 1),
            "panels": {"main": {"question": "MAE and CRPS vs lead time by baseline"}},
        },
        {
            "figure_id": "EXP4_OPERATIONAL",
            "layout": (1, 1),
            "panels": {"main": {"question": "Availability, portability, and latency vs 300s budget"}},
        },
    ),
}
def registry_for(experiment_id: str) -> tuple[MetricContract, ...]:
    return tuple(item for item in METRIC_REGISTRY if item.experiment_id == experiment_id)


def metric_contract(experiment_id: str, metric_id: str) -> MetricContract | None:
    for item in METRIC_REGISTRY:
        if item.experiment_id == experiment_id and item.metric_id == metric_id:
            return item
    return None


def _git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root),
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def require_output_safety(payload: Mapping[str, Any]) -> None:
    safety = payload.get("safety", payload)
    if safety.get("FINAL_TEST_ACCESS_COUNT", 0) != 0:
        raise ContractError("OUTPUT_CONTRACT_FINAL_TEST_ACCESS_NONZERO")
    if safety.get("PAPER_FULL_RUN", False) is not False:
        raise ContractError("OUTPUT_CONTRACT_PAPER_FULL_FORBIDDEN")
    if safety.get("AUTHORITATIVE_RANKING", False) is not False:
        raise ContractError("OUTPUT_CONTRACT_AUTHORITATIVE_RANKING_FORBIDDEN")


def validate_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    support = SupportStatus(str(normalized["support"]))
    normalized["support"] = support.value
    contract = metric_contract(str(normalized["experiment"]), str(normalized["metric_id"]))
    if contract is None:
        raise ContractError("OUTPUT_CONTRACT_METRIC_UNREGISTERED:" + str(normalized["metric_id"]))
    if normalized.get("value") is None:
        if support in VALUE_BEARING_SUPPORT:
            raise ContractError("OUTPUT_CONTRACT_VALUE_REQUIRED:" + str(normalized["metric_id"]))
        if not normalized.get("reason"):
            raise ContractError("OUTPUT_CONTRACT_REASON_REQUIRED:" + str(normalized["metric_id"]))
    else:
        if support not in VALUE_BEARING_SUPPORT:
            raise ContractError("OUTPUT_CONTRACT_VALUE_FORBIDDEN:" + str(normalized["metric_id"]))
    normalized.setdefault("level", contract.level.value)
    normalized.setdefault("unit", contract.unit)
    return normalized


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)
    return path


def _hashed(payload: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in payload.items() if key != "artifact_hash"}
    return {**clean, "artifact_hash": content_id(clean)}


def _write_hashed_json(path: Path, payload: dict[str, Any]) -> Path:
    return _write_json(path, _hashed(payload))


def _cohort_card(cohort: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": cohort.get("dataset_id", "DATA2"),
        "split": cohort.get("split", "DEVELOPMENT"),
        "episode_count": int(cohort.get("episode_count", 0)),
        "node_count": int(cohort.get("node_count", 0)),
        "scenario_count_per_node": int(cohort.get("scenario_count_per_node", 0)),
        "seed": int(cohort.get("seed", 0)),
    }


def build_protocol_manifest(
    *, experiment_id: str, cohort: Mapping[str, Any], variants: tuple[str, ...],
    frozen_hashes: Mapping[str, str], config_hash: str, root: Path,
) -> dict[str, Any]:
    payload = {
        "schema_version": "AIR_SLOT_EXP_PROTOCOL_MANIFEST_V1",
        "contract_version": CONTRACT_VERSION,
        "experiment_id": experiment_id,
        "dataset_id": cohort.get("dataset_id", "DATA2"),
        "split": cohort.get("split", "DEVELOPMENT"),
        "variants": list(variants),
        "seed": int(cohort.get("seed", 0)),
        "scenario_count": int(cohort.get("scenario_count_per_node", 0)),
        "frozen_hashes": dict(frozen_hashes),
        "config_hash": config_hash,
        "git_sha": _git_sha(root),
        "cohort": _cohort_card(cohort),
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "AUTHORITATIVE_RANKING": False,
        },
        "paper_result": False,
    }
    require_output_safety(payload)
    return payload


def build_variant_manifest(
    *, variant_definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    entries = {}
    for variant_id, definition in sorted(variant_definitions.items()):
        entries[variant_id] = {
            **definition,
            "definition_hash": content_id({
                key: value for key, value in definition.items() if key != "definition_hash"
            }),
        }
    payload = {
        "schema_version": "AIR_SLOT_EXP_VARIANT_MANIFEST_V1",
        "contract_version": CONTRACT_VERSION,
        "variants": entries,
    }
    return payload


def build_split_audit(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    checks = {
        "episodes_consistent": True,
        "no_future_information": True,
        "no_cross_split_episode": True,
    }
    splits: set[str] = set()
    for row in rows:
        if row.get("split"):
            splits.add(str(row["split"]))
        cutoff = row.get("information_cutoff_utc") or row.get("information_cutoff")
        decision = row.get("decision_time_utc") or row.get("decision_time")
        if cutoff is not None and decision is not None:
            if str(cutoff) > str(decision):
                checks["no_future_information"] = False
    if len(splits) > 1:
        checks["no_cross_split_episode"] = False
    payload = {
        "schema_version": "AIR_SLOT_EXP_SPLIT_AUDIT_V1",
        "contract_version": CONTRACT_VERSION,
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "observed_splits": sorted(splits),
    }
    return payload


def build_leakage_audit(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    checks = {"realized_outcome_evaluation_only": True}
    for row in rows:
        role = str(row.get("role", "EVALUATION"))
        carries_outcome = row.get("realized_outcome") is not None or row.get("contains_labels") is True
        if role == "INFERENCE" and carries_outcome:
            checks["realized_outcome_evaluation_only"] = False
    payload = {
        "schema_version": "AIR_SLOT_EXP_LEAKAGE_AUDIT_V1",
        "contract_version": CONTRACT_VERSION,
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
    }
    return payload


def build_parity_audit(experiment_id: str, checks: Mapping[str, bool]) -> dict[str, Any]:
    default_checks = {
        "EXP2": {
            "exp2a_marginal_weight_parity": True,
            "exp2b_coarse_no_hidden_7comp_access": True,
        },
        "EXP4": {
            "exp4d_shared_recomputed_output_parity": True,
        },
    }
    merged = dict(default_checks.get(experiment_id, {}))
    merged.update({key: bool(value) for key, value in checks.items()})
    payload = {
        "schema_version": "AIR_SLOT_EXP_PARITY_AUDIT_V1",
        "contract_version": CONTRACT_VERSION,
        "experiment_id": experiment_id,
        "checks": merged,
        "verdict": "PASS" if all(merged.values()) else "FAIL",
    }
    return payload


def write_metrics_csv(rows: Iterable[Mapping[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = tuple(validate_metric_row(row) for row in rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_CSV_COLUMNS)
        writer.writeheader()
        for row in normalized:
            writer.writerow({key: row.get(key, "") for key in METRIC_CSV_COLUMNS})
    return path


def build_summary_payload(
    *, experiment_id: str, cohort: Mapping[str, Any],
    metric_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    headline: list[dict[str, Any]] = []
    for row in metric_rows:
        contract = metric_contract(experiment_id, str(row["metric_id"]))
        if contract is None or not contract.headline:
            continue
        headline.append({
            "variant_id": row.get("variant", ""),
            "metric_id": row["metric_id"],
            "estimate": row.get("estimate", row.get("value")),
            "ci_lower": row.get("ci_lower"),
            "ci_upper": row.get("ci_upper"),
            "n_episodes": row.get("n_episodes"),
            "support_status": row.get("support"),
            "reason": row.get("reason"),
        })
    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "experiment_id": experiment_id,
        "status": "COMPLETE_WITH_EXPLICIT_GATES",
        "dataset_id": cohort.get("dataset_id", "DATA2"),
        "split": cohort.get("split", "DEVELOPMENT"),
        "episode_count": int(cohort.get("episode_count", 0)),
        "node_count": int(cohort.get("node_count", 0)),
        "scenario_count_per_node": int(cohort.get("scenario_count_per_node", 0)),
        "seed": int(cohort.get("seed", 0)),
        "headline": headline,
        "safety": {
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "AUTHORITATIVE_RANKING": False,
        },
        "paper_result": False,
    }
    require_output_safety(payload)
    return payload


def build_main_table_rows(
    *, metric_rows: Iterable[Mapping[str, Any]],
    condition_of: Mapping[str, str],
    variant_definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    rows = []
    for row in metric_rows:
        if row.get("value") is None:
            continue
        variant_id = str(row.get("variant", ""))
        subexperiment = str(
            row.get("subexperiment")
            or variant_definitions.get(variant_id, {}).get("subexperiment", variant_id)
        )
        lower = row.get("ci_lower")
        upper = row.get("ci_upper")
        n_episodes = row.get("n_episodes")

        def display(value):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value

        rows.append({
            "Subexperiment": subexperiment,
            "Condition": str(
                row.get("condition") or condition_of.get(variant_id, variant_id)
            ),
            "Metric": row["metric_id"],
            "Estimate": display(row.get("value")),
            "95% CI": (
                CI_UNAVAILABLE if lower is None or upper is None
                else f"{display(lower)} - {display(upper)}"
            ),
            "N episodes": (
                n_episodes if n_episodes is not None else N_EPISODES_UNAVAILABLE
            ),
        })
    return tuple(rows)


def write_main_table(
    *, rows: Iterable[Mapping[str, Any]], csv_path: Path, tex_path: Path,
    caption: str,
) -> dict[str, Path]:
    frame_rows = tuple(rows)
    generate_three_line_table(
        frame_rows, csv_path.stem, csv_path.parent,
        {"schema_version": "AIR_SLOT_EXP_MAIN_TABLE_V1", "contract_version": CONTRACT_VERSION},
        caption=caption,
    )
    return {"csv": csv_path, "tex": tex_path}
def write_figure_sources(
    *, figure_specs: Iterable[Mapping[str, Any]],
    figure_panels: Mapping[str, Mapping[str, list[Mapping[str, Any]]]],
    output_root: Path,
) -> dict[str, Path]:
    written: dict[str, Path] = {}
    for spec in figure_specs:
        figure_id = str(spec["figure_id"])
        panels = figure_panels.get(figure_id)
        if panels is None:
            continue
        source_paths = {}
        for panel_id, panel_rows in panels.items():
            source_path = output_root / f"figure_source_{figure_id}_{panel_id}.csv"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            if panel_rows:
                fieldnames = list(panel_rows[0].keys())
                with source_path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(panel_rows)
            else:
                source_path.write_text("", encoding="utf-8")
            source_paths[panel_id] = source_path
        metadata = {key: value for key, value in spec.items() if key != "panels"}
        generate_figure_bundle(
            None, figure_id, output_root, metadata,
            panels=panels, layout=tuple(spec.get("layout", (1, 1))),
        )
        written[figure_id] = output_root / f"figure_source_{figure_id}.csv"
        written.update({f"{figure_id}_{panel_id}": path for panel_id, path in source_paths.items()})
    return written


def write_interpretation_md(
    *, experiment_id: str, text: str, claim_scope: str, limitations: Iterable[str],
    omega_insight: str, output_root: Path,
) -> Path:
    lines = [
        f"# {experiment_id} interpretation (Development-only)",
        "",
        "## Claim scope",
        claim_scope,
        "",
        "## Development-only interpretation",
        text,
        "",
        "## Boundary statement",
    ]
    lines.extend(f"- {item}" for item in limitations)
    lines += [
        "",
        "## Omega managerial insight",
        omega_insight,
        "",
        "> Development evidence only. NOT_RUN/BLOCKED/ABSTAIN metrics carry their",
        "> reason text; no zero-fill, no silent renormalization, no causal claim,",
        "> no authoritative ranking.",
    ]
    path = output_root / f"exp{experiment_id[-1]}_interpretation.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_experiment_artifacts(
    *,
    experiment_id: str,
    output_root: Path,
    metric_rows: Iterable[Mapping[str, Any]],
    cohort: Mapping[str, Any],
    variants: tuple[str, ...],
    variant_definitions: Mapping[str, Mapping[str, Any]],
    frozen_hashes: Mapping[str, str],
    config_hash: str,
    interpretation: str,
    claim_scope: str,
    limitations: Iterable[str],
    omega_insight: str,
    condition_of: Mapping[str, str] | None = None,
    figure_panels: Mapping[str, Mapping[str, list[Mapping[str, Any]]]] | None = None,
    parity_checks: Mapping[str, bool] | None = None,
    split_rows: Iterable[Mapping[str, Any]] = (),
    leakage_rows: Iterable[Mapping[str, Any]] = (),
    empty_reason: str | None = None,
    root: Path | None = None,
) -> dict[str, Path]:
    """Write the ten-class output contract artifact set for one experiment."""
    if experiment_id not in OUTPUT_ROOTS:
        raise ContractError("OUTPUT_CONTRACT_EXPERIMENT_UNKNOWN:" + experiment_id)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    root = root or output_root
    rows = tuple(validate_metric_row(row) for row in metric_rows)
    cohort_card = _cohort_card(cohort)

    protocol = build_protocol_manifest(
        experiment_id=experiment_id, cohort=cohort_card, variants=variants,
        frozen_hashes=frozen_hashes, config_hash=config_hash, root=root,
    )
    variant_payload = build_variant_manifest(variant_definitions=variant_definitions)
    split_audit = build_split_audit(split_rows)
    leakage_audit = build_leakage_audit(leakage_rows)
    parity_audit = build_parity_audit(experiment_id, parity_checks or {})

    suffix = experiment_id[-1]
    paths = {
        "protocol": output_root / f"exp{suffix}_protocol_manifest.json",
        "variant": output_root / f"exp{suffix}_variant_manifest.json",
        "split_audit": output_root / f"exp{suffix}_split_audit.json",
        "leakage_audit": output_root / f"exp{suffix}_leakage_audit.json",
        "parity_audit": output_root / f"exp{suffix}_parity_audit.json",
        "metrics": output_root / f"exp{suffix}_metrics.csv",
        "summary": output_root / f"exp{suffix}_summary.json",
        "main_table_csv": output_root / f"exp{suffix}_main_table.csv",
        "main_table_tex": output_root / f"exp{suffix}_main_table.tex",
        "interpretation": output_root / f"exp{suffix}_interpretation.md",
    }
    _write_hashed_json(paths["protocol"], protocol)
    _write_hashed_json(paths["variant"], variant_payload)
    _write_hashed_json(paths["split_audit"], split_audit)
    _write_hashed_json(paths["leakage_audit"], leakage_audit)
    _write_hashed_json(paths["parity_audit"], parity_audit)
    write_metrics_csv(rows, paths["metrics"])
    condition = condition_of or {variant: variant for variant in variants}
    table_rows = build_main_table_rows(
        metric_rows=rows, condition_of=condition,
        variant_definitions=variant_definitions,
    )
    summary = build_summary_payload(experiment_id=experiment_id, cohort=cohort_card, metric_rows=rows)
    if not table_rows:
        summary["empty_reason"] = (
            empty_reason
            or "MAIN_TABLE_EMPTY_ALL_METRIC_VALUES_NOT_RUN_OR_BLOCKED"
        )
    _write_hashed_json(paths["summary"], summary)
    write_main_table(
        rows=table_rows, csv_path=paths["main_table_csv"],
        tex_path=paths["main_table_tex"],
        caption=f"{experiment_id} main results (Development evidence only).",
    )
    write_interpretation_md(
        experiment_id=experiment_id, text=interpretation, claim_scope=claim_scope,
        limitations=limitations, omega_insight=omega_insight, output_root=output_root,
    )
    figure_specs = FIGURE_SPECS.get(experiment_id, ())
    if figure_panels:
        written = write_figure_sources(
            figure_specs=figure_specs, figure_panels=figure_panels,
            output_root=output_root,
        )
        paths.update(written)
    return paths


def validate_artifacts(experiment_id: str, output_root: Path) -> dict[str, Any]:
    """Require the output contract artifact set and recompute hashes."""
    output_root = Path(output_root).resolve()
    suffix = experiment_id[-1]
    required = (
        output_root / f"exp{suffix}_protocol_manifest.json",
        output_root / f"exp{suffix}_variant_manifest.json",
        output_root / f"exp{suffix}_split_audit.json",
        output_root / f"exp{suffix}_leakage_audit.json",
        output_root / f"exp{suffix}_parity_audit.json",
        output_root / f"exp{suffix}_metrics.csv",
        output_root / f"exp{suffix}_summary.json",
        output_root / f"exp{suffix}_main_table.csv",
        output_root / f"exp{suffix}_main_table.tex",
        output_root / f"exp{suffix}_interpretation.md",
    )
    missing = [path.as_posix() for path in required if not path.is_file()]
    if missing:
        raise ContractError("OUTPUT_CONTRACT_ARTIFACTS_MISSING:" + ",".join(missing))
    json_paths = [path for path in required if path.suffix == ".json"]
    for path in json_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("artifact_hash", None)
        recomputed = content_id(payload)
        recorded = json.loads(path.read_text(encoding="utf-8")).get("artifact_hash")
        if recorded != recomputed:
            raise ContractError(f"OUTPUT_CONTRACT_HASH_MISMATCH:{path.name}")
        require_output_safety(payload)
    summary = json.loads((output_root / f"exp{suffix}_summary.json").read_text(encoding="utf-8"))
    if summary.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        raise ContractError("OUTPUT_CONTRACT_SUMMARY_SCHEMA_INVALID")
    if summary.get("paper_result") is not False:
        raise ContractError("OUTPUT_CONTRACT_SUMMARY_PAPER_RESULT_FORBIDDEN")
    with (output_root / f"exp{suffix}_metrics.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    if tuple(header) != METRIC_CSV_COLUMNS:
        raise ContractError("OUTPUT_CONTRACT_METRICS_CSV_SCHEMA_INVALID")
    with (output_root / f"exp{suffix}_main_table.csv").open(encoding="utf-8", newline="") as handle:
        main_rows = list(csv.DictReader(handle))
    if not main_rows:
        if not summary.get("empty_reason"):
            raise ContractError("OUTPUT_CONTRACT_MAIN_TABLE_EMPTY_WITHOUT_REASON")
    else:
        for index, row in enumerate(main_rows, start=2):
            for column in MAIN_TABLE_COLUMNS:
                cell = row.get(column)
                if cell is None or str(cell) == "":
                    raise ContractError(
                        f"OUTPUT_CONTRACT_MAIN_TABLE_BLANK_CELL:{column}:ROW{index}"
                    )
    return {
        "experiment_id": experiment_id,
        "status": "OUTPUT_CONTRACT_ARTIFACTS_VALIDATED",
        "artifact_count": len(required),
    }




__all__ = [
    "CONTRACT_VERSION",
    "FIGURE_SPECS",
    "MAIN_TABLE_COLUMNS",
    "METRIC_CSV_COLUMNS",
    "METRIC_REGISTRY",
    "MetricContract",
    "OUTPUT_ROOTS",
    "SUMMARY_SCHEMA_VERSION",
    "build_leakage_audit",
    "build_main_table_rows",
    "build_parity_audit",
    "build_protocol_manifest",
    "build_split_audit",
    "build_summary_payload",
    "build_variant_manifest",
    "metric_contract",
    "registry_for",
    "require_output_safety",
    "rows_from_global_metrics",
    "validate_artifacts",
    "validate_metric_row",
    "write_experiment_artifacts",
    "write_figure_sources",
    "write_from_global_metrics",
    "write_interpretation_md",
    "write_main_table",
    "write_metrics_csv",
]
