# -*- coding: utf-8 -*-
"""Metrics/protocol layer for the M5-b consequence-side stability battery.

Directly imported by ``data2/scripts/consequence_stability_battery.py`` and by
``data2/scripts/run_m5b_autonomous.py``.  This module contains NO new scientific
estimand: every screening ranking, consequence aggregation, and recovery
enumeration reuses the canonical repository implementations

  - headroom quantile rules ......... model.M3.support (+ train_support population)
  - node reference bindings ......... validation.v2_phase5.common.build_node_binding
  - consequence mapping ............. model.M2.consequence_service.M2ConsequenceService
  - comparison support .............. validation.v2_phase5.common.comparison_support_for
  - Stage-I selection ............... model.M3.stage1.select_paired_attention
  - Stage-II exact enumeration ...... model.M3.stage2.solve_recovery/expected_objective
  - L_att / L_rec / activation ...... model.M4.evaluation

Only plumbing is new: the protocol V2 freeze, per-year headroom
materialization, M2-bundle hash verification, evaluation-pass artifact I/O,
bootstrap resampling, and the equivalence/identifiability bookkeeping demanded
by the frozen protocol.  Missing canonical inputs raise typed M5BBlockedError
subclasses (never zero-filled substitutes).

Bootstrap note: point estimates use the full canonical objects
(``select_paired_attention`` + ``evaluate_attention_allocation`` +
``evaluate_recovery_loss``).  Inside the 2000 bootstrap replicates the same
frozen selector rules (``STAGE_I_TIE_BREAK`` ordering and
``stage1.attention_capacity_k``) are applied vectorized for feasibility; the
replicate rule is identical to the canonical selector by construction and every
point estimate is the canonical object itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from model.common.decision_contracts import (  # noqa: E402
    AttentionDecision,
    AttentionEntry,
    ConsequenceScenarioSet,
    HeadroomSummary,
    PrioritySignal,
    SignalKind,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState  # noqa: E402
from model.common.identity import content_id  # noqa: E402
from model.M2.comparison_support import (  # noqa: E402
    PRIMARY_AGGREGATION_VIEW,
    delay_priority_signal,
    phi_c,
)
from model.M2.consequence_service import (  # noqa: E402
    ConsequenceReferenceBinding,
    M2ConsequenceService,
)
from model.M2.context import load_data2_reference_bundle  # noqa: E402
from model.M3.stage1 import (  # noqa: E402
    NOMINAL_ATTENTION_CAPACITY,
    attention_capacity_k,
    select_paired_attention,
)
from model.M3.stage2 import (  # noqa: E402
    LAMBDA_NOMINAL,
    action_grid,
    expected_objective,
    solve_recovery,
)
from model.M3.support import (  # noqa: E402
    FLOOR_TO_MINUTES,
    TURNAROUND_QUANTILE_NOMINAL,
    build_headroom_summary,
)
from model.M3.transition import TransitionContext  # noqa: E402
from model.M4.evaluation import (  # noqa: E402
    aggregate_attention_evaluations,
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)
from model.PRE.decision_environment import action_stage_class, is_actionable  # noqa: E402
from model.PRE.reference.data2_m2_train_fit import (  # noqa: E402
    collect_train_rows,
    ontime_paths,
)
from model.PRE.streaming.data2 import load_timezones  # noqa: E402
from validation.v2_phase5.common import (  # noqa: E402
    TRAIN_MONTHS,
    build_node_binding,
    chain_id_for_episode,
    comparison_support_for,
    consequence_set,
    expected_cu_for_support,
    file_hash,
    representation_spec,
    state_scenario_from_coordinates,
    state_set_from_m1_scenarios,
)
from validation.v2_phase5.train_support import (  # noqa: E402
    build_rotation_population,
    headroom_minutes,
)

REPO = _REPO_ROOT
STUDY_ROOT = REPO / "data2" / "reports" / "cohort_size_stability"
PRE_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
INSTANCE_ID = "data2_2017_2022"
TRAIN_SEED = 20260821
BOOTSTRAP_SEED = 20260906
BOOTSTRAP_REPLICATES = 2000
SCENARIO_COUNT = 64
NOMINAL_Q = NOMINAL_ATTENTION_CAPACITY
EVAL_BUDGET_HOURS = 6.0
LADDER = (4096, 2048, 1024)
SMOKE_E = 3
HISTORY_JOINT = "HISTORY_JOINT"
HISTORY_JOINT_SPEC = representation_spec(TemporalKind.HISTORY, UncertaintyKind.JOINT)
STAGE1_ACTIONABLE_STAGES = (OperationalStage.PRE_IB, OperationalStage.POST_IB_PRE_OB)
COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation",
    "P_time", "P_itinerary", "P_service", "R_operating",
)
BUNDLE_KINDS = (
    "taxi", "turnaround", "downstream_exposure", "passenger",
    "expected_passengers", "connection_share",
)
SUPPORT_CODE = {SupportState.SUPPORTED: 1, SupportState.DEGRADED: 2,
                SupportState.ABSTAIN: 0}
SUPPORT_FROM_CODE = {code: state for state, code in SUPPORT_CODE.items()}
SHARD_EPISODES = 256
IDENTIFIABILITY_MIN_EVENTS = 30

V1_PROTOCOL_NAME = "CONSEQUENCE_STABILITY_PROTOCOL_V1.json"
V2_PROTOCOL_NAME = "CONSEQUENCE_STABILITY_PROTOCOL_V2.json"
V1_EXPECTED_HASH = "sha256:bbb70f0796a947488001da21a9ec3e1b5ba7a8b48a7b8a95bd1a6f6692fc8d40"
FROZEN_2019_HEADROOM = (
    REPO / "artifacts" / "diagnostics" / "v2_phase5_development"
    / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json"
)
FROZEN_2019_HEADROOM_VALUES = {"u_max": 45.0, "turnaround_lower_bound_q": 41.0}
HEADROOM_SCHEMA = "M5B_TRAIN_HEADROOM_SUMMARY_V1"
PASS_MANIFEST_NAME = "PASS_MANIFEST.json"
NODE_FRAME_NAME = "node_frame.jsonl"
DECISIONS_NAME = "stage2_decisions.json"
BINDINGS_NAME = "bindings.json"
LADDER_PROBE_NAME = "LADDER_PROBE.json"

BINDING_METRICS: dict[str, str] = {
    "kendall_tau_b": "kendall_tau_b",
    "ranking_at_k": "ranking_at_k",
    "top_k_overlap": "top_k_overlap_abs",
    "large_decile_displacement_rate": "large_decile_displacement_rate_abs",
    "activation_rate": "activation_rate_abs",
    "missed_activation_rate": "missed_activation_rate_abs",
    "false_activation_rate": "false_activation_rate_abs",
    "l_att": "l_att_scale_normalized_abs",
    "l_rec": "l_rec_scale_normalized_abs",
}
for _component in COMPONENTS:
    BINDING_METRICS[f"component_{_component}"] = "seven_cu_components_scale_normalized_abs"

METRIC_DEFINITIONS = {
    "kendall_tau_b": (
        "Kendall tau-b between the P^C ranking and the P^D ranking of the "
        "eligible nodes inside one cohort (canonical Delay-vs-Consequence "
        "contrast, as computed by M4 evaluate_attention_allocation)."
    ),
    "ranking_at_k": (
        "|topK(P^C) intersect topK(P^D)| / K within one cohort, with "
        "K = attention_capacity_k(0.10, N_eligible)."
    ),
    "top_k_overlap": (
        "FIT: |topK(model_N, P^C) intersect topK(model_ref, P^C)| / K over the "
        "shared case set. EVAL: |topK_N(P^C) intersect topK_ref(P^C)| / "
        "|topK_ref| (reference shortlist retention)."
    ),
    "large_decile_displacement_rate": (
        "Share of eligible nodes whose P^C decile differs by >=3 between the "
        "two score maps; deciles formed by the "
        "cohort_size_metrics.max_decile_displacement construction."
    ),
    "component_*": (
        "Support-conditional expected CU per component; scale-normalized "
        "delta vs reference with denominator max(protocol floor, "
        "year_train_scale_median)."
    ),
    "activation_rate": (
        "Share of Stage-II decisions with u_star > 0 over the comparison "
        "cohort (canonical exact enumeration)."
    ),
    "missed_activation_rate": (
        "MISSED_ACTIVATION events (reference u*>0, comparator u*=0) / "
        "comparison cohort size (M4 evaluate_recovery_loss)."
    ),
    "false_activation_rate": (
        "FALSE_ACTIVATION events (reference u*=0, comparator u*>0) / "
        "comparison cohort size."
    ),
    "l_att": (
        "Attention-allocation loss L_att = (A*(H_ref) - A*(H_comp)) / A*(H_ref) "
        "on the consequence-priority basis (M4 evaluate_attention_allocation; "
        "stage-combined via aggregate_attention_evaluations)."
    ),
    "l_rec": (
        "Recovery loss L_rec = sum(J*(u(r)) - J*(u*)) / sum V* over the union "
        "Stage-II cohort on the reference objective basis (M4 "
        "evaluate_recovery_loss); comparator nodes outside the comparator "
        "shortlist carry typed zero action."
    ),
}


# --------------------------------------------------------------------------- #
# typed errors
# --------------------------------------------------------------------------- #

class M5BBlockedError(RuntimeError):
    """Typed blocking condition; ``status`` is the machine-readable token."""

    status = "BLOCKED_M5B"

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class ProtocolHashMismatch(M5BBlockedError):
    status = "BLOCKED_PROTOCOL_HASH"


class HeadroomReproductionError(M5BBlockedError):
    status = "BLOCK_M5B_HEADROOM_REPRODUCTION"


class MissingBundleError(M5BBlockedError):
    status = "BLOCKED_M2_REFERENCE"


class ConsequenceInterfaceError(M5BBlockedError):
    status = "BLOCKED_CONSEQUENCE_INTERFACE"


class ComputeBudgetError(M5BBlockedError):
    status = "BLOCK_M5B_COMPUTE_BUDGET"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] [m5b-metrics] {message}", flush=True)


def sha256_json(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return file_hash(path)


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def git_provenance() -> dict[str, str]:
    def _git(*args: str) -> str:
        try:
            out = subprocess.run(
                ["git", *args], cwd=str(REPO), capture_output=True, text=True,
                timeout=30, check=True)
            return out.stdout.strip()
        except Exception as error:  # pragma: no cover - provenance only
            return f"UNAVAILABLE:{error}"
    return {
        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
    }


def source_script_hashes() -> dict[str, str]:
    scripts = sorted((REPO / "data2" / "scripts").glob("consequence_stability_*.py"))
    scripts.append(Path(__file__).resolve())
    return {path.name: file_hash(path) for path in sorted(set(scripts))}


def _require(condition: bool, error: M5BBlockedError) -> None:
    if not condition:
        raise error


# --------------------------------------------------------------------------- #
# protocol V2 freeze (topmost rule: freeze before any floor/stability metric)
# --------------------------------------------------------------------------- #

def _protocol_serialization(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _protocol_hash_of(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "protocol_hash"}
    return "sha256:" + hashlib.sha256(_protocol_serialization(body)).hexdigest()


FLOOR_RULE_V2 = {
    "detection": (
        "per sentinel setting (year, N): compare the two replica digests "
        "(examples, normalization, calibration, state_dict); any digest "
        "mismatch sets nondeterminism_detected for that setting"
    ),
    "quantification": (
        "evaluate both replica checkpoints of every sentinel setting on the "
        "SAME fixed development case set (top evaluation_E episodes, with "
        "evaluation_E chosen by the compute_fallback_ladder probe) and compute "
        "every binding metric value per replica; "
        "TRAINING_NONDETERMINISM_FLOOR_m = max over settings of "
        "|metric_m(replica_1) - metric_m(replica_2)|"
    ),
    "binding_metrics": sorted(BINDING_METRICS.keys()),
    "decision": (
        "stop with BLOCK_M5B_NONDETERMINISM iff any binding metric has "
        "floor_m >= floor_fraction * half_width(band_m); otherwise record all "
        "floors and proceed to FIT/EVAL"
    ),
    "floor_fraction": 0.1,
    "scope": (
        "floor metrics are diagnostic only; they are computed before any "
        "FIT/EVAL stability metric and are never stability results"
    ),
}


def create_or_verify_protocol_v2(study_root: Path = STUDY_ROOT) -> dict[str, Any]:
    """Create (deterministically) or hash-verify CONSEQUENCE_STABILITY_PROTOCOL_V2."""

    v2_path = study_root / V2_PROTOCOL_NAME
    if v2_path.is_file():
        payload = json.loads(v2_path.read_text(encoding="utf-8"))
        stored = payload.get("protocol_hash")
        recomputed = _protocol_hash_of(payload)
        if stored != recomputed:
            raise ProtocolHashMismatch(
                f"PROTOCOL_V2_HASH_MISMATCH:{stored}/{recomputed}")
        return payload

    v1_path = study_root / V1_PROTOCOL_NAME
    if not v1_path.is_file():
        raise ProtocolHashMismatch(f"PROTOCOL_V1_MISSING:{v1_path}")
    v1_payload = json.loads(v1_path.read_text(encoding="utf-8"))
    v1_stored = v1_payload.get("protocol_hash")
    if v1_stored != V1_EXPECTED_HASH:
        raise ProtocolHashMismatch(
            f"PROTOCOL_V1_STORED_HASH_UNEXPECTED:{v1_stored}")
    v1_recomputed = _protocol_hash_of(v1_payload)
    v1_verified = bool(v1_stored == v1_recomputed)

    body = {key: value for key, value in v1_payload.items()
            if key != "protocol_hash"}
    v2 = json.loads(json.dumps(body, ensure_ascii=False))
    v2["schema_version"] = "CONSEQUENCE_STABILITY_PROTOCOL_V2"
    v2["v2_lineage"] = {
        "predecessor_schema_version": v1_payload.get("schema_version"),
        "predecessor_protocol_hash": v1_stored,
        "predecessor_protocol_hash_recomputed_match": v1_verified,
        "change_scope": (
            "m1_determinism_sentinel.floor_rule operationalization only; "
            "bands, seed, N grid, and fallback ladder are unchanged"
        ),
        "created_by": "data2/scripts/consequence_stability_metrics.py",
    }
    v1_sentinel = dict(v2.get("m1_determinism_sentinel", {}))
    v2["m1_determinism_sentinel"] = {
        **v1_sentinel,
        "floor_rule_v1_text": v1_sentinel.get("floor_rule"),
        "floor_rule": FLOOR_RULE_V2,
    }
    v2["protocol_hash"] = _protocol_hash_of(v2)
    write_json_atomic(v2_path, v2)
    log(f"protocol V2 created: {v2['protocol_hash']}")
    return v2


def band_half_width(protocol: Mapping[str, Any], band_key: str) -> float:
    band = protocol["practical_equivalence_bands"][band_key]
    if isinstance(band, (list, tuple)):
        return float(band[1])
    return float(band)


def band_epsilon(protocol: Mapping[str, Any], band_key: str) -> float:
    return band_half_width(protocol, band_key)


# --------------------------------------------------------------------------- #
# per-year Stage-II headroom (authoritative: no cross-year reuse)
# --------------------------------------------------------------------------- #

def build_year_headroom(year: int, *, repo_root: Path = REPO,
                        study_root: Path = STUDY_ROOT) -> dict[str, Any]:
    """Derive the year-specific HeadroomSummary from that year's H1 train data.

    2019 must reproduce the frozen v2_phase5 values exactly (u_max=45.0,
    turnaround_lower_bound_q=41.0); any deviation is a typed stop.  2020 uses
    the same computational definition on its own H1 rows; the frozen 2019
    summary is never reused across years.
    """

    out_path = study_root / str(year) / "M2_TRAIN_HEADROOM_SUMMARY.json"
    frozen = None
    if year == 2019 and FROZEN_2019_HEADROOM.is_file():
        frozen = json.loads(FROZEN_2019_HEADROOM.read_text(encoding="utf-8"))

    if out_path.is_file():
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        if (payload.get("schema_version") == HEADROOM_SCHEMA
                and payload.get("year") == year
                and payload.get("status") == "PASS"):
            if frozen is not None:
                _check_headroom_reproduction(payload, frozen)
            log(f"headroom {year}: reused (u_max="
                f"{payload['factual_headroom']['headroom_summary']['u_max']})")
            return payload
        log(f"headroom {year}: existing payload unusable; rederiving")

    paths = ontime_paths(repo_root, TRAIN_MONTHS, year=year)
    zones = load_timezones(repo_root / "data2" / "refs" / "us_airport_timezones.csv")
    rows = collect_train_rows(paths, zones)
    # Reference-legality gate (same rule as the M2 bundle builder): the
    # rotation/episode builders hard-require these keys non-empty, and a row
    # missing an observed gate time can never form a legal rotation, so it is
    # dropped explicitly and counted.  2019 H1 drops zero rows; 2020 H1 drops
    # a small number of rows that carry no usable actual gate time.
    from model.PRE.reference.turnaround_data2 import _REQUIRED_ROW_KEYS
    rows_before_gate = len(rows)
    rows = [row for row in rows
            if all(row.get(key) not in (None, "") for key in _REQUIRED_ROW_KEYS)]
    dropped_by_gate = rows_before_gate - len(rows)
    population = build_rotation_population(rows)
    turnaround = population["turnaround_minutes"]

    quantiles = {
        f"q{int(round(q * 100)):02d}": float(np.quantile(turnaround, q))
        for q in (0.10, TURNAROUND_QUANTILE_NOMINAL, 0.30)
    }
    headroom_values = headroom_minutes(
        population, turnaround_lower_bound=quantiles["q20"])
    summary = build_headroom_summary(
        turnaround_minutes=turnaround,
        headroom_minutes=headroom_values,
        source_id=(
            f"TRAIN_DATA2_{year}_H1:"
            + ",".join(path.name for path in paths)
            + f":n={len(turnaround)}"
        ),
    )
    grid = action_grid(summary.u_max, floor_to_minutes=FLOOR_TO_MINUTES)

    payload: dict[str, Any] = {
        "schema_version": HEADROOM_SCHEMA,
        "status": "PASS",
        "year": year,
        "artifact_scope": "M5B_PILOT_STAGE2_SUPPORT_ONLY",
        "derivation": (
            "same computational definition as validation/v2_phase5/"
            "train_support.py (T_lb = Q20(T^turn | Train H1); "
            "U_max = floor5(Q90(H+ | Train H1))); year-parameterized inputs; "
            "no cross-year reuse"
        ),
        "train_partition": {
            "start": f"{year}-01-01", "end": f"{year}-06-30",
            "months": list(TRAIN_MONTHS), "fit_period": f"{year}-H1",
        },
        "source_paths": [str(path) for path in paths],
        "source_hashes": [file_hash(path) for path in paths],
        "episode_count": population["episode_count"],
        "excluded_rotations": population["excluded_rotations"],
        "rotation_count": len(turnaround),
        "rows_streamed": rows_before_gate,
        "rows_dropped_by_reference_legality_gate": dropped_by_gate,
        "turnaround_median_minutes": float(np.median(turnaround)),
        "turnaround_quantile_minutes": quantiles,
        "factual_headroom": {
            "definition": (
                "max(actual_departure - max(scheduled_departure, "
                "actual_arrival + turnaround_q20), 0)"
            ),
            "positive_count": int(np.count_nonzero(np.asarray(headroom_values) > 0.0)),
            "headroom_summary": summary.model_dump(mode="json"),
        },
        "u_max_nominal_minutes": summary.u_max,
        "action_grid": {"step_minutes": FLOOR_TO_MINUTES, "nominal": list(grid)},
        "final_test_access_count": 0,
    }
    if frozen is not None:
        _check_headroom_reproduction(payload, frozen)
        payload["frozen_2019_reproduction"] = {
            "frozen_artifact": str(FROZEN_2019_HEADROOM),
            "frozen_hash": file_hash(FROZEN_2019_HEADROOM),
            "reproduced": True,
        }
    payload["artifact_hash"] = sha256_json(
        {key: value for key, value in payload.items() if key != "artifact_hash"})
    write_json_atomic(out_path, payload)
    log(f"headroom {year}: derived (u_max={summary.u_max}, "
        f"lb={summary.turnaround_lower_bound_q}, rotations={len(turnaround)})")
    return payload


def _check_headroom_reproduction(payload: Mapping[str, Any],
                                 frozen: Mapping[str, Any]) -> None:
    frozen_summary = frozen["factual_headroom"]["headroom_summary"]
    summary = payload["factual_headroom"]["headroom_summary"]
    diffs: dict[str, Any] = {}
    for key, expected in FROZEN_2019_HEADROOM_VALUES.items():
        observed = float(summary[key])
        if abs(observed - float(expected)) > 1e-9:
            diffs[key] = {"expected": expected, "observed": observed}
        if abs(observed - float(frozen_summary[key])) > 1e-9:
            diffs[f"{key}_vs_frozen_artifact"] = {
                "expected": frozen_summary[key], "observed": observed}
    if diffs:
        raise HeadroomReproductionError(
            f"HEADROOM_2019_REPRODUCTION_FAILED:{diffs}", detail=diffs)
    frozen_rotation = frozen.get("rotation_count")
    if frozen_rotation is not None and int(payload["rotation_count"]) != int(frozen_rotation):
        raise HeadroomReproductionError(
            "HEADROOM_2019_ROTATION_COUNT_MISMATCH:"
            f"{payload['rotation_count']}/{frozen_rotation}")


def year_headroom_summary(year: int, *,
                          study_root: Path | None = None) -> HeadroomSummary:
    if study_root is None:
        study_root = (RUN_STUDY_BASE if RUN_STUDY_BASE is not None
                      else STUDY_ROOT)
    payload = build_year_headroom(year, study_root=study_root)
    return HeadroomSummary.model_validate(payload["factual_headroom"]["headroom_summary"])


# --------------------------------------------------------------------------- #
# M2 reference bundle (verify-only; never rebuild or cross-year substitute)
# --------------------------------------------------------------------------- #

# run context: a run with its own output root reads its M2 reference bundles
# from that root ("bundles" base), never from the shared PRE location
RUN_BUNDLE_BASE: Path | None = None
# study base for derived artifacts whose callers do not pass study_root
# explicitly (year_headroom_summary): runs with their own output root set it
# so nothing leaks into the shared pilot STUDY_ROOT
RUN_STUDY_BASE: Path | None = None


def set_run_context(*, bundle_base: Path | None,
                    study_base: Path | None = None) -> None:
    global RUN_BUNDLE_BASE, RUN_STUDY_BASE
    RUN_BUNDLE_BASE = Path(bundle_base) if bundle_base is not None else None
    RUN_STUDY_BASE = Path(study_base) if study_base is not None else None


def m2_bundle_dir(year: int, *, repo_root: Path = REPO) -> Path:
    base = RUN_BUNDLE_BASE if RUN_BUNDLE_BASE is not None else (
        repo_root / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1")
    return base / str(year) / "M2_REFERENCES"


def m2_bundle_present(year: int, *, repo_root: Path = REPO) -> bool:
    return (m2_bundle_dir(year, repo_root=repo_root)
            / "M2_REFERENCE_BUNDLE_MANIFEST.json").is_file()


def load_year_m2_bundle(year: int, *, repo_root: Path = REPO) -> dict[str, Any]:
    """Load and hash-verify one year's M2 reference bundle; fail closed."""

    directory = m2_bundle_dir(year, repo_root=repo_root)
    manifest_path = directory / "M2_REFERENCE_BUNDLE_MANIFEST.json"
    if not manifest_path.is_file():
        raise MissingBundleError(f"M2_BUNDLE_MISSING:{directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("year", -1)) != int(year):
        raise MissingBundleError(
            f"M2_BUNDLE_YEAR_MISMATCH:{manifest.get('year')}/{year}")
    recorded = manifest.get("payload_hashes", {})
    payloads: dict[str, Any] = {}
    file_hashes: dict[str, str] = {}
    for kind in BUNDLE_KINDS:
        path = directory / f"M2_{kind.upper()}_REFERENCE_{year}-H1.json"
        if not path.is_file():
            raise MissingBundleError(f"M2_BUNDLE_FILE_MISSING:{path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        digest = sha256_json(payload)
        expected = recorded.get(kind)
        if expected is None or expected != digest:
            raise MissingBundleError(
                f"M2_BUNDLE_HASH_MISMATCH:{kind}:{expected}/{digest}")
        payloads[kind] = payload
        file_hashes[path.name] = file_hash(path)
    scales_path = directory / "M2_SEVEN_COMPONENT_TRAIN_SCALES.json"
    if not scales_path.is_file():
        raise MissingBundleError(f"M2_SCALES_MISSING:{scales_path}")
    scales_payload = json.loads(scales_path.read_text(encoding="utf-8"))
    if int(scales_payload.get("experiment_year", year)) != int(year):
        raise MissingBundleError("M2_SCALES_YEAR_MISMATCH")
    scales_self = scales_payload.get("bundle_hash")
    scales_recomputed = sha256_json(
        {key: value for key, value in scales_payload.items()
         if key != "bundle_hash"})
    if scales_self is not None and scales_self != scales_recomputed:
        raise MissingBundleError(
            f"M2_SCALES_HASH_MISMATCH:{scales_self}/{scales_recomputed}")
    scales = {component: float(entry["median"])
              for component, entry in scales_payload["scales"].items()}
    missing = [component for component in COMPONENTS if component not in scales]
    if missing:
        raise MissingBundleError(f"M2_SCALES_COMPONENTS_MISSING:{missing}")
    return {
        "year": year,
        "payloads": payloads,
        "scales": scales,
        "manifest": manifest,
        "manifest_hash": file_hash(manifest_path),
        "scales_payload": scales_payload,
        "file_hashes": file_hashes,
        "bundle_hash": content_id({
            "manifest_hash": file_hash(manifest_path),
            "scales_hash": file_hash(scales_path),
            "file_hashes": file_hashes,
        }),
        "directory": str(directory),
    }


# --------------------------------------------------------------------------- #
# year consequence service
# --------------------------------------------------------------------------- #

class YearFormalCURegistryAdapter:
    """Duck-typed registry for M2ConsequenceService bound to ONE year's scales.

    ``M2Data2FormalCuRegistry``'s freeze validator only accepts the frozen 2019
    registry identities, so a year-parameterized formal registry object cannot
    be constructed.  This adapter exposes exactly the members
    M2ConsequenceService consumes (``scale``/``registry_id``/``registry_hash``)
    over the year bundle's frozen scales; the native formulas and the CU
    transformation remain 100% the canonical service code.
    """

    def __init__(self, year: int, scales: Mapping[str, float]) -> None:
        self.year = int(year)
        self._scales = {str(key): float(value) for key, value in scales.items()}
        self.registry_id = f"M2_DATA2_FORMAL_CU_{int(year)}"
        self.registry_hash = content_id({
            "registry_id": self.registry_id,
            "reference_period": f"{year}-H1",
            "scales": self._scales,
        })
        self.final_test_access_count = 0

    def scale(self, component: str) -> float:
        return self._scales[component]


def build_year_service(year: int, bundle: Mapping[str, Any],
                       bindings: Mapping[str, ConsequenceReferenceBinding],
                       ) -> M2ConsequenceService:
    """Canonical M2ConsequenceService over one year's bindings.

    Corrections applied: ``build_node_binding`` (a standalone function in
    validation/v2_phase5/common.py) produces every per-node binding FIRST;
    the service is constructed afterwards.  No
    ``service.build_node_binding``-style call exists anywhere.
    """

    adapter = YearFormalCURegistryAdapter(year, bundle["scales"])
    return M2ConsequenceService(adapter, bindings)


def reference_bundle_object(bundle: Mapping[str, Any]):
    return load_data2_reference_bundle(bundle["payloads"])


def service_from_pass(year: int, pass_dir: Path,
                      bundle: Mapping[str, Any]) -> M2ConsequenceService:
    """Rebuild the year service from a pass's persisted bindings (offline)."""

    payload = json.loads((Path(pass_dir) / BINDINGS_NAME).read_text("utf-8"))
    bindings = {
        node_id: ConsequenceReferenceBinding.model_validate(record)
        for node_id, record in payload.get("bindings", {}).items()
    }
    return build_year_service(year, bundle, bindings)


def floor_comparison(year: int, *, ref_pass_dir: Path, comp_pass_dir: Path,
                     service: M2ConsequenceService, headroom: HeadroomSummary,
                     protocol: Mapping[str, Any], scales: Mapping[str, float],
                     setting: str) -> dict[str, Any]:
    """Point-estimate replica comparison for the determinism floor.

    The floor rule needs |metric(r1) - metric(r2)| per binding metric; no
    bootstrap and no stability conclusion is produced here.
    """

    ref_rows = read_node_frame(ref_pass_dir)
    comp_rows = read_node_frame(comp_pass_dir)
    ref_stage1 = stage1_evaluate(ref_rows, cohort_id=f"FLOOR_REF_{setting}")
    comp_stage1 = stage1_evaluate(comp_rows, cohort_id=f"FLOOR_COMP_{setting}")
    ref_shortlists = {stage: info["shortlist"]
                      for stage, info in ref_stage1["per_stage"].items() if info}
    comp_shortlists = {stage: info["shortlist"]
                       for stage, info in comp_stage1["per_stage"].items() if info}
    union = _stage2_union(ref_rows, ref_shortlists, comp_shortlists)
    ref_stage2 = stage2_solve_nodes(
        year, pass_dir=ref_pass_dir, node_ids=union, service=service,
        headroom=headroom, want_curves=True)
    comp_nodes = sorted({node for nodes in comp_shortlists.values()
                         for node in nodes} & set(union))
    comp_stage2 = stage2_solve_nodes(
        year, pass_dir=comp_pass_dir, node_ids=comp_nodes, service=service,
        headroom=headroom)
    tables = _stage_tables(ref_rows, comp_rows, intersection_only=True)
    stage2_rank = {node: int(next(row["episode_rank"] for row in ref_rows
                                  if str(row["node_id"]) == node))
                   for node in union}
    point, extras = _comparison_point_metrics(
        ref_rows=ref_rows, comp_rows=comp_rows,
        ref_stage1=ref_stage1, comp_stage1=comp_stage1, tables=tables,
        stage2={"cohort": union, "decisions_ref": ref_stage2["decisions"],
                "decisions_comp": comp_stage2["decisions"],
                "curves": ref_stage2["curves"], "episode_rank": stage2_rank},
        ref_shortlists=ref_shortlists, comp_shortlists=comp_shortlists,
        scales=scales, protocol=protocol, nested=False, n_prefix=None)
    floors = {}
    for name, record in point.items():
        if record.get("delta") is None:
            continue
        floors[name] = {
            "floor": abs(float(record["delta"])),
            "band": BINDING_METRICS[record["metric"]],
            "band_half_width": band_half_width(
                protocol, BINDING_METRICS[record["metric"]]),
        }
    payload = {
        "schema_version": "M5B_FLOOR_SETTING_V1",
        "year": year,
        "setting": setting,
        "floors": floors,
        "extras": _jsonable(extras),
        "analysis_layer": "TRAINING_NONDETERMINISM_FLOOR_ONLY",
        "final_test_access_count": 0,
    }
    payload["artifact_hash"] = sha256_json(
        {key: value for key, value in payload.items() if key != "artifact_hash"})
    return payload


# --------------------------------------------------------------------------- #
# PRE-state helpers + deterministic node iteration
# --------------------------------------------------------------------------- #

def _schedule_sobt_minutes(state) -> float:
    schedule = state.successor_state.get("schedule_reference")
    value = None if schedule is None else schedule.value
    scheduled = None if not isinstance(value, dict) else value.get(
        "scheduled_departure_utc")
    if scheduled is None:
        raise ConsequenceInterfaceError(
            "M5B_SCHEDULED_DEPARTURE_MISSING:"
            f"{state.decision_node.decision_node_id}")
    decision_time = state.decision_node.decision_time
    if isinstance(scheduled, str):
        scheduled = datetime.fromisoformat(scheduled)
    return float((scheduled - decision_time).total_seconds() / 60.0)


def route_destination(state) -> str:
    from exp.exp2.development_inputs import _destination
    return _destination(state)


def _load_year_references(year: int):
    from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
    from model.PRE.reference.turnaround_data2 import (
        data2_turnaround_reference_from_payload,
    )
    root = PRE_ROOT / str(year)
    taxi = data2_taxi_reference_from_payload(json.loads(
        (root / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json").read_text("utf-8")))
    turnaround = data2_turnaround_reference_from_payload(json.loads(
        (root / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json").read_text("utf-8")))
    return taxi, turnaround


def _abstaining_consequence_set(state_set: StateScenarioSet, *,
                                registry_id: str, registry_hash: str):
    return ConsequenceScenarioSet(
        episode_id=state_set.episode_id,
        chain_id=state_set.chain_id,
        node_id=state_set.node_id,
        stage=state_set.stage,
        representation=state_set.representation,
        registry_id=registry_id,
        registry_hash=registry_hash,
        scenarios=tuple(
            state_scenario_from_coordinates(
                scenario_id=scenario.scenario_id,
                scenario_weight=scenario.scenario_weight,
                stage=scenario.stage,
                t_ib_minutes=None, d_ob_minutes=None, d_tx_minutes=None,
                d_to_minutes=None, support=SupportState.ABSTAIN,
            )
            for scenario in state_set.scenarios
        ),
        support=SupportState.SUPPORTED,
    )


def _iter_active_nodes(cohorts, taxi) -> Iterator[tuple[int, Any, Any, Any]]:
    """Yield (episode_rank, prepared, node, prefix) deterministically.

    ``episode_rank`` is the position of the episode in the caller's rank-ordered
    case list; the nested-prefix logic (D_N subset D_4096) is defined on it.
    """

    for episode_rank, prepared in enumerate(cohorts.development):
        lookup = taxi.lookup(prepared.episode.connection_airport_id)
        reference_minutes = None
        reference_id = None
        if (getattr(lookup, "value", None) is not None
                and getattr(getattr(lookup, "support_state", None),
                            "value", None) == "SUPPORTED"):
            reference_minutes = float(lookup.value)
            reference_id = taxi.reference_id
        from model.M1.coverage import active_node_prefixes
        for node, prefix, _labels in active_node_prefixes(
                episode=prepared.episode, nodes=prepared.nodes,
                states=prepared.states,
                successor_schedule=prepared.successor_schedule,
                predecessor_outcome=prepared.predecessor_outcome,
                successor_outcome=prepared.successor_outcome,
                taxi_reference_minutes=reference_minutes,
                taxi_reference_id=reference_id,
                taxi_reference_hash=taxi.manifest_freeze_id):
            yield episode_rank, prepared, node, prefix


# --------------------------------------------------------------------------- #
# evaluation pass: one model x one fixed development case set
# --------------------------------------------------------------------------- #

def evaluate_model_on_cases(
    year: int,
    checkpoint: Path,
    ranked_dev_episodes: Sequence[tuple[int, Any]],
    *,
    scientific: Any,
    out_dir: Path,
    pass_id: str,
) -> dict[str, Any]:
    """Evaluate one M1 checkpoint on a fixed, rank-ordered development case set.

    ``ranked_dev_episodes`` is a list of ``(rank, EpisodeRecord)`` in the frozen
    hash-rank order; ``rank`` is the nested-prefix rank.  Phases: (1) per-node
    reference bindings (canonical ``build_node_binding``); (2) per-node scenario
    sampling + consequence/support frames (canonical M2ConsequenceService path);
    (3) artifacts (node frame, scenario shards, bindings, manifest).
    Stage-I/Stage-II run offline from these artifacts so memory stays bounded.
    """

    import torch
    from exp.exp2.development_inputs import (
        TAIL_MANIFEST, _observed, load_tail_continuations,
    )
    from model.M1.data import encode_pre_sequence
    from model.M1.pipeline import M1Pipeline
    from model.PRE.cohort import split_for_date_multiyear
    from model.PRE.development import materialize_preselected_cohorts

    started = time.perf_counter()
    out_dir = Path(out_dir)
    manifest_path = out_dir / PASS_MANIFEST_NAME
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text("utf-8"))
        if manifest.get("status") == "PASS" and manifest.get("pass_id") == pass_id:
            log(f"pass {pass_id}: reused ({manifest['node_count']} nodes)")
            return manifest
        raise M5BBlockedError(f"M5B_PASS_DIR_INCONSISTENT:{out_dir}")

    taxi, turnaround = _load_year_references(year)
    bundle = load_year_m2_bundle(year)
    bundle_object = reference_bundle_object(bundle)
    headroom = year_headroom_summary(year)
    shards_dir = out_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    # ``rank`` in the JSONL is the sha256 hex token; the nested-prefix rank is
    # the record's POSITION in the caller's rank-ordered (lexicographic) list.
    rank_of = {record.episode_id: position
               for position, (_rank, record) in enumerate(ranked_dev_episodes)}

    # materialize_preselected_cohorts requires all three partition keys;
    # the evaluation pass needs only the development partition (train and
    # calibration are empty here and are never read by this pass).
    partitions = {"train": (),
                  "calibration": (),
                  "development": tuple(record for _rank, record in ranked_dev_episodes)}
    cohorts = materialize_preselected_cohorts(
        scientific, root=REPO, partitions=partitions, year=year,
        dataset_instance_id=INSTANCE_ID, split_resolver=split_for_date_multiyear,
        taxi_reference=taxi, turnaround_reference=turnaround)
    pipeline = M1Pipeline.load(checkpoint)
    tails = load_tail_continuations(
        REPO / "artifacts" / "diagnostics" / "m1_positive_tail_continuation_v1"
        / "M1_POSITIVE_TAIL_CONTINUATION_V1.json")
    pipeline.tail_continuations = dict(tails)

    # ---- phase 1: canonical per-node reference bindings ------------------- #
    bindings: dict[str, ConsequenceReferenceBinding] = {}
    node_meta: dict[str, dict[str, Any]] = {}
    for episode_rank, prepared, node, prefix in _iter_active_nodes(cohorts, taxi):
        node_id = node.decision_node_id
        if node.episode_id != prepared.episode.episode_id:
            raise ConsequenceInterfaceError(
                f"M5B_EPISODE_IDENTITY_MISMATCH:{node.episode_id}/"
                f"{prepared.episode.episode_id}")
        chain_id = chain_id_for_episode(prepared.episode)
        resolved = build_node_binding(
            node_id=node_id,
            episode_id=node.episode_id,
            chain_id=chain_id,
            connection_airport_id=prepared.episode.connection_airport_id,
            destination_airport_id=route_destination(prefix[-1]),
            decision_time=node.decision_time,
            bundle=bundle_object,
        )
        if resolved.binding is not None:
            bindings[node_id] = resolved.binding
        node_meta[node_id] = {
            "episode_rank": episode_rank,
            "chain_id": chain_id,
            "decision_time": node.decision_time.isoformat(),
            "sobt_minutes": _schedule_sobt_minutes(prefix[-1]),
            "binding_status": resolved.audit.get("status"),
        }
    if not node_meta:
        raise ConsequenceInterfaceError(f"M5B_NO_ACTIVE_DEV_NODES:{year}")
    service = build_year_service(year, bundle, bindings)
    write_json_atomic(out_dir / BINDINGS_NAME, {
        "year": year,
        "registry_id": service.registry_id,
        "registry_hash": service.registry_hash,
        "bound_node_count": len(bindings),
        "node_count": len(node_meta),
        "unsupported_node_count": len(node_meta) - len(bindings),
        "bindings": {node_id: binding.model_dump(mode="json")
                     for node_id, binding in sorted(bindings.items())},
    })

    # ---- phase 2: sampling + canonical consequence/support frames --------- #
    node_frame_path = out_dir / NODE_FRAME_NAME
    if node_frame_path.exists():
        node_frame_path.unlink()
    shard_index: list[dict[str, Any]] = []
    shard_blocks: list[dict[str, Any]] = []
    shard_rows: list[dict[str, Any]] = []
    shards_dir.mkdir(parents=True, exist_ok=True)

    def _flush_shard() -> None:
        if not shard_rows:
            return
        arrays = _pack_shard(shard_rows, shard_blocks)
        shard_name = f"shard_{len(shard_index):05d}.npz"
        np.savez_compressed(shards_dir / shard_name, **arrays)
        shard_index.append({
            "shard": shard_name,
            "nodes": len(shard_rows),
            "hash": file_hash(shards_dir / shard_name),
        })
        shard_blocks.clear()
        shard_rows.clear()

    node_count = 0
    for episode_rank, prepared, node, prefix in _iter_active_nodes(cohorts, taxi):
        node_id = node.decision_node_id
        meta = node_meta[node_id]
        state = prefix[-1]
        values = encode_pre_sequence(prefix, pipeline.normalization)
        from exp.exp2.development_inputs import _observed as _observed_fn
        scenarios = pipeline.sample_from_pre(
            state,
            values.unsqueeze(0),
            torch.tensor([len(values)]),
            observed=_observed_fn(state, taxi),
            count=SCENARIO_COUNT,
            seed=TRAIN_SEED,
            taxi_reference=taxi,
            tail_continuations=tails,
        )
        state_set = state_set_from_m1_scenarios(
            scenarios,
            episode_id=node.episode_id,
            chain_id=meta["chain_id"],
            node_id=node_id,
            stage=node.operational_stage,
            representation=HISTORY_JOINT_SPEC,
        )
        if node_id in bindings:
            consequences = consequence_set(service, state_set)
        else:
            consequences = _abstaining_consequence_set(
                state_set,
                registry_id=service.registry_id,
                registry_hash=service.registry_hash,
            )
        support = comparison_support_for(state_set, consequences)
        row = {
            "node_id": node_id,
            "episode_id": node.episode_id,
            "episode_rank": meta["episode_rank"],
            "chain_id": meta["chain_id"],
            "stage": node.operational_stage.value,
            "decision_time": meta["decision_time"],
            "sobt_minutes": meta["sobt_minutes"],
            "binding_status": meta["binding_status"],
            "supported_mass": float(support.supported_mass),
            "support_threshold": float(support.threshold),
            "eligible": bool(support.included),
            "scenario_count": len(state_set.scenarios),
        }
        if support.included:
            expected = expected_cu_for_support(consequences, support)
            delay_signal = delay_priority_signal(state_set, support)
            row["p_c"] = float(phi_c(expected))
            row["p_d"] = (None if delay_signal.score is None
                          else float(delay_signal.score))
            row["Z"] = {component: float(expected[component])
                        for component in COMPONENTS}
            row["domain"] = {
                "F": (row["Z"]["F_continuity"] + row["Z"]["F_execution"]
                      + row["Z"]["F_propagation"]) / 3.0,
                "P": (row["Z"]["P_time"] + row["Z"]["P_itinerary"]
                      + row["Z"]["P_service"]) / 3.0,
                "R": row["Z"]["R_operating"],
            }
            row["support_full"] = abs(float(support.supported_mass) - 1.0) <= 1e-9
        else:
            row.update({"p_c": None, "p_d": None, "Z": None,
                        "domain": None, "support_full": False})
        append_jsonl(node_frame_path, row)
        if int(row["episode_rank"]) != int(episode_rank):
            raise ConsequenceInterfaceError(
                f"M5B_EPISODE_RANK_DRIFT:{node_id}")
        shard_blocks.append(_scenario_arrays(state_set))
        shard_rows.append(row)
        if len(shard_rows) >= SHARD_EPISODES:
            _flush_shard()
        node_count += 1
    _flush_shard()

    # ---- phase 3: manifest ------------------------------------------------ #
    seconds = time.perf_counter() - started
    provenance = git_provenance()
    manifest = {
        "schema_version": "M5B_EVAL_PASS_V1",
        "status": "PASS",
        "pass_id": pass_id,
        "year": year,
        "checkpoint": str(checkpoint),
        "checkpoint_hash": file_hash(checkpoint),
        "case_count": len(cohorts.development),
        "node_count": node_count,
        "bound_node_count": len(bindings),
        "evaluation_E": len(cohorts.development),
        "shards": shard_index,
        "scenario_count": SCENARIO_COUNT,
        "sampling_seed": TRAIN_SEED,
        "representation": HISTORY_JOINT,
        "registry_id": service.registry_id,
        "registry_hash": service.registry_hash,
        "bundle_hash": bundle["bundle_hash"],
        "headroom_summary_hash": sha256_json(headroom.model_dump(mode="json")),
        "analysis_layer": "CONSEQUENCE_FRAMES_ONLY",
        "final_test_access_count": 0,
        "seconds": round(seconds, 1),
        "git_head": provenance["git_head"],
        "git_branch": provenance["git_branch"],
        "source_script_hashes": source_script_hashes(),
        "artifact_hash": None,
    }
    manifest["artifact_hash"] = sha256_json(
        {key: value for key, value in manifest.items() if key != "artifact_hash"})
    write_json_atomic(manifest_path, manifest)
    log(f"pass {pass_id}: {node_count} nodes in {seconds:.0f}s")
    return manifest


def _scenario_arrays(state_set: StateScenarioSet) -> dict[str, Any]:
    count = len(state_set.scenarios)
    coords = np.empty((count, 4), dtype=np.float64)
    tx_ref = np.empty(count, dtype=np.float64)
    weights = np.empty(count, dtype=np.float64)
    ids = np.empty(count, dtype=np.int64)
    codes = np.empty(count, dtype=np.int8)
    observed = np.empty((count, 3), dtype=bool)
    for position, scenario in enumerate(state_set.scenarios):
        coords[position] = (
            float("nan") if scenario.t_ib_minutes is None else scenario.t_ib_minutes,
            float("nan") if scenario.d_ob_minutes is None else scenario.d_ob_minutes,
            float("nan") if scenario.d_tx_minutes is None else scenario.d_tx_minutes,
            float("nan") if scenario.d_to_minutes is None else scenario.d_to_minutes,
        )
        tx_ref[position] = (float("nan") if scenario.tx_reference_minutes is None
                            else scenario.tx_reference_minutes)
        weights[position] = scenario.scenario_weight
        ids[position] = scenario.scenario_id
        codes[position] = SUPPORT_CODE[scenario.support]
        observed[position] = (scenario.ib_observed, scenario.ob_observed,
                              scenario.tx_observed)
    return {
        "coords": coords, "tx_ref": tx_ref, "weights": weights,
        "scenario_ids": ids, "support_codes": codes, "observed": observed,
    }


def _pack_shard(node_rows: Sequence[Mapping[str, Any]],
                scenario_blocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    node_count = len(node_rows)
    offsets = np.zeros(node_count + 1, dtype=np.int64)
    for index, block in enumerate(scenario_blocks):
        offsets[index + 1] = offsets[index] + len(block["scenario_ids"])
    return {
        "node_offsets": offsets,
        "scenario_ids": np.concatenate([b["scenario_ids"] for b in scenario_blocks]),
        "weights": np.concatenate([b["weights"] for b in scenario_blocks]),
        "coords": np.concatenate([b["coords"] for b in scenario_blocks]),
        "tx_ref": np.concatenate([b["tx_ref"] for b in scenario_blocks]),
        "support_codes": np.concatenate([b["support_codes"] for b in scenario_blocks]),
        "observed": np.concatenate([b["observed"] for b in scenario_blocks]),
        "node_ids": np.asarray([row["node_id"] for row in node_rows]),
        "episode_ids": np.asarray([row["episode_id"] for row in node_rows]),
        "episode_ranks": np.asarray([row["episode_rank"] for row in node_rows],
                                    dtype=np.int64),
        "chain_ids": np.asarray([row["chain_id"] for row in node_rows]),
        "stages": np.asarray([row["stage"] for row in node_rows]),
        "sobt_minutes": np.asarray([row["sobt_minutes"] for row in node_rows],
                                   dtype=np.float64),
    }


def load_node_scenarios(pass_dir: Path,
                        node_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Reconstruct per-node scenario blocks from a pass's shards (offline)."""

    manifest = json.loads((pass_dir / PASS_MANIFEST_NAME).read_text("utf-8"))
    wanted = set(node_ids)
    output: dict[str, dict[str, Any]] = {}
    for shard_info in manifest["shards"]:
        with np.load(pass_dir / "shards" / shard_info["shard"],
                     allow_pickle=False) as data:
            shard_node_ids = [str(value) for value in data["node_ids"]]
            hits = [position for position, node_id in enumerate(shard_node_ids)
                    if node_id in wanted and node_id not in output]
            if not hits:
                continue
            offsets = data["node_offsets"]
            for position in hits:
                node_id = shard_node_ids[position]
                start, end = int(offsets[position]), int(offsets[position + 1])
                output[node_id] = {
                    "node_id": node_id,
                    "episode_id": str(data["episode_ids"][position]),
                    "episode_rank": int(data["episode_ranks"][position]),
                    "chain_id": str(data["chain_ids"][position]),
                    "stage": str(data["stages"][position]),
                    "sobt_minutes": float(data["sobt_minutes"][position]),
                    "scenario_ids": data["scenario_ids"][start:end].astype(int),
                    "weights": data["weights"][start:end].astype(float),
                    "coords": data["coords"][start:end],
                    "tx_ref": data["tx_ref"][start:end],
                    "support_codes": data["support_codes"][start:end],
                    "observed": data["observed"][start:end],
                }
                if len(output) == len(wanted):
                    return output
    missing = sorted(wanted - set(output))
    if missing:
        raise ConsequenceInterfaceError(
            f"M5B_SCENARIO_SHARD_MISSING:{len(missing)}:{missing[:3]}")
    return output


def rebuild_state_set(block: Mapping[str, Any]) -> StateScenarioSet:
    """Rebuild one node's HISTORY_JOINT StateScenarioSet from shard arrays."""

    coords = block["coords"]
    codes = block["support_codes"]
    scenarios = []
    for position in range(len(block["scenario_ids"])):
        support = SUPPORT_FROM_CODE[int(codes[position])]
        supported = support is not SupportState.ABSTAIN
        t_ib = float(coords[position][0])
        d_ob = float(coords[position][1])
        d_tx = float(coords[position][2])
        d_to = float(coords[position][3])
        scenarios.append(state_scenario_from_coordinates(
            scenario_id=int(block["scenario_ids"][position]),
            scenario_weight=float(block["weights"][position]),
            stage=OperationalStage(str(block["stage"])),
            t_ib_minutes=t_ib if supported else None,
            d_ob_minutes=d_ob if supported else None,
            d_tx_minutes=d_tx if supported else None,
            d_to_minutes=d_to if supported else None,
            support=support,
            tx_reference_minutes=(None if np.isnan(block["tx_ref"][position])
                                  else float(block["tx_ref"][position])),
            ib_observed=bool(block["observed"][position][0]),
            ob_observed=bool(block["observed"][position][1]),
            tx_observed=bool(block["observed"][position][2]),
        ))
    return StateScenarioSet(
        episode_id=str(block["episode_id"]),
        chain_id=str(block["chain_id"]),
        node_id=str(block["node_id"]),
        stage=OperationalStage(str(block["stage"])),
        representation=HISTORY_JOINT_SPEC,
        scenarios=tuple(scenarios),
    )


# --------------------------------------------------------------------------- #
# Stage-I (canonical) over a pass's node frame
# --------------------------------------------------------------------------- #

def read_node_frame(pass_dir: Path) -> list[dict[str, Any]]:
    rows = []
    with (pass_dir / NODE_FRAME_NAME).open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


def _priority_signal(row: Mapping[str, Any], *, signal_type: SignalKind,
                     score: float) -> PrioritySignal:
    return PrioritySignal(
        signal_type=signal_type,
        episode_id=str(row["episode_id"]),
        chain_id=str(row["chain_id"]),
        node_id=str(row["node_id"]),
        representation_id=f"M5B:{HISTORY_JOINT}",
        score=float(score),
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=float(row["supported_mass"]),
        comparison_support_threshold=float(row["support_threshold"]),
    )


def _stage_rows(node_rows: Sequence[Mapping[str, Any]],
                stage_value: str) -> list[Mapping[str, Any]]:
    return [row for row in node_rows
            if row["stage"] == stage_value and row.get("eligible")
            and row.get("p_c") is not None and row.get("p_d") is not None]


def stage1_evaluate(node_rows: Sequence[Mapping[str, Any]], *,
                    cohort_id: str) -> dict[str, Any]:
    """Canonical Stage-I per actionable stage + L_att (consequence vs delay)."""

    per_stage: dict[str, Any] = {}
    evaluations = []
    for stage in STAGE1_ACTIONABLE_STAGES:
        stage_value = stage.value
        rows = _stage_rows(node_rows, stage_value)
        if not rows:
            per_stage[stage_value] = None
            continue
        delay_signals = [_priority_signal(row, signal_type=SignalKind.DELAY,
                                          score=row["p_d"]) for row in rows]
        consequence_signals = [
            _priority_signal(row, signal_type=SignalKind.CONSEQUENCE,
                             score=row["p_c"]) for row in rows]
        delay_decision, consequence_decision = select_paired_attention(
            delay_signals, consequence_signals, q=NOMINAL_Q)
        priorities = {str(row["node_id"]): float(row["p_c"]) for row in rows}
        domains = {str(row["node_id"]): {key: float(value)
                                         for key, value in row["domain"].items()}
                   for row in rows}
        evaluation = evaluate_attention_allocation(
            cohort_id=f"{cohort_id}:{stage_value}",
            reference_id="M5B_CONSEQUENCE",
            comparator_id="M5B_DELAY",
            reference_decision=consequence_decision,
            comparator_decision=delay_decision,
            reference_priority=priorities,
            reference_domain_scores=domains,
        )
        evaluations.append(evaluation)
        per_stage[stage_value] = {
            "stage": stage_value,
            "cohort_size": int(consequence_decision.cohort_size),
            "k": int(consequence_decision.k),
            "shortlist": [entry.node_id for entry
                          in consequence_decision.entries if entry.selected],
            "delay_shortlist": [entry.node_id for entry
                                in delay_decision.entries if entry.selected],
            "l_att": evaluation.L_att,
            "kendall_tau_b": evaluation.kendall_tau,
            "ranking_at_k": evaluation.diagnostics.get("overlap_fraction_of_reference"),
            "evaluation": evaluation.model_dump(mode="json"),
        }
    combined = None
    if evaluations:
        aggregated = aggregate_attention_evaluations(evaluations)
        combined = {"l_att": aggregated.L_att,
                    "value_status": aggregated.value_status.value}
    return {"per_stage": per_stage, "combined": combined}


def stage1_shortlists(node_rows: Sequence[Mapping[str, Any]], *,
                      cohort_id: str) -> dict[str, list[str]]:
    result = stage1_evaluate(node_rows, cohort_id=cohort_id)
    return {stage: (info["shortlist"] if info else [])
            for stage, info in result["per_stage"].items()}


def project_shortlist_onto_queue(shortlist: Sequence[str],
                                 queue_rows: Sequence[Mapping[str, Any]], *,
                                 q: float) -> AttentionDecision:
    """Project a smaller-cohort shortlist onto the reference candidate queue.

    M4 requires both decisions to cover the same candidate queue; the
    comparator decision re-ranks the reference queue with the SAME P^C scores
    (one fixed model) and selects exactly the projected shortlist members.
    """

    shortlist_set = set(shortlist)
    ranked = sorted(queue_rows,
                    key=lambda row: (-float(row["p_c"]), str(row["episode_id"]),
                                     str(row["node_id"])))
    entries = tuple(
        AttentionEntry(
            episode_id=str(row["episode_id"]),
            chain_id=str(row["chain_id"]),
            node_id=str(row["node_id"]),
            score=float(row["p_c"]),
            rank=rank,
            selected=str(row["node_id"]) in shortlist_set,
            selected_for=SignalKind.CONSEQUENCE,
        )
        for rank, row in enumerate(ranked, start=1)
    )
    return AttentionDecision(
        signal_type=SignalKind.CONSEQUENCE,
        q=float(q), k=len(shortlist_set), cohort_size=len(ranked),
        entries=entries, status=TypedStatus.SUPPORTED,
    )


# --------------------------------------------------------------------------- #
# Stage-II (canonical exact enumeration, offline from shards)
# --------------------------------------------------------------------------- #

def stage2_solve_nodes(year: int, *, pass_dir: Path, node_ids: Sequence[str],
                       service: M2ConsequenceService,
                       headroom: HeadroomSummary,
                       want_curves: bool = False) -> dict[str, Any]:
    """``solve_recovery`` + optional objective curves for the requested nodes."""

    blocks = load_node_scenarios(pass_dir, node_ids)
    decisions: dict[str, Any] = {}
    curves: dict[str, dict[str, float]] = {}
    grid = action_grid(headroom.u_max, floor_to_minutes=FLOOR_TO_MINUTES)
    for node_id in node_ids:
        block = blocks[node_id]
        stage = OperationalStage(str(block["stage"]))
        if not is_actionable(stage):
            decisions[node_id] = {
                "node_id": node_id, "stage": block["stage"],
                "actionable_status": TypedStatus.NOT_ACTIONABLE.value,
                "u_star": 0.0, "j_zero": None, "j_star": None,
                "recoverable_value": None, "episode_rank": block["episode_rank"],
            }
            continue
        state_set = rebuild_state_set(block)
        if not all(scenario.support is not SupportState.ABSTAIN
                   for scenario in state_set.scenarios):
            decisions[node_id] = {
                "node_id": node_id, "stage": block["stage"],
                "actionable_status": "TYPED_UNSUPPORTED_STATE",
                "u_star": 0.0, "j_zero": None, "j_star": None,
                "recoverable_value": None, "episode_rank": block["episode_rank"],
            }
            continue
        context = TransitionContext(
            sobt_minutes=float(block["sobt_minutes"]),
            turnaround_lower_bound_minutes=float(headroom.turnaround_lower_bound_q),
        )
        decision = solve_recovery(
            state_set, context=context, service=service,
            headroom_summary=headroom)
        decisions[node_id] = {
            "node_id": node_id,
            "episode_id": block["episode_id"],
            "episode_rank": block["episode_rank"],
            "stage": block["stage"],
            "actionable_status": decision.actionable_status.value,
            "solver_status": decision.solver_status.value,
            "u_star": float(decision.u_star),
            "u_max": float(decision.u_max),
            "j_zero": (None if decision.j_zero is None else float(decision.j_zero)),
            "j_star": (None if decision.j_star is None else float(decision.j_star)),
            "recoverable_value": (None if decision.recoverable_value is None
                                  else float(decision.recoverable_value)),
        }
        if want_curves:
            curves[node_id] = {
                f"{float(u):.1f}": float(expected_objective(
                    state_set, context=context, service=service, u=float(u),
                    u_max=float(headroom.u_max),
                    lambda_policy=LAMBDA_NOMINAL,
                    view=PRIMARY_AGGREGATION_VIEW))
                for u in grid
            }
    output: dict[str, Any] = {"decisions": decisions, "action_grid": [float(u) for u in grid]}
    if want_curves:
        output["curves"] = curves
    return output


# --------------------------------------------------------------------------- #
# ranking / component metrics (vectorized frozen rules)
# --------------------------------------------------------------------------- #

def kendall_tau_b(scores_a: Mapping[str, float],
                  scores_b: Mapping[str, float]) -> float | None:
    from scipy import stats
    keys = sorted(set(scores_a) & set(scores_b))
    if len(keys) < 2:
        return None
    vector_a = np.asarray([scores_a[key] for key in keys], dtype=float)
    vector_b = np.asarray([scores_b[key] for key in keys], dtype=float)
    if np.ptp(vector_a) <= 0.0 or np.ptp(vector_b) <= 0.0:
        return None
    value = stats.kendalltau(vector_a, vector_b).statistic
    return None if not np.isfinite(value) else float(value)


def _decile_positions(scores: Mapping[str, float]) -> dict[str, int]:
    keys = sorted(scores)
    ordered = sorted(keys, key=lambda key: (-scores[key], key))
    step = max(1, len(ordered) // 10)
    return {key: min(9, position // step)
            for position, key in enumerate(ordered)}


def large_decile_displacement_rate(scores_a: Mapping[str, float],
                                   scores_b: Mapping[str, float]) -> float | None:
    keys = sorted(set(scores_a) & set(scores_b))
    if len(keys) < 20:
        return None
    deciles_a = _decile_positions({key: scores_a[key] for key in keys})
    deciles_b = _decile_positions({key: scores_b[key] for key in keys})
    displaced = sum(1 for key in keys
                    if abs(deciles_a[key] - deciles_b[key]) >= 3)
    return displaced / len(keys)


def topk_overlap(scores_a: Mapping[str, float], scores_b: Mapping[str, float],
                 *, k: int | None = None,
                 denominator: str = "k") -> float | None:
    keys = sorted(set(scores_a) & set(scores_b))
    if not keys:
        return None
    if k is None:
        k = attention_capacity_k(NOMINAL_Q, len(keys))
    k = max(1, min(int(k), len(keys)))
    top_a = set(sorted(keys, key=lambda key: (-scores_a[key], key))[:k])
    top_b = set(sorted(keys, key=lambda key: (-scores_b[key], key))[:k])
    if denominator == "k":
        return len(top_a & top_b) / k
    return len(top_a & top_b) / max(1, len(top_b))


def contrast_tau(node_rows: Sequence[Mapping[str, Any]]) -> float | None:
    """tau(P^C ranking, P^D ranking) within one cohort (canonical contrast)."""

    scores_c = {str(row["node_id"]): float(row["p_c"]) for row in node_rows
                if row.get("p_c") is not None}
    scores_d = {str(row["node_id"]): float(row["p_d"]) for row in node_rows
                if row.get("p_d") is not None}
    return kendall_tau_b(scores_c, scores_d)


def contrast_ranking_at_k(node_rows: Sequence[Mapping[str, Any]]) -> float | None:
    scores_c = {str(row["node_id"]): float(row["p_c"]) for row in node_rows
                if row.get("p_c") is not None}
    scores_d = {str(row["node_id"]): float(row["p_d"]) for row in node_rows
                if row.get("p_d") is not None}
    keys = sorted(set(scores_c) & set(scores_d))
    if len(keys) < 2:
        return None
    return topk_overlap(scores_c, scores_d)


def scale_normalized_delta(value: float, reference: float, *,
                           floor: float) -> float:
    denominator = max(float(floor), abs(float(reference)))
    if denominator <= 0.0:
        return float("inf")
    return abs(float(value) - float(reference)) / denominator


# --------------------------------------------------------------------------- #
# bootstrap episode draws (frozen seed/replicates)
# --------------------------------------------------------------------------- #

def episode_draws(episode_ranks: Sequence[int], *, replicates: int,
                  seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ranks = np.asarray(list(episode_ranks), dtype=np.int64)
    return rng.choice(ranks, size=(replicates, len(ranks)), replace=True)


def _draw_counts(draw: np.ndarray) -> dict[int, int]:
    unique, counts = np.unique(draw, return_counts=True)
    return {int(rank): int(count) for rank, count in zip(unique, counts)}


def _canonical_topk(scores: Mapping[str, float], episode_of: Mapping[str, str],
                    k: int) -> set[str]:
    """Vectorized application of the frozen STAGE_I_TIE_BREAK rule.

    Ordering ``(-score, episode_id, node_id)`` via numpy lexsort with the
    canonical ``attention_capacity_k``; identical to ``select_attention``.
    """

    if k <= 0 or not scores:
        return set()
    keys = list(scores)
    order = np.lexsort((
        np.asarray([str(key) for key in keys]),
        np.asarray([str(episode_of.get(key, "")) for key in keys]),
        -np.asarray([scores[key] for key in keys], dtype=float),
    ))
    return {str(keys[position]) for position in order[:min(int(k), len(keys))]}


def _jsonable(payload: Any) -> Any:
    """Strip pydantic decision objects so payloads stay JSON-serializable."""

    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()
                if not hasattr(value, "model_dump") or isinstance(value, (str, int, float, bool))}
    if isinstance(payload, (list, tuple)):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return str(payload)


# --------------------------------------------------------------------------- #
# comparison metric suite (FIT paired / EVAL nested bootstrap)
# --------------------------------------------------------------------------- #

def _stage_tables(ref_rows: Sequence[Mapping[str, Any]],
                  comp_rows: Sequence[Mapping[str, Any]],
                  *, intersection_only: bool) -> dict[str, dict[str, Any]]:
    """Per-stage aligned node arrays for the two score maps."""

    ref_by_id = {str(row["node_id"]): row for row in ref_rows}
    comp_by_id = {str(row["node_id"]): row for row in comp_rows}
    tables: dict[str, dict[str, Any]] = {}
    for stage in STAGE1_ACTIONABLE_STAGES:
        stage_value = stage.value
        ref_stage = [row for row in ref_rows
                     if row["stage"] == stage_value and row.get("eligible")
                     and row.get("p_c") is not None and row.get("p_d") is not None]
        if intersection_only:
            keys = [str(row["node_id"]) for row in ref_stage
                    if str(row["node_id"]) in comp_by_id
                    and comp_by_id[str(row["node_id"])].get("eligible")
                    and comp_by_id[str(row["node_id"])].get("p_c") is not None
                    and comp_by_id[str(row["node_id"])].get("p_d") is not None]
        else:
            keys = [str(row["node_id"]) for row in ref_stage]
        tables[stage_value] = {
            "node_ids": keys,
            "episode_id": {key: str(ref_by_id[key]["episode_id"])
                           for key in keys},
            "ref_pc": {key: float(ref_by_id[key]["p_c"]) for key in keys},
            "ref_pd": {key: float(ref_by_id[key]["p_d"]) for key in keys},
            "comp_pc": {key: float(comp_by_id[key]["p_c"]) for key in keys},
            "comp_pd": {key: float(comp_by_id[key]["p_d"]) for key in keys},
            "episode_rank": {key: int(ref_by_id[key]["episode_rank"])
                             for key in keys},
        }
    return tables


def _episode_component_means(rows: Sequence[Mapping[str, Any]]
                             ) -> dict[int, dict[str, float]]:
    totals: dict[int, dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in COMPONENTS})
    counts: dict[int, int] = defaultdict(int)
    for row in rows:
        if row.get("Z") is None:
            continue
        rank = int(row["episode_rank"])
        counts[rank] += 1
        for component in COMPONENTS:
            totals[rank][component] += float(row["Z"][component])
    return {rank: {component: totals[rank][component] / counts[rank]
                   for component in COMPONENTS}
            for rank in counts}


def _shortlist_sum(scores: Mapping[str, float], shortlist: Sequence[str]) -> float:
    return float(sum(scores[node_id] for node_id in shortlist
                     if node_id in scores))


def _l_att_pair(ref_pc: Mapping[str, float],
                ref_shortlist: Sequence[str],
                comp_shortlist: Sequence[str]) -> tuple[float, float]:
    """Canonical L_att components: (delta A, reference A*) on the reference basis."""

    reference_value = _shortlist_sum(ref_pc, ref_shortlist)
    comparator_value = _shortlist_sum(ref_pc, comp_shortlist)
    return reference_value - comparator_value, reference_value


def _l_att_from_shortlists(ref_pc: Mapping[str, float],
                           ref_shortlist: Sequence[str],
                           comp_shortlist: Sequence[str]) -> float | None:
    delta, reference_value = _l_att_pair(ref_pc, ref_shortlist, comp_shortlist)
    if reference_value <= 0.0:
        return None
    return delta / reference_value


def _comparison_point_metrics(
    *, ref_rows: Sequence[Mapping[str, Any]],
    comp_rows: Sequence[Mapping[str, Any]],
    ref_stage1: Mapping[str, Any],
    comp_stage1: Mapping[str, Any],
    tables: Mapping[str, Mapping[str, Any]],
    stage2: Mapping[str, Any],
    ref_shortlists: Mapping[str, Sequence[str]],
    comp_shortlists: Mapping[str, Sequence[str]],
    scales: Mapping[str, float],
    protocol: Mapping[str, Any],
    nested: bool,
    n_prefix: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Point estimates for every binding metric instance.

    ``nested=True`` marks the EVAL stage (two cohorts of one model);
    ``nested=False`` marks the FIT stage (two models on one case set).
    """

    metrics: dict[str, Any] = {}

    for stage_value, table in tables.items():
        ref_s1 = (ref_stage1["per_stage"].get(stage_value) or {})
        comp_s1 = (comp_stage1["per_stage"].get(stage_value) or {})
        if nested:
            ref_nodes = [row for row in ref_rows
                         if row["stage"] == stage_value and row.get("eligible")
                         and row.get("p_c") is not None]
            comp_nodes = [row for row in comp_rows
                          if row["stage"] == stage_value and row.get("eligible")
                          and row.get("p_c") is not None]
        else:
            ref_nodes = [row for row in ref_rows
                         if row["stage"] == stage_value
                         and str(row["node_id"]) in set(table["node_ids"])]
            comp_nodes = [row for row in comp_rows
                          if row["stage"] == stage_value
                          and str(row["node_id"]) in set(table["node_ids"])]
        ref_pc = {str(row["node_id"]): float(row["p_c"]) for row in ref_nodes}
        ref_pd = {str(row["node_id"]): float(row["p_d"]) for row in ref_nodes}
        comp_pc = {str(row["node_id"]): float(row["p_c"]) for row in comp_nodes}
        comp_pd = {str(row["node_id"]): float(row["p_d"]) for row in comp_nodes}
        common = sorted(set(ref_pc) & set(comp_pc))
        common_map = {key: True for key in common}

        tau_ref = contrast_tau(ref_nodes)
        tau_comp = contrast_tau(comp_nodes)
        rank_ref = contrast_ranking_at_k(ref_nodes)
        rank_comp = contrast_ranking_at_k(comp_nodes)
        k_ref = attention_capacity_k(NOMINAL_Q, len(common))
        if nested:
            ref_rank = _rank_map(ref_nodes)
            comp_rank = _rank_map(comp_nodes)
            # nested-cohort shortlist comparison: the SMALLER cohort's shortlist
            # (D_N prefix universe, K_N = ceil(0.1 * N_N)) against the reference
            # cohort's shortlist (D_4096 universe, K_ref = ceil(0.1 * N_ref)).
            # Comparing both shortlists on the prefix universe would be
            # degenerate (identical scores -> overlap 1.0 by construction).
            episode_of_ref = {str(row["node_id"]): str(row["episode_id"])
                              for row in ref_nodes}
            episode_of_comp = {str(row["node_id"]): str(row["episode_id"])
                               for row in comp_nodes}
            overlap_rate, jaccard = _shortlist_agreement(
                comp_pc, episode_of_comp, ref_pc, episode_of_ref,
                k_a=attention_capacity_k(NOMINAL_Q, len(comp_pc)),
                k_b=attention_capacity_k(NOMINAL_Q, len(ref_pc)))
            decile = _within_decile_rate(
                {key: comp_rank[key] for key in common},
                {key: ref_rank[key] for key in common},
                size_a=len(comp_rank), size_b=len(ref_rank)) \
                if len(common) >= 20 else None
        else:
            episode_of_ref = {str(row["node_id"]): str(row["episode_id"])
                              for row in ref_nodes}
            episode_of_comp = {str(row["node_id"]): str(row["episode_id"])
                               for row in comp_nodes}
            overlap_rate, jaccard = _shortlist_agreement(
                {key: comp_pc[key] for key in common}, episode_of_comp,
                {key: ref_pc[key] for key in common}, episode_of_ref,
                k_a=k_ref, k_b=k_ref)
            decile = large_decile_displacement_rate(
                {key: comp_pc[key] for key in common},
                {key: ref_pc[key] for key in common})
        ref_shortlist = list(ref_shortlists.get(stage_value, []))
        comp_shortlist = list(comp_shortlists.get(stage_value, []))
        l_att_delta, l_att_reference = _l_att_pair(
            ref_pc, ref_shortlist, comp_shortlist)
        l_att = (None if l_att_reference <= 0.0
                 else l_att_delta / l_att_reference)

        metrics[f"kendall_tau_b@{stage_value}"] = {
            "metric": "kendall_tau_b", "stage": stage_value,
            "value_ref": tau_ref, "value_comp": tau_comp,
            "delta": (None if tau_ref is None or tau_comp is None
                      else tau_comp - tau_ref),
            "event_count": len(common),
        }
        metrics[f"ranking_at_k@{stage_value}"] = {
            "metric": "ranking_at_k", "stage": stage_value,
            "value_ref": rank_ref, "value_comp": rank_comp,
            "delta": (None if rank_ref is None or rank_comp is None
                      else rank_comp - rank_ref),
            "event_count": len(common),
        }
        # the binding band top_k_overlap_abs is a DISPLACEMENT-scale band, so
        # the reported statistic is the deviation from perfect agreement,
        # |1 - shortlist overlap rate|; the rate and the Jaccard index are kept
        # alongside for audit (verified against a direct intersection count)
        metrics[f"top_k_overlap@{stage_value}"] = {
            "metric": "top_k_overlap", "stage": stage_value,
            "value_ref": None, "value_comp": None,
            "delta": (None if overlap_rate is None
                      else abs(1.0 - overlap_rate)),
            "overlap_rate": overlap_rate, "jaccard": jaccard,
            "event_count": len(common),
        }
        metrics[f"large_decile_displacement_rate@{stage_value}"] = {
            "metric": "large_decile_displacement_rate", "stage": stage_value,
            "value_ref": None, "value_comp": None, "delta": decile,
            "event_count": len(common),
        }
        metrics[f"l_att@{stage_value}"] = {
            "metric": "l_att", "stage": stage_value,
            "value_ref": ref_s1.get("l_att"), "value_comp": comp_s1.get("l_att"),
            "delta": l_att, "event_count": int(ref_s1.get("cohort_size") or 0),
            "l_att_delta": l_att_delta, "l_att_reference_value": l_att_reference,
        }

    # l_att combined = ratio of SUMMED values across stages (canonical
    # aggregation semantics: never a mean of ratios)
    stage_pairs = [(value.get("l_att_delta"), value.get("l_att_reference_value"))
                   for key, value in metrics.items() if key.startswith("l_att@")]
    total_delta = sum(delta for delta, _reference in stage_pairs
                      if delta is not None)
    total_reference = sum(reference for _delta, reference in stage_pairs
                          if reference is not None)
    metrics["l_att@combined"] = {
        "metric": "l_att", "stage": "combined",
        "value_ref": None, "value_comp": None,
        "delta": (None if total_reference <= 0.0 else total_delta / total_reference),
        "l_att_delta": total_delta, "l_att_reference_value": total_reference,
        "event_count": sum(int(value["event_count"]) for key, value
                           in metrics.items() if key.startswith("l_att@")),
    }

    # components (episode-level means over the whole case set)
    ref_means = _episode_component_means(ref_rows)
    comp_means = _episode_component_means(comp_rows)
    for component in COMPONENTS:
        values_ref = [ref_means[rank][component] for rank in sorted(ref_means)]
        values_comp = [comp_means[rank][component] for rank in sorted(comp_means)]
        value_ref = float(np.mean(values_ref)) if values_ref else None
        value_comp = float(np.mean(values_comp)) if values_comp else None
        delta = (None if value_ref is None or value_comp is None
                 else scale_normalized_delta(
                     value_comp, value_ref,
                     floor=max(_protocol_floor(protocol, component),
                               float(scales[component]))))
        metrics[f"component_{component}"] = {
            "metric": f"component_{component}", "stage": "all",
            "value_ref": value_ref, "value_comp": value_comp,
            "delta": delta,
            "event_count": min(len(values_ref), len(values_comp)),
        }

    # Stage-II decision metrics over the union cohort (canonical M4 evaluation)
    decisions_ref = stage2["decisions_ref"]
    decisions_comp = stage2["decisions_comp"]
    cohort = stage2["cohort"]
    curves = stage2.get("curves", {})
    reference_actions, comparator_actions = {}, {}
    reference_objectives: dict[tuple[str, float], float] = {}
    reference_values: dict[str, float] = {}
    for node_id in cohort:
        ref_row = decisions_ref[node_id]
        ref_u = float(ref_row["u_star"])
        reference_actions[node_id] = ref_u
        comparator_actions[node_id] = (
            float(decisions_comp[node_id]["u_star"])
            if node_id in decisions_comp else 0.0)
        curve = curves.get(node_id, {})
        for action in (ref_u, comparator_actions[node_id]):
            key = f"{action:.1f}"
            if key in curve:
                reference_objectives[(node_id, round(action, 6))] = float(curve[key])
        value = ref_row.get("recoverable_value")
        if value is not None:
            reference_values[node_id] = float(value)
    missing_objectives = [node_id for node_id in cohort
                          if (node_id, round(reference_actions[node_id], 6))
                          not in reference_objectives
                          or (node_id, round(comparator_actions[node_id], 6))
                          not in reference_objectives]
    l_rec = None
    recovery_events = {"MISSED_ACTIVATION": 0, "FALSE_ACTIVATION": 0,
                       "UNDER_RECOVERY": 0, "OVER_RECOVERY": 0}
    recovery_extras: dict[str, Any] = {}
    if missing_objectives:
        recovery_extras["typed_undefined_nodes"] = len(missing_objectives)
    if cohort and not missing_objectives:
        evaluation = evaluate_recovery_loss(
            cohort_id="M5B_UNION",
            reference_id="M5B_REFERENCE",
            comparator_id="M5B_COMPARATOR",
            fixed_cohort=tuple(cohort),
            reference_actions=reference_actions,
            comparator_actions=comparator_actions,
            reference_objectives=reference_objectives,
            reference_recoverable_values=reference_values,
        )
        recovery_events = dict(evaluation.activation_events)
        l_rec = evaluation.L_rec
        recovery_extras.update({
            "l_rec_status": evaluation.status.value,
            "total_delta_objective": evaluation.delta_recovery_objective,
            "total_reference_value": evaluation.reference_recoverable_value,
            "reference_activation_rate":
                evaluation.diagnostics["reference_activation_rate"],
            "comparator_activation_rate":
                evaluation.diagnostics["comparator_activation_rate"],
        })
    size = len(cohort)
    ref_activation = (float(np.mean([reference_actions[node] > 0.0
                                     for node in cohort])) if cohort else None)
    comp_activation = (float(np.mean([comparator_actions[node] > 0.0
                                      for node in cohort])) if cohort else None)
    metrics["activation_rate"] = {
        "metric": "activation_rate", "stage": "all",
        "value_ref": ref_activation, "value_comp": comp_activation,
        "delta": (None if ref_activation is None or comp_activation is None
                  else comp_activation - ref_activation),
        "event_count": size,
    }
    metrics["missed_activation_rate"] = {
        "metric": "missed_activation_rate", "stage": "all",
        "value_ref": None, "value_comp": None,
        "delta": (recovery_events["MISSED_ACTIVATION"] / size) if size else None,
        "event_count": size,
    }
    metrics["false_activation_rate"] = {
        "metric": "false_activation_rate", "stage": "all",
        "value_ref": None, "value_comp": None,
        "delta": (recovery_events["FALSE_ACTIVATION"] / size) if size else None,
        "event_count": size,
    }
    metrics["l_rec"] = {
        "metric": "l_rec", "stage": "all",
        "value_ref": None, "value_comp": None, "delta": l_rec,
        "event_count": size,
    }
    extras = {
        "stage2_events": recovery_events,
        "ref_actions": reference_actions,
        "comp_actions": comparator_actions,
        "cohort_size": size,
        "recovery": _jsonable(recovery_extras),
    }
    return metrics, extras


def _shortlist_agreement(scores_a: Mapping[str, float],
                         episode_of_a: Mapping[str, str],
                         scores_b: Mapping[str, float],
                         episode_of_b: Mapping[str, str], *,
                         k_a: int, k_b: int) -> tuple[float | None, float | None]:
    """(overlap rate, Jaccard) of two top-K shortlists under the frozen rule.

    Each shortlist is computed on its OWN score universe with its OWN capacity
    (FIT: two models, one case set, same K; EVAL: one model, D_N prefix with
    K_N = ceil(0.1*N_N) against the D_4096 cohort with K_ref = ceil(0.1*N_ref)).
    The overlap rate is the retention of the FIRST (smaller) shortlist,
    ``|A ∩ B| / |A|``; the Jaccard index is ``|A ∩ B| / |A ∪ B|``.  Both the
    point estimate and every bootstrap replicate use this same convention, so
    the reported CI is a CI for the reported statistic.
    """

    if not scores_a or not scores_b or k_a <= 0 or k_b <= 0:
        return None, None
    top_a = _canonical_topk(scores_a, episode_of_a, k_a)
    top_b = _canonical_topk(scores_b, episode_of_b, k_b)
    if not top_a:
        return None, None
    intersection = top_a & top_b
    union = top_a | top_b
    return (len(intersection) / len(top_a),
            (len(intersection) / len(union)) if union else None)


def _rank_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    ordered = sorted(rows, key=lambda item: (-float(item["p_c"]),
                                             str(item["node_id"])))
    return {str(row["node_id"]): float(position)
            for position, row in enumerate(ordered, start=1)}


def _within_decile_rate(ranks_a: Mapping[str, float],
                        ranks_b: Mapping[str, float], *,
                        size_a: int, size_b: int) -> float | None:
    """Decile displacement from WITHIN-cohort rank positions (nested mode).

    The rank VALUES are already within-cohort positions (rank 1 = highest
    score); the decile of a node is derived from its position and its OWN
    cohort's size.  The sizes MUST be passed explicitly because the maps are
    restricted to the common-key intersection -- deriving a cohort size from
    the restricted dict length was the exact defect that moved the point
    estimate outside its bootstrap CI.
    """

    keys = sorted(set(ranks_a) & set(ranks_b))
    if len(keys) < 20:
        return None
    step_a = max(1, int(size_a) // 10)
    step_b = max(1, int(size_b) // 10)
    displaced = 0
    for key in keys:
        decile_a = min(9, int(ranks_a[key] - 1.0) // step_a)
        decile_b = min(9, int(ranks_b[key] - 1.0) // step_b)
        if abs(decile_a - decile_b) >= 3:
            displaced += 1
    return displaced / len(keys)


def _protocol_floor(protocol: Mapping[str, Any], component: str) -> float:
    floors = protocol.get("scale_normalization", {}).get("floors", {})
    entry = floors.get(component, {})
    return float(entry.get("value", 0.0))


def _protocol_fixed_floor(protocol: Mapping[str, Any], name: str) -> float:
    floors = protocol.get("scale_normalization", {}).get("floors", {})
    entry = floors.get(name, {})
    return float(entry.get("value", 0.01))


# --------------------------------------------------------------------------- #
# bootstrap engine (episode subset draws; frozen seed/replicates)
# --------------------------------------------------------------------------- #

def _percentile_interval(values: Sequence[float]) -> list[float]:
    array = np.asarray([float(value) for value in values], dtype=float)
    return [float(np.quantile(array, 0.025)), float(np.quantile(array, 0.975))]


def _prep_stage_arrays(table: Mapping[str, Any], *, n_prefix: int | None) -> dict[str, Any]:
    node_ids = [str(key) for key in table["node_ids"]]
    order = sorted(range(len(node_ids)), key=lambda i: node_ids[i])
    node_ids = [node_ids[i] for i in order]
    return {
        "node_ids": node_ids,
        "ref_pc": np.asarray([float(table["ref_pc"][key]) for key in node_ids]),
        "ref_pd": np.asarray([float(table["ref_pd"][key]) for key in node_ids]),
        "comp_pc": np.asarray([float(table["comp_pc"][key]) for key in node_ids]),
        "comp_pd": np.asarray([float(table["comp_pd"][key]) for key in node_ids]),
        "ep_rank": np.asarray([int(table["episode_rank"][key]) for key in node_ids],
                              dtype=np.int64),
        "rank_lt_n": (None if n_prefix is None else np.asarray(
            [int(table["episode_rank"][key]) < int(n_prefix)
             for key in node_ids])),
        "episode_of": {key: str(table.get("episode_id", {}).get(key, key))
                       for key in node_ids},
    }


def _masked_maps(prep: Mapping[str, Any], mask: np.ndarray) -> tuple[dict[str, float], ...]:
    keys = [key for key, keep in zip(prep["node_ids"], mask) if keep]
    return (
        {key: float(prep["ref_pc"][position]) for position, key in enumerate(prep["node_ids"]) if keep},
        {key: float(prep["ref_pd"][position]) for position, key in enumerate(prep["node_ids"]) if keep},
        {key: float(prep["comp_pc"][position]) for position, key in enumerate(prep["node_ids"]) if keep},
        {key: float(prep["comp_pd"][position]) for position, key in enumerate(prep["node_ids"]) if keep},
    )


def _replicate_deltas(
    *, tables: Mapping[str, Mapping[str, Any]],
    ref_means: Mapping[int, Mapping[str, float]],
    comp_means: Mapping[int, Mapping[str, float]],
    stage2: Mapping[str, Any],
    draws: np.ndarray,
    nested: bool,
    n_prefix: int | None,
    scales: Mapping[str, float],
    protocol: Mapping[str, Any],
) -> dict[str, list[float | None]]:
    deltas: dict[str, list[float | None]] = defaultdict(list)
    preps = {stage: _prep_stage_arrays(table, n_prefix=n_prefix)
             for stage, table in tables.items()}
    stage2_cohort = stage2["cohort"]
    decisions_ref = stage2["decisions_ref"]
    decisions_comp = stage2["decisions_comp"]
    curves = stage2.get("curves", {})
    cohort_ep = np.asarray([int(stage2["episode_rank"][node])
                            for node in stage2_cohort], dtype=np.int64) \
        if stage2_cohort else np.empty(0, dtype=np.int64)
    ref_rank_means = {rank: {c: float(ref_means.get(rank, {}).get(c, float("nan")))
                             for c in COMPONENTS} for rank in ref_means}
    comp_rank_means = {rank: {c: float(comp_means.get(rank, {}).get(c, float("nan")))
                              for c in COMPONENTS} for rank in comp_means}

    for replicate in range(draws.shape[0]):
        counts = _draw_counts(draws[replicate])
        drawn = np.fromiter(counts.keys(), dtype=np.int64)
        replicate_latt_pairs: list[tuple[float, float]] = []
        # ---- stage-level ranking metrics ----
        for stage_value, prep in preps.items():
            mask = np.isin(prep["ep_rank"], drawn)
            idx = np.where(mask)[0]
            if idx.size < 2:
                for base in ("kendall_tau_b", "ranking_at_k", "top_k_overlap",
                             "large_decile_displacement_rate", "l_att"):
                    deltas[f"{base}@{stage_value}"].append(None)
                continue
            keys = [prep["node_ids"][position] for position in idx]
            ref_pc = {key: float(prep["ref_pc"][position])
                      for position, key in zip(idx, keys)}
            ref_pd = {key: float(prep["ref_pd"][position])
                      for position, key in zip(idx, keys)}
            comp_pc = {key: float(prep["comp_pc"][position])
                       for position, key in zip(idx, keys)}
            comp_pd = {key: float(prep["comp_pd"][position])
                       for position, key in zip(idx, keys)}
            episode_of = prep["episode_of"]
            tau_ref = kendall_tau_b(ref_pc, ref_pd)
            contrast_ref = topk_overlap(ref_pc, ref_pd)
            k = attention_capacity_k(NOMINAL_Q, len(keys))
            if nested:
                # nested cohorts: the comparator side is the D_N prefix ONLY --
                # for the shortlist metrics, the ranking contrasts and l_att --
                # exactly as in the point estimator
                keep_n = prep["rank_lt_n"][idx]
                comp_keys = [key for key, keep in zip(keys, keep_n) if keep]
                k_n = attention_capacity_k(NOMINAL_Q, len(comp_keys))
                comp_pc_n = {key: comp_pc[key] for key in comp_keys}
                comp_pd_n = {key: comp_pd[key] for key in comp_keys}
                tau_comp = kendall_tau_b(comp_pc_n, comp_pd_n)
                contrast_comp = topk_overlap(comp_pc_n, comp_pd_n)
            else:
                tau_comp = kendall_tau_b(comp_pc, comp_pd)
                contrast_comp = topk_overlap(comp_pc, comp_pd)
            deltas[f"kendall_tau_b@{stage_value}"].append(
                None if tau_ref is None or tau_comp is None else tau_comp - tau_ref)
            deltas[f"ranking_at_k@{stage_value}"].append(
                contrast_overlap(contrast_ref, contrast_comp))
            if nested:
                if comp_keys:
                    # comparator = D_N prefix at its own capacity; reference =
                    # the drawn D_4096 cohort at ITS own capacity (k), exactly
                    # as in the point estimator
                    top_n = _canonical_topk(
                        {key: comp_pc[key] for key in comp_keys}, episode_of, k_n)
                    top_ref = _canonical_topk(ref_pc, episode_of, k)
                    overlap = abs(1.0 - len(top_n & top_ref) / max(1, len(top_n)))
                else:
                    overlap = None
                decile = _within_decile_rate(
                    _rank_map_arrays(comp_pc, comp_keys),
                    _rank_map_arrays(ref_pc, keys),
                    size_a=len(comp_keys), size_b=len(keys)) \
                    if len(keys) >= 20 else None
                l_att_pair = _l_att_pair(ref_pc, list(top_ref), list(top_n))
            else:
                top_ref = _canonical_topk(ref_pc, episode_of, k)
                top_comp = _canonical_topk(comp_pc, episode_of, k)
                overlap = abs(1.0 - len(top_ref & top_comp) / max(1, k))
                decile = large_decile_displacement_rate(comp_pc, ref_pc)
                l_att_pair = _l_att_pair(ref_pc, list(top_ref), list(top_comp))
            l_att_reference = l_att_pair[1]
            deltas[f"top_k_overlap@{stage_value}"].append(overlap)
            deltas[f"large_decile_displacement_rate@{stage_value}"].append(decile)
            deltas[f"l_att@{stage_value}"].append(
                None if l_att_reference <= 0.0
                else l_att_pair[0] / l_att_reference)
            replicate_latt_pairs.append(l_att_pair)
        # stage-combined l_att replicate = ratio of SUMMED deltas over SUMMED
        # reference values across stages (canonical aggregation semantics)
        combined_delta = sum(pair[0] for pair in replicate_latt_pairs)
        combined_reference = sum(pair[1] for pair in replicate_latt_pairs)
        deltas["l_att@combined"].append(
            None if not replicate_latt_pairs or combined_reference <= 0.0
            else combined_delta / combined_reference)
        # ---- components ----
        total = float(sum(counts.values()))
        for component in COMPONENTS:
            ref_vals = [ref_rank_means[rank][component] * count
                        for rank, count in counts.items()
                        if rank in ref_rank_means
                        and np.isfinite(ref_rank_means[rank][component])]
            comp_vals = [comp_rank_means[rank][component] * count
                         for rank, count in counts.items()
                         if rank in comp_rank_means
                         and np.isfinite(comp_rank_means[rank][component])]
            weight_ref = sum(counts[rank] for rank in counts
                             if rank in ref_rank_means
                             and np.isfinite(ref_rank_means[rank][component]))
            weight_comp = sum(counts[rank] for rank in counts
                              if rank in comp_rank_means
                              and np.isfinite(comp_rank_means[rank][component]))
            if not weight_ref or not weight_comp:
                deltas[f"component_{component}"].append(None)
                continue
            value_ref = sum(ref_vals) / weight_ref
            value_comp = sum(comp_vals) / weight_comp
            deltas[f"component_{component}"].append(scale_normalized_delta(
                value_comp, value_ref,
                floor=max(_protocol_floor(protocol, component),
                          float(scales[component]))))
        # ---- Stage-II decision metrics over drawn union cohort ----
        if stage2_cohort:
            mask = np.isin(cohort_ep, drawn)
            cohort_drawn = [node for node, keep in zip(stage2_cohort, mask) if keep]
            if cohort_drawn:
                ref_active = [float(decisions_ref[node]["u_star"]) > 0.0
                              for node in cohort_drawn]
                comp_active = [float(decisions_comp[node]["u_star"]) > 0.0
                               if node in decisions_comp else False
                               for node in cohort_drawn]
                deltas["activation_rate"].append(
                    float(np.mean(comp_active)) - float(np.mean(ref_active)))
                deltas["missed_activation_rate"].append(float(np.mean([
                    1.0 if active_ref and not active_comp else 0.0
                    for active_ref, active_comp in zip(ref_active, comp_active)])))
                deltas["false_activation_rate"].append(float(np.mean([
                    1.0 if not active_ref and active_comp else 0.0
                    for active_ref, active_comp in zip(ref_active, comp_active)])))
                total_delta = total_value = 0.0
                for node in cohort_drawn:
                    ref_u = float(decisions_ref[node]["u_star"])
                    comp_u = (float(decisions_comp[node]["u_star"])
                              if node in decisions_comp else 0.0)
                    curve = curves.get(node, {})
                    j_ref = curve.get(f"{ref_u:.1f}")
                    j_comp = curve.get(f"{comp_u:.1f}")
                    value = decisions_ref[node].get("recoverable_value")
                    if j_ref is None or j_comp is None or value is None:
                        continue
                    total_delta += float(j_comp) - float(j_ref)
                    total_value += float(value)
                deltas["l_rec"].append(
                    total_delta / total_value if total_value > 0.0 else None)
            else:
                for base in ("activation_rate", "missed_activation_rate",
                             "false_activation_rate", "l_rec"):
                    deltas[base].append(None)
    return dict(deltas)


def contrast_overlap(value_a: float | None, value_b: float | None) -> float | None:
    return None if value_a is None or value_b is None else value_b - value_a


def _rank_map_arrays(values: Mapping[str, float],
                     keys: Sequence[str]) -> dict[str, float]:
    ordered = sorted(keys, key=lambda key: (-values[key], key))
    return {key: float(position) for position, key in enumerate(ordered, start=1)}


def apply_equivalence(point_metrics: Mapping[str, Mapping[str, Any]],
                      replicate_map: Mapping[str, Sequence[float | None]],
                      protocol: Mapping[str, Any], *, replicates: int,
                      ) -> dict[str, Any]:
    """Frozen equivalence + identifiability rules per binding metric instance."""

    results: dict[str, Any] = {}
    for name, point in point_metrics.items():
        base = point["metric"]
        band_key = BINDING_METRICS[base]
        half = band_half_width(protocol, band_key)
        values = [value for value in replicate_map.get(name, [])
                  if value is not None and np.isfinite(value)]
        record = dict(point)
        record.update({"band": band_key, "band_half_width": half})
        if (point["delta"] is None
                or int(point.get("event_count") or 0) < IDENTIFIABILITY_MIN_EVENTS
                or len(values) < max(1, replicates // 2)):
            record.update({"delta_ci": None, "replicates_used": len(values),
                           "status": "NOT_IDENTIFIABLE_AT_THIS_N"})
        else:
            ci = _percentile_interval(values)
            record.update({
                "delta_ci": ci, "replicates_used": len(values),
                "status": ("PASS" if ci[0] >= -half and ci[1] <= half
                           else "FAIL"),
            })
        results[name] = record
    return results


# --------------------------------------------------------------------------- #
# comparison orchestrators
# --------------------------------------------------------------------------- #

def _stage2_union(ref_rows: Sequence[Mapping[str, Any]],
                  ref_shortlists: Mapping[str, Sequence[str]],
                  comp_shortlists: Mapping[str, Sequence[str]]) -> list[str]:
    ref_by_id = {str(row["node_id"]): row for row in ref_rows}
    union = {str(node) for nodes in ref_shortlists.values() for node in nodes}
    union |= {str(node) for nodes in comp_shortlists.values() for node in nodes}
    cohort = []
    for node_id in sorted(union):
        row = ref_by_id.get(node_id)
        if row is None or not row.get("support_full"):
            continue
        if not is_actionable(OperationalStage(str(row["stage"]))):
            continue
        cohort.append(node_id)
    return cohort


def fit_comparison_batch(
    year: int, *, n_grid: Sequence[int], ref_pass_dir: Path,
    comp_pass_dirs: Mapping[int, Path], service: M2ConsequenceService,
    headroom: HeadroomSummary, protocol: Mapping[str, Any],
    scales: Mapping[str, float], out_root: Path, tag: str = "FIT",
    replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
    skip_n: int | None = 4096,
) -> dict[int, dict[str, Any]]:
    """FIT stage: each M1_N vs M1_4096 on the same fixed cases (paired bootstrap).

    Also serves the determinism floor (two replica passes as ref/comp with a
    single pseudo-N) via ``tag="FLOOR"``.
    """

    ref_rows = read_node_frame(ref_pass_dir)
    ref_stage1 = stage1_evaluate(ref_rows, cohort_id=f"{tag}_REF_{year}")
    ref_shortlists = {stage: info["shortlist"]
                      for stage, info in ref_stage1["per_stage"].items() if info}
    comp_stage1_by_n = {
        n: stage1_evaluate(read_node_frame(path), cohort_id=f"{tag}_COMP_{year}_N{n}")
        for n, path in comp_pass_dirs.items()}
    all_comp_shortlists: dict[str, list[str]] = defaultdict(list)
    for stage in ref_shortlists:
        seen: set[str] = set()
        for n in comp_pass_dirs:
            for node in (comp_stage1_by_n[n]["per_stage"].get(stage)
                         or {}).get("shortlist", []):
                if node not in seen:
                    seen.add(node)
                    all_comp_shortlists[stage].append(node)
    union = _stage2_union(ref_rows, ref_shortlists, dict(all_comp_shortlists))
    ref_stage2 = stage2_solve_nodes(
        year, pass_dir=ref_pass_dir, node_ids=union, service=service,
        headroom=headroom, want_curves=True)
    comp_stage2_by_n = {}
    for n, path in comp_pass_dirs.items():
        shortlist = [node for stage in ref_shortlists
                     for node in (comp_stage1_by_n[n]["per_stage"].get(stage)
                                  or {}).get("shortlist", [])
                     if node in set(union)]
        comp_stage2_by_n[n] = stage2_solve_nodes(
            year, pass_dir=path, node_ids=sorted(set(shortlist)),
            service=service, headroom=headroom)
    ref_means = _episode_component_means(ref_rows)
    e_ref = max((int(row["episode_rank"]) for row in ref_rows), default=-1) + 1
    stage2_rank = {node: int(next(row["episode_rank"] for row in ref_rows
                                  if str(row["node_id"]) == node))
                   for node in union}
    outputs: dict[int, dict[str, Any]] = {}
    for n in n_grid:
        if skip_n is not None and int(n) == skip_n:
            continue
        comp_rows = read_node_frame(comp_pass_dirs[n])
        tables = _stage_tables(ref_rows, comp_rows, intersection_only=True)
        point, extras = _comparison_point_metrics(
            ref_rows=ref_rows, comp_rows=comp_rows,
            ref_stage1=ref_stage1, comp_stage1=comp_stage1_by_n[n],
            tables=tables,
            stage2={"cohort": union,
                    "decisions_ref": ref_stage2["decisions"],
                    "decisions_comp": comp_stage2_by_n[n]["decisions"],
                    "curves": ref_stage2["curves"],
                    "episode_rank": stage2_rank},
            ref_shortlists=ref_shortlists,
            comp_shortlists={stage: (comp_stage1_by_n[n]["per_stage"].get(stage)
                                     or {}).get("shortlist", [])
                             for stage in ref_shortlists},
            scales=scales, protocol=protocol, nested=False, n_prefix=None)
        comp_means = _episode_component_means(comp_rows)
        draws = episode_draws(range(e_ref), replicates=replicates, seed=seed)
        replicate_map = _replicate_deltas(
            tables=tables, ref_means=ref_means, comp_means=comp_means,
            stage2={"cohort": union,
                    "decisions_ref": ref_stage2["decisions"],
                    "decisions_comp": comp_stage2_by_n[n]["decisions"],
                    "curves": ref_stage2["curves"],
                    "episode_rank": stage2_rank},
            draws=draws, nested=False, n_prefix=None, scales=scales,
            protocol=protocol)
        results = apply_equivalence(point, replicate_map, protocol,
                                    replicates=replicates)
        payload = {
            "schema_version": "M5B_COMPARISON_METRICS_V1",
            "stage": tag, "year": year, "n": int(n),
            "n_ref": 4096 if tag == "FIT" else None,
            "bootstrap": {"type": "EPISODE_LEVEL_PAIRED", "replicates": replicates,
                          "seed": seed},
            "results": _jsonable(results),
            "extras": _jsonable(extras),
            "metric_definitions": METRIC_DEFINITIONS,
            "final_test_access_count": 0,
        }
        payload["artifact_hash"] = sha256_json(
            {key: value for key, value in payload.items()
             if key != "artifact_hash"})
        write_json_atomic(out_root / f"{tag}_METRICS_{year}_N{n}.json", payload)
        outputs[int(n)] = payload
    return outputs


def eval_comparison_batch(
    year: int, *, n_grid: Sequence[int], ref_pass_dir: Path,
    service: M2ConsequenceService, headroom: HeadroomSummary,
    protocol: Mapping[str, Any], scales: Mapping[str, float], out_root: Path,
    replicates: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED,
    evaluation_e: int | None = None,
) -> dict[int, dict[str, Any]]:
    """EVAL stage: fixed M1_4096 over nested prefixes (nested-cohort bootstrap)."""

    ref_rows = read_node_frame(ref_pass_dir)
    e_ref = evaluation_e or (max((int(row["episode_rank"]) for row in ref_rows),
                                 default=-1) + 1)
    ref_stage1 = stage1_evaluate(ref_rows, cohort_id=f"EVAL_REF_{year}")
    ref_shortlists = {stage: info["shortlist"]
                      for stage, info in ref_stage1["per_stage"].items() if info}
    prefixes = {}
    for n in n_grid:
        if int(n) >= e_ref:
            continue
        rows_n = [row for row in ref_rows if int(row["episode_rank"]) < int(n)]
        prefixes[int(n)] = stage1_shortlists(rows_n, cohort_id=f"EVAL_N{int(n)}")
    union = _stage2_union(ref_rows, ref_shortlists,
                          {stage: [node for nodes in prefixes.values()
                                   for node in nodes.get(stage, [])]
                           for stage in ref_shortlists})
    ref_stage2 = stage2_solve_nodes(
        year, pass_dir=ref_pass_dir, node_ids=union, service=service,
        headroom=headroom, want_curves=True)
    stage2_rank = {node: int(next(row["episode_rank"] for row in ref_rows
                                  if str(row["node_id"]) == node))
                   for node in union}
    ref_means = _episode_component_means(ref_rows)
    outputs: dict[int, dict[str, Any]] = {}
    for n in n_grid:
        n = int(n)
        if n >= e_ref:
            payload = {
                "schema_version": "M5B_COMPARISON_METRICS_V1",
                "stage": "EVAL", "year": year, "n": n,
                "status": "NOT_IDENTIFIABLE_AT_THIS_N",
                "reason": f"LADDER_CAP:{e_ref}",
                "results": {}, "final_test_access_count": 0,
            }
            payload["artifact_hash"] = sha256_json(
                {key: value for key, value in payload.items()
                 if key != "artifact_hash"})
            write_json_atomic(out_root / f"EVAL_METRICS_{year}_N{n}.json", payload)
            outputs[n] = payload
            continue
        comp_rows = [row for row in ref_rows if int(row["episode_rank"]) < n]
        comp_stage1 = stage1_evaluate(comp_rows, cohort_id=f"EVAL_N{n}")
        tables = _stage_tables(ref_rows, ref_rows, intersection_only=False)
        decisions_comp = {node: dict(ref_stage2["decisions"][node])
                          for stage, nodes in prefixes[n].items()
                          for node in nodes if node in ref_stage2["decisions"]}
        point, extras = _comparison_point_metrics(
            ref_rows=ref_rows, comp_rows=comp_rows,
            ref_stage1=ref_stage1, comp_stage1=comp_stage1,
            tables=tables,
            stage2={"cohort": union,
                    "decisions_ref": ref_stage2["decisions"],
                    "decisions_comp": decisions_comp,
                    "curves": ref_stage2["curves"],
                    "episode_rank": stage2_rank},
            ref_shortlists=ref_shortlists,
            comp_shortlists=prefixes[n],
            scales=scales, protocol=protocol, nested=True, n_prefix=n)
        draws = episode_draws(range(e_ref), replicates=replicates, seed=seed)
        replicate_map = _replicate_deltas(
            tables=tables, ref_means=ref_means,
            comp_means=_episode_component_means(comp_rows),
            stage2={"cohort": union,
                    "decisions_ref": ref_stage2["decisions"],
                    "decisions_comp": decisions_comp,
                    "curves": ref_stage2["curves"],
                    "episode_rank": stage2_rank},
            draws=draws, nested=True, n_prefix=n, scales=scales,
            protocol=protocol)
        results = apply_equivalence(point, replicate_map, protocol,
                                    replicates=replicates)
        payload = {
            "schema_version": "M5B_COMPARISON_METRICS_V1",
            "stage": "EVAL", "year": year, "n": n, "n_ref": e_ref,
            "bootstrap": {"type": "NESTED_COHORT", "replicates": replicates,
                          "seed": seed},
            "results": _jsonable(results),
            "extras": _jsonable(extras),
            "metric_definitions": METRIC_DEFINITIONS,
            "final_test_access_count": 0,
        }
        payload["artifact_hash"] = sha256_json(
            {key: value for key, value in payload.items()
             if key != "artifact_hash"})
        write_json_atomic(out_root / f"EVAL_METRICS_{year}_N{n}.json", payload)
        outputs[n] = payload
    return outputs


def floor_decision(metrics_by_setting: Mapping[str, Mapping[str, Any]],
                   protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Frozen floor rule: stop iff any floor >= 0.1 x band half-width.

    Consumes ``M5B_FLOOR_SETTING_V1`` payloads (``floor_comparison`` output),
    i.e. the per-setting point-estimate |metric(r1) - metric(r2)| table.
    """

    floors: dict[str, Any] = {}
    blocked = []
    for setting, payload in metrics_by_setting.items():
        for name, record in payload["floors"].items():
            floor_value = abs(float(record["floor"]))
            half = float(record["band_half_width"])
            current = floors.get(name)
            if current is None or floor_value > current["floor"]:
                floors[name] = {
                    "floor": floor_value,
                    "band": record.get("band"),
                    "band_half_width": half,
                    "setting": setting,
                }
    for name, record in floors.items():
        threshold = float(protocol["m1_determinism_sentinel"]["floor_rule"]
                          ["floor_fraction"]) * record["band_half_width"]
        record["threshold"] = threshold
        record["same_order_as_band"] = bool(record["floor"] >= threshold)
        if record["same_order_as_band"]:
            blocked.append(name)
    return {
        "floors": floors,
        "blocked_metrics": sorted(blocked),
        "decision": ("BLOCK_M5B_NONDETERMINISM" if blocked else "PROCEED"),
    }


# --------------------------------------------------------------------------- #
# ladder probe (runtime/memory ONLY; never outcome-aware)
# --------------------------------------------------------------------------- #

def ladder_probe(year: int, *, checkpoint: Path,
                 ranked_dev_episodes: Sequence[tuple[int, Any]],
                 scientific: Any, out_path: Path,
                 budget_hours: float = EVAL_BUDGET_HOURS,
                 probe_episodes: int = 128) -> dict[str, Any]:
    """Time the FIRST ``probe_episodes`` dev episodes end-to-end.

    Protocol: "time the per-node scenario+consequence cost on the first 128 dev
    nodes".  The probe therefore mirrors ``evaluate_model_on_cases`` exactly
    (binding resolution + scenario sampling + consequence mapping + common
    support) and writes NO artifacts and NO metrics; it produces timing numbers
    only.
    """

    import torch
    from exp.exp2.development_inputs import _observed, load_tail_continuations
    from model.M1.data import encode_pre_sequence
    from model.M1.pipeline import M1Pipeline
    from model.PRE.cohort import split_for_date_multiyear
    from model.PRE.development import materialize_preselected_cohorts

    started = time.perf_counter()
    taxi, turnaround = _load_year_references(year)
    bundle = load_year_m2_bundle(year)
    bundle_object = reference_bundle_object(bundle)
    headroom = year_headroom_summary(year)
    cases = list(ranked_dev_episodes)[:probe_episodes]
    partitions = {"train": (), "calibration": (),
                  "development": tuple(record for _rank, record in cases)}
    cohorts = materialize_preselected_cohorts(
        scientific, root=REPO, partitions=partitions, year=year,
        dataset_instance_id=INSTANCE_ID, split_resolver=split_for_date_multiyear,
        taxi_reference=taxi, turnaround_reference=turnaround)
    # cost model: fixed = reference/bundle/pipeline load + cohort
    # materialization (the 9-month raw scan); variable = per-node work below
    fixed_seconds = time.perf_counter() - started
    pipeline = M1Pipeline.load(checkpoint)
    tails = load_tail_continuations(
        REPO / "artifacts" / "diagnostics" / "m1_positive_tail_continuation_v1"
        / "M1_POSITIVE_TAIL_CONTINUATION_V1.json")
    pipeline.tail_continuations = dict(tails)
    probes: list[tuple[Any, Any, Any]] = list(_iter_active_nodes(cohorts, taxi))
    if not probes:
        raise ConsequenceInterfaceError(f"M5B_NO_ACTIVE_DEV_NODES:{year}")
    # binding resolution (canonical build_node_binding; part of pass cost)
    bindings: dict[str, ConsequenceReferenceBinding] = {}
    for _rank, prepared, node, prefix in probes:
        resolved = build_node_binding(
            node_id=node.decision_node_id,
            episode_id=node.episode_id,
            chain_id=chain_id_for_episode(prepared.episode),
            connection_airport_id=prepared.episode.connection_airport_id,
            destination_airport_id=route_destination(prefix[-1]),
            decision_time=node.decision_time,
            bundle=bundle_object,
        )
        if resolved.binding is not None:
            bindings[node.decision_node_id] = resolved.binding
    service = build_year_service(year, bundle, bindings)
    # scenario sampling + consequence mapping + common support (pass cost)
    scored = 0
    for _rank, prepared, node, prefix in probes:
        state = prefix[-1]
        values = encode_pre_sequence(prefix, pipeline.normalization)
        scenarios = pipeline.sample_from_pre(
            state, values.unsqueeze(0), torch.tensor([len(values)]),
            observed=_observed(state, taxi), count=SCENARIO_COUNT,
            seed=TRAIN_SEED, taxi_reference=taxi, tail_continuations=tails)
        state_set = state_set_from_m1_scenarios(
            scenarios,
            episode_id=node.episode_id,
            chain_id=chain_id_for_episode(prepared.episode),
            node_id=node.decision_node_id,
            stage=node.operational_stage,
            representation=HISTORY_JOINT_SPEC,
        )
        if node.decision_node_id in bindings:
            consequences = consequence_set(service, state_set)
        else:
            consequences = _abstaining_consequence_set(
                state_set, registry_id=service.registry_id,
                registry_hash=service.registry_hash)
        support = comparison_support_for(state_set, consequences)
        if support.included:
            expected = expected_cu_for_support(consequences, support)
            phi_c(expected)
            delay_priority_signal(state_set, support)
            scored += 1
    elapsed = time.perf_counter() - started
    node_count = len(probes)
    variable_seconds = max(0.0, elapsed - fixed_seconds)
    per_node = variable_seconds / max(1, node_count)
    nodes_per_episode = node_count / max(1, len(cohorts.development))
    projections = {}
    chosen = None
    for candidate in LADDER:
        projected_nodes = int(round(nodes_per_episode * candidate))
        projected_seconds = fixed_seconds + per_node * projected_nodes
        projections[str(candidate)] = {
            "projected_nodes": projected_nodes,
            "projected_hours": round(projected_seconds / 3600.0, 3),
        }
        if projected_seconds <= budget_hours * 3600.0 and chosen is None:
            chosen = candidate
    if chosen is None:
        record = {
            "schema_version": "M5B_LADDER_PROBE_V1", "year": year,
            "status": "BLOCK_M5B_COMPUTE_BUDGET",
            "probe_checkpoint": str(checkpoint),
            "probe_episodes": len(cohorts.development),
            "probe_nodes": node_count, "per_node_seconds": round(per_node, 4),
            "budget_hours": budget_hours, "projections": projections,
            "reason": "even ladder step 1024 exceeds the frozen 6h budget",
            "final_test_access_count": 0,
        }
        write_json_atomic(out_path, record)
        raise ComputeBudgetError(
            f"M5B_LADDER_BUDGET_EXCEEDED:{year}:{projections}")
    record = {
        "schema_version": "M5B_LADDER_PROBE_V1", "year": year,
        "status": "PASS", "evaluation_E": chosen,
        "probe_checkpoint": str(checkpoint),
        "probe_checkpoint_hash": file_hash(checkpoint),
        "probe_model_note": (
            "runtime-only timing with a per-year N128 M1 checkpoint (the "
            "year's fit checkpoint when present, else the legacy 2019 "
            "sentinel replica); probe outputs are timing numbers, never "
            "metrics"),
        "probe_scope": ("binding + sampling + consequence + common support "
                        "(mirrors evaluate_model_on_cases)"),
        "probe_episodes": len(cohorts.development),
        "probe_nodes": node_count, "probe_scored_nodes": scored,
        "fixed_seconds": round(fixed_seconds, 1),
        "variable_seconds": round(variable_seconds, 1),
        "per_node_seconds": round(per_node, 4),
        "budget_hours": budget_hours, "projections": projections,
        "demotions": [step for step in LADDER if step > chosen],
        "final_test_access_count": 0,
    }
    record["artifact_hash"] = sha256_json(
        {key: value for key, value in record.items() if key != "artifact_hash"})
    write_json_atomic(out_path, record)
    log(f"ladder {year}: evaluation_E={chosen} "
        f"(per_node={per_node:.4f}s, projections={projections})")
    return record
