"""``CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS``: post-hoc domain-weight stress test.

A ``POST_HOC_ROBUSTNESS`` analysis that answers one managerial question: do the
primary-specification conclusions -- recovery screening, priority versus
recoverability, and the decision value of different operational-information
representations -- depend on the primary specification's equal-domain weighting?

Only the three domain weights of ``Phi_C = w_F * F + w_P * P + w_R * R`` are
varied, through the frozen aggregation interface
(``model.M2.comparison_support.phi_c``), which the executor already threads
through ``RecoveryPolicy.aggregation_view`` for Stage II:

===========================  =========  ==========  ==========
profile_id                   w_F        w_P         w_R
===========================  =========  ==========  ==========
``BALANCED`` (primary)       1/3        1/3         1/3
``FLIGHT_EMPHASIS``          0.50       0.25        0.25
``PASSENGER_EMPHASIS``       0.25       0.50        0.25
``RESOURCE_EMPHASIS``        0.25       0.25        0.50
===========================  =========  ==========  ==========

``BALANCED`` is mapped onto the existing canonical primary aggregation view
(``PRIMARY_AGGREGATION_VIEW``); no balanced alias is created. The three emphasis
profiles are symmetric stress-test scenarios, **not** elicited airline
preference estimates, not learned or calibrated weights, and they never replace
the primary specification.

Nothing else changes. The seven consequence components, component normalization,
component availability, CU construction, the within-domain aggregation, the
domain definition, the effort cost ``0.25 * u / 45``, ``U_max = 45``, the
turnaround lower bound, the five-minute recovery grid, the scenario weights, the
common-support rule, Stage-I ``q = 0.10``, the shared selector and its tie-break,
and the fixed Stage-II cohort ``R*`` (N = 16, PRE 3 / TURN 13) are consumed
exactly as sealed. PRE and TURN are evaluated independently and are never pooled.
No weight grid search, optimization, AHP, entropy weighting, expert scoring,
Bayesian preference estimation, Stage x q x weight factorial, new consequence
component, new recovery cohort, new bootstrap family, new hypothesis-testing
family and no decision-margin quantity is produced. This is descriptive
robustness only: no p-value, no confidence interval, no permutation test, no
regression, and no threshold that would declare a profile "robust".

Replay gates must pass before any emphasis result is produced. Gate B replays the
sealed Stage-I authority (952/952 consequence priorities, the sealed shortlists,
ranks, cohort capacities, the Delay-vs-Consequence headline and the sealed
information comparators). Gate C replays the sealed Stage-II authority (160/160
objective-curve points, 64/64 sealed actions and the sealed recovery
comparators). Gate A holds the repository authority, and Gate D re-asserts the
primary invariance of every sealed and frozen input.

Execution is transactional. Every artifact is written into
``<out_dir>.__staging__`` first and materialized into place with a single
same-filesystem rename (fresh) or a backup swap with rollback (regeneration); a
failed run never leaves a partial directory in the official location. Nothing
outside ``<out_dir>``, its staging sibling and its previous sibling is ever
written, and the two paper-results roots are fingerprinted before and after the
run to prove that no other paper-result artifact was created, changed, replaced
or deleted.

Usage (from the repository root)::

    python -m formal.v2_phase7.consequence_domain_emphasis_robustness \
        --epoch-root <sealed canonical-v2 epoch root> \
        --out-dir <directory receiving the nine result files> \
        [--profiles BALANCED,FLIGHT_EMPHASIS,...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from model.M2.comparison_support import (
    DOMAIN_EMPHASIS_FLIGHT_VIEW,
    DOMAIN_EMPHASIS_PASSENGER_VIEW,
    DOMAIN_EMPHASIS_RESOURCE_VIEW,
    DOMAIN_EMPHASIS_VIEW_WEIGHTS,
    PRIMARY_AGGREGATION_VIEW,
    phi_c,
)
from model.M3.stage1 import select_paired_attention
from model.M3.stage2 import RecoveryPolicy, expected_objective, objective_by_grid
from model.M3.transition import TransitionContext
from model.M4.evaluation import (
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)
from model.common.decision_contracts import (
    AttentionDecision,
    PrioritySignal,
    RecoveryDecision,
    SignalKind,
)

from . import constants as C
from .executor import stages as S
from .executor.attention_decisions import decision_rows
from .executor.checkpoints import CheckpointStore
from .executor.codec import (
    attention_decision_from_payload,
    recovery_decision_from_payload,
)
from .executor.consequence_variants import (
    rows_by_variant as consequence_rows_by_variant,
)
from .executor.consequence_variants import signals_by_variant
from .executor.nodes import nodes_by_id
from .executor.recovery_decisions import rows_by_variant as recovery_rows_by_variant
from .executor.reference_cohort import actionable_cohort
from .executor.services import binding_from_node, load_frozen_services
from .executor.state_variants import state_sets_by_node
from .stage2_authority import solve_production_recovery


ANALYSIS_NAME = "CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS"
ANALYSIS_TYPE = "POST_HOC_ROBUSTNESS"
SPLIT = "FINAL_TEST"
REFERENCE_VARIANT = S.REFERENCE_VARIANT
STAGES = S.ACTIONABLE_STAGE_I_STAGES
STAGE_CLASS = {"PRE_IB": "PRE", "POST_IB_PRE_OB": "TURN"}

NOMINAL_Q = float(C.NOMINAL_Q)
EXPECTED_STAGE1_N = {"PRE_IB": 29, "POST_IB_PRE_OB": 127}
EXPECTED_STAGE1_K = {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
EXPECTED_STAGE2_N = 16
EXPECTED_STAGE2_STAGE_COUNTS = {"PRE_IB": 3, "POST_IB_PRE_OB": 13}
EXPECTED_CONSEQUENCE_VARIANT_ROWS = 952
EXPECTED_STAGE2_SEALED_CASES = 4 * EXPECTED_STAGE2_N
EXPECTED_STAGE2_REPLAY_POINTS = EXPECTED_STAGE2_N * 10

#: Both roles reuse the frozen numerical comparison tolerance, never a new one.
REPLAY_TOLERANCE = float(C.M3_NUMERICAL_COMPARISON_TOLERANCE)
REPLAY_TOLERANCE_SOURCE = "C.M3_NUMERICAL_COMPARISON_TOLERANCE"
VALUE_TOLERANCE = 1e-12

STAGE1_PROFILE_SUMMARY_NAME = "DOMAIN_EMPHASIS_STAGE1_PROFILE_SHORTLIST_SUMMARY.csv"
STAGE1_DELAY_NAME = "DOMAIN_EMPHASIS_STAGE1_DELAY_SUMMARY.csv"
STAGE1_INFORMATION_NAME = "DOMAIN_EMPHASIS_STAGE1_INFORMATION_SUMMARY.csv"
STAGE2_HJ_ACTION_NAME = "DOMAIN_EMPHASIS_STAGE2_HJ_ACTION_SUMMARY.csv"
STAGE2_INFORMATION_NAME = "DOMAIN_EMPHASIS_STAGE2_INFORMATION_SUMMARY.csv"
STAGE1_RECORDS_NAME = "DOMAIN_EMPHASIS_STAGE1_CHAIN_RECORDS.parquet"
STAGE2_RECORDS_NAME = "DOMAIN_EMPHASIS_STAGE2_CHAIN_RECORDS.parquet"
MANIFEST_NAME = "DOMAIN_EMPHASIS_ROBUSTNESS_MANIFEST.json"
REPORT_NAME = "DOMAIN_EMPHASIS_ROBUSTNESS_REPORT.md"

#: Hashed into the manifest. The manifest cannot contain its own SHA256 by
#: construction, so it is listed in ``output_artifact_paths`` only.
PAYLOAD_ARTIFACTS: tuple[str, ...] = (
    STAGE1_PROFILE_SUMMARY_NAME,
    STAGE1_DELAY_NAME,
    STAGE1_INFORMATION_NAME,
    STAGE2_HJ_ACTION_NAME,
    STAGE2_INFORMATION_NAME,
    STAGE1_RECORDS_NAME,
    STAGE2_RECORDS_NAME,
    REPORT_NAME,
)

#: Row-level frames stay local and regenerable; paper-results roots in this
#: repository version-control CSV/JSON/MD only.
LOCAL_ONLY_ARTIFACTS: tuple[str, ...] = (STAGE1_RECORDS_NAME, STAGE2_RECORDS_NAME)

STAGING_SUFFIX = ".__staging__"
PREVIOUS_SUFFIX = ".__previous__"
WRITE_MODE = "STAGED_TRANSACTIONAL_MATERIALIZATION"
FRESH_ATOMIC_RENAME = "FRESH_ATOMIC_RENAME"
BACKUP_SWAP_WITH_ROLLBACK = "BACKUP_SWAP_WITH_ROLLBACK"

SOURCE_RELATIVE_PATH = "formal/v2_phase7/consequence_domain_emphasis_robustness.py"
TEST_RELATIVE_PATH = "tests/phase7/test_consequence_domain_emphasis_robustness.py"
VIEW_CONTRACT_TEST_RELATIVE_PATH = "tests/m2/test_domain_emphasis_views.py"

#: The one implementation source this Step edits on purpose. Its
#: pre-implementation and post-implementation hashes are *not* expected to
#: match; the post-implementation hash becomes the implementation authority and
#: must stay stable for the whole analysis run.
IMPLEMENTATION_MODIFIED_SOURCE_PATH = "model/M2/comparison_support.py"

IMPLEMENTATION_SOURCE_PATHS: tuple[str, ...] = (
    IMPLEMENTATION_MODIFIED_SOURCE_PATH,
    SOURCE_RELATIVE_PATH,
    TEST_RELATIVE_PATH,
    VIEW_CONTRACT_TEST_RELATIVE_PATH,
)

#: Frozen scientific sources this Step must not touch. Their hashes are recorded
#: at run start and re-checked at run end.
#: Frozen scientific sources this Step must not touch. Their hashes are recorded
#: at run start and re-checked at run end. ``model/M2/comparison_support.py`` is
#: deliberately **not** here: it is the declared implementation edit (rule R1) and
#: is tracked by the implementation-authority block instead.
FROZEN_SCIENCE_SOURCE_PATHS: tuple[str, ...] = (
    "model/M2/consequence_service.py",
    "model/M3/stage1.py",
    "model/M3/stage2.py",
    "model/M3/transition.py",
    "model/M4/evaluation.py",
    "model/common/consequence_ontology.py",
)

#: Tracked modifications Gate A may tolerate at run start: this Step's declared
#: implementation edit, plus the two provenance files the repository's own test
#: suite refreshes (restored after the suite, before the final audit). Anything
#: else is a blocker before any scientific output is produced.
KNOWN_TEST_SIDE_EFFECT_MODIFICATIONS: tuple[str, ...] = (
    "artifacts/diagnostics/m1_v2_feature_gate_b2r/AIR_SLOT_M1_V2_FEATURE_GATE_B2R.json",
    "artifacts/diagnostics/m1_v2_feature_gate_b2r/data_usage_audit/"
    "AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT.json",
)

#: Tracked paths this analysis must never modify, except for its own designated
#: transaction paths (see ``_assert_write_target_allowed``).
PROTECTED_TRACKED_PREFIXES: tuple[str, ...] = (
    "artifacts/experiment/final_test_v2",
    "artifacts/paper_results_v2_final_test",
    "artifacts/paper_results_v2_final_test_rmb",
    "registries/",
    "docs/",
)

#: The two paper-results roots fingerprinted before and after the run.
PAPER_RESULTS_ROOTS: tuple[str, ...] = (
    "artifacts/paper_results_v2_final_test",
    "artifacts/paper_results_v2_final_test_rmb",
)

PROHIBITED_COLUMN_PATTERNS: tuple[str, ...] = (
    "p_value",
    "pvalue",
    "ci_low",
    "ci_high",
    "confidence_interval",
    "bootstrap",
    "permutation",
    "regression",
    "cutoff_margin",
    "epsilon",
    "perturbation",
    "certificate",
    "robust_flag",
)

RECOVERY_EVENT_KEYS: tuple[str, ...] = (
    "MISSED_ACTIVATION",
    "FALSE_ACTIVATION",
    "UNDER_RECOVERY",
    "OVER_RECOVERY",
)


@dataclass(frozen=True)
class DomainWeightProfile:
    """One consequence-domain emphasis scenario."""

    profile_id: str
    aggregation_view: str
    domain_weights: tuple[float, float, float]
    role: str
    is_primary_reference: bool

    def as_manifest_block(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "aggregation_view": self.aggregation_view,
            "domain_weights": {
                "F": self.domain_weights[0],
                "P": self.domain_weights[1],
                "R": self.domain_weights[2],
            },
            "role": self.role,
        }


BALANCED_PROFILE = DomainWeightProfile(
    profile_id="BALANCED",
    aggregation_view=PRIMARY_AGGREGATION_VIEW,
    domain_weights=(1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
    role="PRIMARY_REFERENCE_SPECIFICATION_FROZEN",
    is_primary_reference=True,
)

PROFILES: tuple[DomainWeightProfile, ...] = (
    BALANCED_PROFILE,
    DomainWeightProfile(
        profile_id="FLIGHT_EMPHASIS",
        aggregation_view=DOMAIN_EMPHASIS_FLIGHT_VIEW,
        domain_weights=DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_FLIGHT_VIEW],
        role="SYMMETRIC_POST_HOC_STRESS_SCENARIO",
        is_primary_reference=False,
    ),
    DomainWeightProfile(
        profile_id="PASSENGER_EMPHASIS",
        aggregation_view=DOMAIN_EMPHASIS_PASSENGER_VIEW,
        domain_weights=DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_PASSENGER_VIEW],
        role="SYMMETRIC_POST_HOC_STRESS_SCENARIO",
        is_primary_reference=False,
    ),
    DomainWeightProfile(
        profile_id="RESOURCE_EMPHASIS",
        aggregation_view=DOMAIN_EMPHASIS_RESOURCE_VIEW,
        domain_weights=DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_RESOURCE_VIEW],
        role="SYMMETRIC_POST_HOC_STRESS_SCENARIO",
        is_primary_reference=False,
    ),
)

PROFILE_BY_ID: dict[str, DomainWeightProfile] = {
    profile.profile_id: profile for profile in PROFILES
}
EMPHASIS_PROFILES: tuple[DomainWeightProfile, ...] = tuple(
    profile for profile in PROFILES if not profile.is_primary_reference
)
EMPHASIS_PROFILE_IDS: tuple[str, ...] = tuple(
    profile.profile_id for profile in EMPHASIS_PROFILES
)
ALL_PROFILE_IDS: tuple[str, ...] = tuple(profile.profile_id for profile in PROFILES)


class CheckFailure(RuntimeError):
    """A frozen-contract regression check or an analysis gate failed."""


def _require(condition: bool, code: str, detail: Any = None) -> None:
    if not condition:
        raise CheckFailure(f"{code}: {detail}")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_text_sha256_bytes(data: bytes) -> str:
    """CRLF -> LF canonical text hash (line-ending compatibility only)."""

    return "sha256:" + hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=C.ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_head() -> str:
    try:
        return _git("rev-parse", "HEAD")
    except Exception:  # pragma: no cover - provenance only
        return "UNKNOWN"


def _git_porcelain_lines() -> list[str]:
    """Raw porcelain lines; never stripped, the leading status column matters."""

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=C.ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _porcelain_path(line: str) -> str:
    """``XY PATH`` -> ``PATH`` (two status columns plus one separator)."""

    return line[3:].strip() if len(line) > 3 else ""


def _git_tracked_modifications() -> list[str]:
    return [
        _porcelain_path(line)
        for line in _git_porcelain_lines()
        if not line.startswith("??")
    ]


def _git_untracked_paths() -> list[str]:
    return [
        _porcelain_path(line)
        for line in _git_porcelain_lines()
        if line.startswith("??")
    ]


def _git_blob_canonical_sha256(relative_path: str) -> str | None:
    """Canonical-LF hash of the sealed-tree blob at HEAD, or ``None``."""

    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative_path}"],
            cwd=C.ROOT,
            check=True,
            capture_output=True,
        )
    except Exception:  # pragma: no cover - provenance only
        return None
    return _canonical_text_sha256_bytes(result.stdout)


def _rename(source: Path, target: Path) -> None:
    """Single filesystem rename; the transaction's only mutation primitive."""

    source.rename(target)


def _close(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= VALUE_TOLERANCE


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    resolved = float(value)
    return None if not np.isfinite(resolved) else resolved


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    return float(numerator) / float(denominator)


def _joined(values: Sequence[str]) -> str:
    return "|".join(str(value) for value in values)


# ----------------------------------------------------------------------
# profile scope
# ----------------------------------------------------------------------
def resolve_profile_scope(
    profiles: Sequence[str] | None,
) -> tuple[DomainWeightProfile, ...]:
    """Resolve the requested profile scope; ``BALANCED`` is always included.

    ``BALANCED`` is the primary reference and the basis of every replay gate, so
    it is never optional. The returned order follows ``PROFILES``.
    """

    if profiles is None:
        selected = set(ALL_PROFILE_IDS)
    else:
        requested = [str(value).strip() for value in profiles if str(value).strip()]
        unknown = sorted(set(requested) - set(ALL_PROFILE_IDS))
        _require(
            not unknown,
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_UNKNOWN_PROFILE",
            {"unknown": unknown, "known": list(ALL_PROFILE_IDS)},
        )
        selected = set(requested) | {BALANCED_PROFILE.profile_id}
    return tuple(profile for profile in PROFILES if profile.profile_id in selected)


def expected_row_counts(*, profile_ids: Sequence[str]) -> dict[str, int]:
    """Exact expected row counts for a given profile scope."""

    selected = set(profile_ids) | {BALANCED_PROFILE.profile_id}
    emphasis = len(
        [value for value in selected if value != BALANCED_PROFILE.profile_id]
    )
    return {
        STAGE1_PROFILE_SUMMARY_NAME: emphasis * len(STAGES),
        STAGE1_DELAY_NAME: len(selected) * len(STAGES),
        STAGE1_INFORMATION_NAME: (
            len(selected) * len(STAGES) * len(S.COMPARATOR_VARIANTS)
        ),
        STAGE2_HJ_ACTION_NAME: emphasis,
        STAGE2_INFORMATION_NAME: len(selected) * len(S.COMPARATOR_VARIANTS),
        STAGE2_RECORDS_NAME: (
            len(selected) * len(S.PRIMARY_STATE_VARIANTS) * EXPECTED_STAGE2_N
            + len(selected) * len(S.COMPARATOR_VARIANTS) * EXPECTED_STAGE2_N
            + emphasis * EXPECTED_STAGE2_N
        ),
        STAGE1_RECORDS_NAME: (
            len(selected)
            * len(S.PRIMARY_STATE_VARIANTS)
            * sum(EXPECTED_STAGE1_N.values())
        ),
    }


def assert_no_prohibited_columns(*, frames: Mapping[str, pd.DataFrame]) -> None:
    """This analysis introduces no margin, certificate or inference column."""

    offenders: dict[str, list[str]] = {}
    for name, frame in frames.items():
        hits = [
            str(column)
            for column in frame.columns
            if any(
                pattern in str(column).lower() for pattern in PROHIBITED_COLUMN_PATTERNS
            )
        ]
        if hits:
            offenders[name] = sorted(hits)
    _require(
        not offenders,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_PROHIBITED_COLUMN",
        offenders,
    )


# ----------------------------------------------------------------------
# frozen inputs
# ----------------------------------------------------------------------
CHECKPOINT_INPUTS: tuple[str, ...] = (
    S.ATTENTION_DECISIONS,
    S.CANONICAL_NODES,
    S.CONSEQUENCE_VARIANTS,
    S.M4_COMPARISONS,
    S.RECOVERY_DECISIONS,
    S.REFERENCE_RECOVERY_COHORT,
    S.STATE_VARIANTS,
)

EPOCH_INPUTS: tuple[str, ...] = (
    "EPOCH_SEAL.json",
    "FINAL_TEST_EXECUTION_RESULT.json",
    "POST_EXECUTION_AUDIT.json",
    "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json",
    "PAPER_FACING_SECTION5_RESULTS.json",
)


def _frozen_service_inputs() -> dict[str, Path]:
    from .executor.services import (
        CURRENT_CHECKPOINT,
        CURRENT_MANIFEST,
        H16_CHECKPOINT,
        H16_MANIFEST,
        M2_REGISTRY_PATH,
        TAIL_MANIFEST_PATH,
    )

    return {
        "H16_CHECKPOINT": H16_CHECKPOINT,
        "H16_MANIFEST": H16_MANIFEST,
        "CURRENT_CHECKPOINT": CURRENT_CHECKPOINT,
        "CURRENT_MANIFEST": CURRENT_MANIFEST,
        "TAIL_MANIFEST_PATH": TAIL_MANIFEST_PATH,
        "M2_REGISTRY_PATH": M2_REGISTRY_PATH,
        "TRAIN_SUPPORT_SUMMARY_PATH": C.TRAIN_SUPPORT_SUMMARY_PATH,
    }


def collect_input_paths(epoch_root: Path) -> dict[str, str]:
    """Every frozen input is path- and hash-recorded in the manifest."""

    paths: dict[str, str] = {
        f"checkpoints/{stage}": str(epoch_root / "checkpoints" / f"{stage}.json")
        for stage in CHECKPOINT_INPUTS
    }
    paths.update({f"epoch/{name}": str(epoch_root / name) for name in EPOCH_INPUTS})
    paths.update(
        {
            f"frozen_service/{name}": str(path)
            for name, path in _frozen_service_inputs().items()
        }
    )
    return paths


def _frozen_science_source_hashes() -> dict[str, str]:
    """Hashes of the frozen scientific sources; a missing path is a blocker."""

    resolved: dict[str, str] = {}
    for relative in FROZEN_SCIENCE_SOURCE_PATHS:
        path = C.ROOT / relative
        _require(
            path.is_file(),
            "CONSEQUENCE_DOMAIN_EMPHASIS_FROZEN_SOURCE_MISSING",
            relative,
        )
        resolved[relative] = _sha256_file(path)
    return resolved


def _implementation_source_hashes() -> dict[str, str]:
    return {
        path: (
            _sha256_file(C.ROOT / path) if (C.ROOT / path).is_file() else "ABSENT"
        )
        for path in IMPLEMENTATION_SOURCE_PATHS
    }


def _verify_epoch_identity(epoch_root: Path) -> dict[str, Any]:
    """Verify the sealed epoch provenance records used for identity only."""

    seal = _load(epoch_root / "EPOCH_SEAL.json")
    _require(
        seal.get("status") == "SEALED_AUDIT_PASS"
        and seal.get("final_test_complete") is True
        and seal.get("paper_results_frozen") is True
        and seal.get("scientific_definition_changed") is False,
        "CONSEQUENCE_DOMAIN_EMPHASIS_EPOCH_SEAL_INVALID",
        {
            key: seal.get(key)
            for key in (
                "status",
                "final_test_complete",
                "paper_results_frozen",
                "scientific_definition_changed",
            )
        },
    )
    _require(
        _sha256_file(epoch_root / "FINAL_TEST_EXECUTION_RESULT.json")
        == seal.get("execution_result_sha256"),
        "CONSEQUENCE_DOMAIN_EMPHASIS_EPOCH_EXECUTION_RESULT_IDENTITY",
    )
    _require(
        _sha256_file(epoch_root / "POST_EXECUTION_AUDIT.json")
        == seal.get("post_execution_audit_json_sha256"),
        "CONSEQUENCE_DOMAIN_EMPHASIS_EPOCH_POST_AUDIT_IDENTITY",
    )
    return {
        "epoch_seal_status": seal.get("status"),
        "epoch_seal_file_sha256": _sha256_file(epoch_root / "EPOCH_SEAL.json"),
        "execution_result_sha256": seal.get("execution_result_sha256"),
        "post_execution_audit_sha256": seal.get("post_execution_audit_json_sha256"),
    }


# ----------------------------------------------------------------------
# paper-results read-only scope (rule R3)
# ----------------------------------------------------------------------
def paper_results_snapshot(*, excluded: Sequence[Path]) -> dict[str, str]:
    """Path -> sha256 for every file under the paper-results roots.

    The designated transaction paths (the output directory, its staging sibling
    and its previous sibling) are excluded, so an unchanged snapshot proves that
    no other paper-result artifact was created, changed, replaced or deleted.
    """

    resolved_excluded = [Path(item).resolve() for item in excluded]
    snapshot: dict[str, str] = {}
    for relative in PAPER_RESULTS_ROOTS:
        root = C.ROOT / relative
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if any(resolved == item or item in resolved.parents for item in resolved_excluded):
                continue
            snapshot[path.relative_to(C.ROOT).as_posix()] = _sha256_file(path)
    return snapshot


def _snapshot_digest(snapshot: Mapping[str, str]) -> str:
    body = json.dumps(dict(sorted(snapshot.items())), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _assert_write_target_allowed(*, target: Path, out_dir: Path) -> None:
    """Rule R3: only the three designated transaction paths may be written."""

    allowed = (
        Path(out_dir).resolve(),
        staging_path(out_dir).resolve(),
        previous_path(out_dir).resolve(),
    )
    resolved = Path(target).resolve()
    _require(
        any(resolved == item or item in resolved.parents for item in allowed),
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_WRITE_TARGET_OUTSIDE_TRANSACTION",
        {"target": str(target), "out_dir": str(out_dir)},
    )


# ----------------------------------------------------------------------
# staging and transactional materialization
# ----------------------------------------------------------------------
def staging_path(out_dir: Path) -> Path:
    return Path(out_dir).parent / (Path(out_dir).name + STAGING_SUFFIX)


def previous_path(out_dir: Path) -> Path:
    return Path(out_dir).parent / (Path(out_dir).name + PREVIOUS_SUFFIX)


def write_staging(
    *,
    staging: Path,
    frames: Mapping[str, pd.DataFrame],
    report: str,
    out_dir: Path,
) -> None:
    """Write every payload artifact into a fresh staging tree."""

    staging = Path(staging)
    _assert_write_target_allowed(target=staging, out_dir=out_dir)
    staging.mkdir(parents=True, exist_ok=False)
    for name, frame in frames.items():
        target = staging / name
        if target.suffix.lower() == ".parquet":
            frame.to_parquet(target, index=False)
        else:
            frame.to_csv(target, index=False, lineterminator="\n")
    (staging / REPORT_NAME).write_text(report, encoding="utf-8", newline="\n")


def write_manifest(*, staging: Path, manifest: Mapping[str, Any], out_dir: Path) -> None:
    """Write the manifest last, so it describes artifacts that already exist."""

    staging = Path(staging)
    _assert_write_target_allowed(target=staging, out_dir=out_dir)
    with open(staging / MANIFEST_NAME, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False))
        handle.write("\n")


def _verify_materialized(*, out_dir: Path, hashes: Mapping[str, str]) -> None:
    mismatches: dict[str, Any] = {}
    for name, digest in hashes.items():
        observed = _sha256_file(out_dir / name)
        if observed != digest:
            mismatches[name] = {"expected": digest, "observed": observed}
    _require(
        not mismatches,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_MATERIALIZATION_VERIFICATION",
        mismatches,
    )


def materialize(*, staging: Path, out_dir: Path, hashes: Mapping[str, str]) -> str:
    """Move a completed staging tree into place; never expose a partial result.

    A fresh run is a single same-filesystem rename. A regeneration is a backup
    swap: the completed previous result is moved aside, staging is moved in, the
    materialized tree is verified against its recorded hashes, and only then is
    the backup removed. If the swap fails the previous result is restored; if
    even that fails, all three directories are preserved and named in the error.
    """

    out_dir = Path(out_dir)
    staging = Path(staging)
    previous = previous_path(out_dir)
    _assert_write_target_allowed(target=out_dir, out_dir=out_dir)
    if not out_dir.exists():
        _rename(staging, out_dir)
        _verify_materialized(out_dir=out_dir, hashes=hashes)
        return FRESH_ATOMIC_RENAME

    _require(
        not previous.exists(),
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_MATERIALIZATION_RESIDUE",
        {"previous_path": str(previous)},
    )
    _rename(out_dir, previous)
    try:
        _rename(staging, out_dir)
    except OSError as error:
        try:
            _rename(previous, out_dir)
        except OSError as rollback_error:
            raise CheckFailure(
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_MATERIALIZATION_ROLLBACK: "
                + json.dumps(
                    {
                        "target_path": str(out_dir),
                        "previous_path": str(previous),
                        "staging_path": str(staging),
                        "swap_error": str(error),
                        "rollback_error": str(rollback_error),
                    },
                    sort_keys=True,
                )
            ) from rollback_error
        shutil.rmtree(staging, ignore_errors=True)
        raise CheckFailure(
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_MATERIALIZATION: "
            + json.dumps(
                {
                    "target_path": str(out_dir),
                    "previous_path": str(previous),
                    "staging_path": str(staging),
                    "swap_error": str(error),
                    "rollback": "SUCCEEDED_PREVIOUS_RESULT_RESTORED",
                },
                sort_keys=True,
            )
        ) from error
    _verify_materialized(out_dir=out_dir, hashes=hashes)
    shutil.rmtree(previous)
    return BACKUP_SWAP_WITH_ROLLBACK


def planned_materialization_mode(out_dir: Path) -> str:
    return (
        FRESH_ATOMIC_RENAME if not Path(out_dir).exists() else BACKUP_SWAP_WITH_ROLLBACK
    )


# ----------------------------------------------------------------------
# Gate A - repository authority and output collision
# ----------------------------------------------------------------------
def gate_repository_authority(*, out_dir: Path) -> dict[str, Any]:
    """Branch, head, worktree classification and residue checks.

    Only two classes of pre-existing tracked modification are tolerated: this
    Step's declared implementation sources, and the two provenance files the
    repository's own test suite refreshes (which are restored before the final
    audit). Any other tracked modification is a blocker raised before any
    scientific output is produced. What must also hold is that *this* run
    introduces no tracked modification at all and that no protected scientific
    path is dirty in either direction.
    """

    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        head_start = _git("rev-parse", "HEAD")
        porcelain_lines = _git_porcelain_lines()
    except Exception as error:  # pragma: no cover - environment dependent
        raise CheckFailure(
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY: "
            f"git unavailable: {error}"
        ) from error

    tracked_modifications = [
        _porcelain_path(line)
        for line in porcelain_lines
        if not line.startswith("??")
    ]
    preexisting_untracked = [
        _porcelain_path(line) for line in porcelain_lines if line.startswith("??")
    ]
    implementation = sorted(
        path
        for path in tracked_modifications
        if path in IMPLEMENTATION_SOURCE_PATHS
    )
    known_side_effects = sorted(
        path
        for path in tracked_modifications
        if path in KNOWN_TEST_SIDE_EFFECT_MODIFICATIONS
    )
    unexpected = sorted(
        set(tracked_modifications) - set(implementation) - set(known_side_effects)
    )
    _require(
        not unexpected,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY",
        {
            "reason": "UNEXPECTED_TRACKED_MODIFICATION_AT_RUN_START",
            "entries": unexpected,
            "allowed_implementation_modifications": list(IMPLEMENTATION_SOURCE_PATHS),
            "known_test_side_effects": list(KNOWN_TEST_SIDE_EFFECT_MODIFICATIONS),
        },
    )

    staging = staging_path(out_dir)
    previous = previous_path(out_dir)
    exempt = {
        str(Path(out_dir).resolve()),
        str(staging.resolve()),
        str(previous.resolve()),
    }
    protected = [
        path
        for path in tracked_modifications
        if any(path.startswith(prefix) for prefix in PROTECTED_TRACKED_PREFIXES)
        and str((C.ROOT / path).resolve()) not in exempt
    ]
    _require(
        not protected,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY",
        {"reason": "PROTECTED_TRACKED_FILE_MODIFIED", "entries": protected},
    )
    _require(
        not staging.exists(),
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_STAGING_RESIDUE",
        {"staging_path": str(staging)},
    )
    _require(
        not previous.exists(),
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_MATERIALIZATION_RESIDUE",
        {"previous_path": str(previous)},
    )
    return {
        "repo_root": str(C.ROOT),
        "branch": branch,
        "head_start": head_start,
        "preexisting_untracked": preexisting_untracked,
        "tracked_modifications_start": tracked_modifications,
        "preexisting_implementation_modifications": implementation,
        "preexisting_known_test_side_effects": known_side_effects,
        "preexisting_unexpected_tracked_modifications": unexpected,
        "protected_tracked_modifications": protected,
        "protected_tracked_prefixes": list(PROTECTED_TRACKED_PREFIXES),
        "protected_tracked_prefix_exemptions": sorted(exempt),
        "unexpected_tracked_modification_policy": "BLOCKER_NOT_METADATA",
    }


def check_output_collision(
    *,
    out_dir: Path,
    head: str,
    input_hashes: Mapping[str, str],
    analysis_source_sha256: str | None,
) -> dict[str, Any]:
    """An existing result is only regenerated by an identical run.

    Identical means the same git head, the same input hashes **and** the same
    analysis source hash: a human edit of this module must never silently
    overwrite an earlier result.
    """

    manifest_path = Path(out_dir) / MANIFEST_NAME
    if not manifest_path.is_file():
        _require(
            not Path(out_dir).exists(),
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_OUTPUT_COLLISION",
            {"reason": "OUTPUT_DIRECTORY_WITHOUT_MANIFEST", "out_dir": str(out_dir)},
        )
        return {"collision_check": "NO_PREVIOUS_RESULT", "regeneration": False}

    previous = _load(manifest_path)
    mismatches: dict[str, Any] = {}
    if previous.get("git_head") != head:
        mismatches["git_head"] = {"previous": previous.get("git_head"), "current": head}
    previous_inputs = dict(previous.get("input_artifact_hashes", {}))
    if previous_inputs != dict(input_hashes):
        mismatches["input_artifact_hashes"] = {
            "changed_keys": sorted(
                key
                for key in set(previous_inputs) | set(input_hashes)
                if previous_inputs.get(key) != input_hashes.get(key)
            )
        }
    if previous.get("analysis_source_sha256") != analysis_source_sha256:
        mismatches["analysis_source_sha256"] = {
            "previous": previous.get("analysis_source_sha256"),
            "current": analysis_source_sha256,
        }
    _require(
        not mismatches,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_OUTPUT_COLLISION",
        {
            "reason": "EXISTING_RESULT_FROM_A_DIFFERENT_RUN",
            "out_dir": str(out_dir),
            "mismatches": mismatches,
        },
    )
    return {
        "collision_check": "IDENTICAL_PRIOR_RUN",
        "regeneration": True,
        "previous_git_head": previous.get("git_head"),
        "previous_run_timestamp": previous.get("run_timestamp"),
    }


# ----------------------------------------------------------------------
# Stage-I basis: one (profile, variant, stage) screening decision
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Stage1Basis:
    profile_id: str
    variant: str
    stage: str
    cohort_size: int
    k: int
    eligible_node_ids: tuple[str, ...]
    stage_node_ids: tuple[str, ...]
    delay_decision: AttentionDecision
    consequence_decision: AttentionDecision
    priority: Mapping[str, float]

    @property
    def shortlist(self) -> tuple[str, ...]:
        return tuple(
            entry.node_id
            for entry in self.consequence_decision.entries
            if entry.selected
        )

    @property
    def delay_shortlist(self) -> tuple[str, ...]:
        return tuple(
            entry.node_id for entry in self.delay_decision.entries if entry.selected
        )


def _profile_consequence_signal(
    sealed: PrioritySignal, *, score: float | None
) -> PrioritySignal:
    """The same sealed signal with the profile's consequence score.

    Identity, support state, attested common-support mass, threshold and reason
    codes are copied verbatim: only the score changes.
    """

    return PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id=sealed.episode_id,
        chain_id=sealed.chain_id,
        node_id=sealed.node_id,
        representation_id=sealed.representation_id,
        score=score,
        support=sealed.support,
        status=sealed.status,
        comparison_support_mass=sealed.comparison_support_mass,
        comparison_support_threshold=sealed.comparison_support_threshold,
        reason_codes=sealed.reason_codes,
    )


def _priority_map(decision: AttentionDecision) -> dict[str, float]:
    resolved: dict[str, float] = {}
    for entry in decision.entries:
        _require(
            entry.score is not None,
            "CONSEQUENCE_DOMAIN_EMPHASIS_ABSTAINING_CANDIDATE_IN_QUEUE",
            {"node_id": entry.node_id, "signal": str(entry.selected_for)},
        )
        resolved[entry.node_id] = float(entry.score)
    return resolved


def build_stage1_basis(
    *,
    profile: DomainWeightProfile,
    variant: str,
    stage: str,
    attention: Mapping[str, Any],
    consequence_variants: Mapping[str, Any],
) -> Stage1Basis:
    """Re-run the frozen shared selector under one profile's domain weights.

    ``P^D`` is passed through untouched, the candidate cohort and the common
    support are the sealed ones, ``q`` and the capacity rule are frozen, and the
    only changed quantity is the consequence score. For the ``BALANCED`` profile
    this reproduces the sealed screening decision exactly, which Gate B verifies.
    """

    row = decision_rows(attention, variant, stage, NOMINAL_Q)
    rows = consequence_rows_by_variant(consequence_variants, variant)
    signals = signals_by_variant(consequence_variants, variant)
    stage_node_ids = tuple(row["canonical_stage_node_ids"])
    delay_queue: list[PrioritySignal] = []
    consequence_queue: list[PrioritySignal] = []
    for node_id in stage_node_ids:
        sealed_delay, sealed_consequence = signals[node_id]
        expected_cu = rows[node_id]["expected_cu"]
        score = (
            None
            if sealed_consequence.score is None
            else float(phi_c(expected_cu, view=profile.aggregation_view))
        )
        delay_queue.append(sealed_delay)
        consequence_queue.append(
            _profile_consequence_signal(sealed_consequence, score=score)
        )
    delay_decision, consequence_decision = select_paired_attention(
        tuple(delay_queue), tuple(consequence_queue), q=NOMINAL_Q
    )
    return Stage1Basis(
        profile_id=profile.profile_id,
        variant=variant,
        stage=stage,
        cohort_size=int(consequence_decision.cohort_size),
        k=int(consequence_decision.k),
        eligible_node_ids=tuple(row["eligible_candidate_node_ids"]),
        stage_node_ids=stage_node_ids,
        delay_decision=delay_decision,
        consequence_decision=consequence_decision,
        priority=_priority_map(consequence_decision),
    )


def build_stage1_grid(
    *,
    profiles: Sequence[DomainWeightProfile],
    attention: Mapping[str, Any],
    consequence_variants: Mapping[str, Any],
) -> dict[tuple[str, str, str], Stage1Basis]:
    grid: dict[tuple[str, str, str], Stage1Basis] = {}
    for profile in profiles:
        for variant in S.PRIMARY_STATE_VARIANTS:
            for stage in STAGES:
                grid[(profile.profile_id, variant, stage)] = build_stage1_basis(
                    profile=profile,
                    variant=variant,
                    stage=stage,
                    attention=attention,
                    consequence_variants=consequence_variants,
                )
    return grid


def _attention_evaluation(
    *,
    m4: Mapping[str, Any],
    stage: str,
    reference: Stage1Basis,
    comparator: Stage1Basis,
) -> Any:
    return evaluate_attention_allocation(
        cohort_id=f"{m4['cohort_id']}_{stage}",
        reference_id=reference.variant,
        comparator_id=comparator.variant,
        reference_decision=reference.consequence_decision,
        comparator_decision=comparator.consequence_decision,
        reference_priority=dict(reference.priority),
    )


def _stage1_headline(*, balanced: Stage1Basis) -> dict[str, Any]:
    """The frozen projection's definitions, recomputed from the replayed basis."""

    priority = balanced.priority
    consequence = balanced.shortlist
    delay = balanced.delay_shortlist
    a_consequence = sum(priority[node_id] for node_id in consequence)
    a_delay = sum(priority[node_id] for node_id in delay)
    consequence_set, delay_set = set(consequence), set(delay)
    return {
        "n_g": balanced.cohort_size,
        "k_g": balanced.k,
        "a_consequence": a_consequence,
        "a_delay": a_delay,
        "delta_att": a_consequence - a_delay,
        "L_att": _ratio(a_consequence - a_delay, a_consequence),
        "eta_att": _ratio(a_delay, a_consequence),
        "changed_position_count": len(consequence_set - delay_set),
        "overlap_count": len(consequence_set & delay_set),
    }


# ----------------------------------------------------------------------
# Gate B - Stage-I Balanced replay
# ----------------------------------------------------------------------
def gate_stage1_replay(
    *,
    epoch_root: Path,
    attention: Mapping[str, Any],
    consequence_variants: Mapping[str, Any],
    m4: Mapping[str, Any],
    stage1_grid: Mapping[tuple[str, str, str], Stage1Basis],
) -> dict[str, Any]:
    """Replay the sealed Stage-I authority before any emphasis result exists."""

    rows = list(consequence_variants["rows"])
    identity_points = 0
    identity_failures: list[dict[str, Any]] = []
    max_identity_deviation = 0.0
    for row in rows:
        expected_cu = row["expected_cu"]
        sealed_score = row["consequence_signal"]["score"]
        _require(
            expected_cu is not None and sealed_score is not None,
            "CONSEQUENCE_DOMAIN_EMPHASIS_EXPECTED_CU_MISSING",
            {"node_id": row["node_id"], "variant": row["variant"]},
        )
        replay = float(phi_c(expected_cu, view=PRIMARY_AGGREGATION_VIEW))
        deviation = abs(replay - float(sealed_score))
        max_identity_deviation = max(max_identity_deviation, deviation)
        if deviation <= VALUE_TOLERANCE:
            identity_points += 1
        else:
            identity_failures.append(
                {
                    "node_id": row["node_id"],
                    "variant": row["variant"],
                    "sealed": float(sealed_score),
                    "replay": replay,
                }
            )
    _require(
        identity_points == len(rows) == EXPECTED_CONSEQUENCE_VARIANT_ROWS,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
        {
            "reason": "SEALED_CONSEQUENCE_PRIORITY_IDENTITY",
            "points_matched": identity_points,
            "points_expected": len(rows),
            "max_abs_deviation": max_identity_deviation,
            "failures": identity_failures[:8],
        },
    )

    decision_checks: dict[str, Any] = {}
    for stage in STAGES:
        basis = stage1_grid[(BALANCED_PROFILE.profile_id, REFERENCE_VARIANT, stage)]
        row = decision_rows(attention, REFERENCE_VARIANT, stage, NOMINAL_Q)
        _require(
            basis.cohort_size == int(row["cohort_size"]) == EXPECTED_STAGE1_N[stage]
            and basis.k == int(row["k"]) == EXPECTED_STAGE1_K[stage],
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
            {
                "reason": "SEALED_COHORT_OR_CAPACITY",
                "stage": stage,
                "cohort_size": basis.cohort_size,
                "k": basis.k,
                "sealed_cohort_size": row["cohort_size"],
                "sealed_k": row["k"],
            },
        )
        _require(
            set(basis.eligible_node_ids) == set(row["eligible_candidate_node_ids"]),
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
            {"reason": "SEALED_ELIGIBLE_COHORT", "stage": stage},
        )
        for signal, key, replay in (
            ("CONSEQUENCE", "consequence_decision", basis.consequence_decision),
            ("DELAY", "delay_decision", basis.delay_decision),
        ):
            sealed = attention_decision_from_payload(row[key])
            _require(
                replay.signal_type == sealed.signal_type
                and replay.cohort_size == sealed.cohort_size
                and replay.k == sealed.k
                and _close(replay.q, sealed.q),
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
                {"reason": "SEALED_DECISION_HEADER", "stage": stage, "signal": signal},
            )
            sealed_entries = {entry.node_id: entry for entry in sealed.entries}
            replay_entries = {entry.node_id: entry for entry in replay.entries}
            _require(
                set(sealed_entries) == set(replay_entries),
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
                {"reason": "SEALED_QUEUE_IDENTITY", "stage": stage, "signal": signal},
            )
            for node_id, sealed_entry in sealed_entries.items():
                replay_entry = replay_entries[node_id]
                _require(
                    replay_entry.rank == sealed_entry.rank
                    and replay_entry.selected is sealed_entry.selected
                    and _close(replay_entry.score, sealed_entry.score),
                    "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
                    {
                        "reason": "SEALED_ENTRY_MISMATCH",
                        "stage": stage,
                        "signal": signal,
                        "node_id": node_id,
                        "sealed_rank": sealed_entry.rank,
                        "replay_rank": replay_entry.rank,
                    },
                )
        decision_checks[stage] = {
            "cohort_size": basis.cohort_size,
            "k": basis.k,
            "entries_matched": len(basis.consequence_decision.entries),
            "delay_shortlist_matched": True,
            "consequence_shortlist_matched": True,
        }

    projection = _load(epoch_root / "PAPER_FACING_DELAY_VS_CONSEQUENCE_STAGE1.json")
    stage_headlines = {
        stage: _stage1_headline(
            balanced=stage1_grid[(BALANCED_PROFILE.profile_id, REFERENCE_VARIANT, stage)]
        )
        for stage in STAGES
    }
    headline_checks: dict[str, Any] = {}
    for stage in STAGES:
        sealed = projection["results"][stage]
        replay = stage_headlines[stage]
        fields = (
            "n_g",
            "k_g",
            "a_consequence",
            "a_delay",
            "L_att",
            "eta_att",
            "changed_position_count",
            "overlap_count",
        )
        mismatches = {
            field: {"sealed": sealed.get(field), "replay": replay.get(field)}
            for field in fields
            if not _close(sealed.get(field), replay.get(field))
        }
        _require(
            not mismatches,
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
            {
                "reason": "SEALED_DELAY_VS_CONSEQUENCE_HEADLINE",
                "stage": stage,
                "mismatches": mismatches,
            },
        )
        headline_checks[stage] = {field: replay[field] for field in fields}
    overall_sealed = projection["results"]["overall"]
    overall_replay = {
        "a_consequence": sum(item["a_consequence"] for item in stage_headlines.values()),
        "a_delay": sum(item["a_delay"] for item in stage_headlines.values()),
        "changed_position_count": sum(
            item["changed_position_count"] for item in stage_headlines.values()
        ),
    }
    overall_replay["L_att"] = _ratio(
        overall_replay["a_consequence"] - overall_replay["a_delay"],
        overall_replay["a_consequence"],
    )
    overall_mismatches = {
        field: {"sealed": overall_sealed.get(field), "replay": value}
        for field, value in overall_replay.items()
        if not _close(overall_sealed.get(field), value)
    }
    _require(
        not overall_mismatches,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
        {"reason": "SEALED_OVERALL_HEADLINE", "mismatches": overall_mismatches},
    )

    comparator_checks: list[dict[str, Any]] = []
    for stage in STAGES:
        reference = stage1_grid[(BALANCED_PROFILE.profile_id, REFERENCE_VARIANT, stage)]
        sealed_block = m4["attention"]["by_stage"][stage]["comparators"]
        for variant in S.COMPARATOR_VARIANTS:
            comparator = stage1_grid[(BALANCED_PROFILE.profile_id, variant, stage)]
            evaluation = _attention_evaluation(
                m4=m4, stage=stage, reference=reference, comparator=comparator
            )
            sealed = sealed_block[variant]
            _require(
                sealed.get("record_kind") == "EVALUATED",
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
                {"reason": "SEALED_COMPARATOR_TYPED", "stage": stage, "variant": variant},
            )
            mismatches: dict[str, Any] = {}
            for field, replay_value in (
                ("L_att", evaluation.L_att),
                ("reference_attention_value", evaluation.reference_attention_value),
                ("comparator_attention_value", evaluation.comparator_attention_value),
                ("kendall_tau", evaluation.kendall_tau),
                ("spearman_rho", evaluation.spearman_rho),
            ):
                if not _close(replay_value, sealed.get(field)):
                    mismatches[field] = {
                        "sealed": sealed.get(field),
                        "replay": replay_value,
                    }
            if int(sealed.get("overlap_count", -1)) != int(evaluation.overlap_count):
                mismatches["overlap_count"] = {
                    "sealed": sealed.get("overlap_count"),
                    "replay": evaluation.overlap_count,
                }
            if list(sealed.get("entered", ())) != sorted(evaluation.entered):
                mismatches["entered"] = {
                    "sealed": list(sealed.get("entered", ())),
                    "replay": sorted(evaluation.entered),
                }
            if list(sealed.get("displaced", ())) != sorted(evaluation.displaced):
                mismatches["displaced"] = {
                    "sealed": list(sealed.get("displaced", ())),
                    "replay": sorted(evaluation.displaced),
                }
            _require(
                not mismatches,
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE1_REPLAY",
                {
                    "reason": "SEALED_INFORMATION_COMPARATOR",
                    "stage": stage,
                    "variant": variant,
                    "mismatches": mismatches,
                },
            )
            comparator_checks.append(
                {
                    "stage": stage,
                    "variant": variant,
                    "L_att": evaluation.L_att,
                    "overlap_count": evaluation.overlap_count,
                }
            )

    return {
        "gate": "B",
        "status": "PASS",
        "consequence_priority_points_matched": identity_points,
        "consequence_priority_points_expected": len(rows),
        "max_abs_priority_deviation": max_identity_deviation,
        "decision_checks": decision_checks,
        "headline_checks": headline_checks,
        "overall_headline_L_att": overall_replay["L_att"],
        "information_comparators": comparator_checks,
        "replay_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": REPLAY_TOLERANCE,
            "value_tolerance_for_identity": VALUE_TOLERANCE,
        },
    }


# ----------------------------------------------------------------------
# Stage-I result tables
# ----------------------------------------------------------------------
def build_stage1_profile_rows(
    *,
    m4: Mapping[str, Any],
    stage1_grid: Mapping[tuple[str, str, str], Stage1Basis],
    emphasis_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Balanced versus emphasis shortlists, both evaluation directions."""

    rows: list[dict[str, Any]] = []
    for profile_id in emphasis_ids:
        for stage in STAGES:
            balanced = stage1_grid[(BALANCED_PROFILE.profile_id, REFERENCE_VARIANT, stage)]
            emphasis = stage1_grid[(profile_id, REFERENCE_VARIANT, stage)]
            balanced_basis = _attention_evaluation(
                m4=m4, stage=stage, reference=balanced, comparator=emphasis
            )
            profile_basis = _attention_evaluation(
                m4=m4, stage=stage, reference=emphasis, comparator=balanced
            )
            rows.append(
                {
                    "stage": stage,
                    "stage_class": STAGE_CLASS[stage],
                    "profile_id": profile_id,
                    "reference_profile_id": BALANCED_PROFILE.profile_id,
                    "N": balanced.cohort_size,
                    "K": balanced.k,
                    "shortlist_overlap_count": balanced_basis.overlap_count,
                    "shortlist_overlap_rate": _ratio(
                        balanced_basis.overlap_count, balanced.k
                    ),
                    "changed_positions": len(balanced_basis.entered),
                    "entered_count": len(balanced_basis.entered),
                    "displaced_count": len(balanced_basis.displaced),
                    "entered_node_ids": _joined(balanced_basis.entered),
                    "displaced_node_ids": _joined(balanced_basis.displaced),
                    "rank_correlation_kendall_tau": _finite_or_none(
                        balanced_basis.kendall_tau
                    ),
                    "rank_correlation_spearman_rho": _finite_or_none(
                        balanced_basis.spearman_rho
                    ),
                    "balanced_reference_value": balanced_basis.reference_attention_value,
                    "balanced_value_of_emphasis_shortlist": (
                        balanced_basis.comparator_attention_value
                    ),
                    "balanced_retained_value": _ratio(
                        balanced_basis.comparator_attention_value,
                        balanced_basis.reference_attention_value,
                    ),
                    "balanced_attention_loss": balanced_basis.L_att,
                    "profile_reference_value": profile_basis.reference_attention_value,
                    "profile_value_of_balanced_shortlist": (
                        profile_basis.comparator_attention_value
                    ),
                    "profile_retained_value": _ratio(
                        profile_basis.comparator_attention_value,
                        profile_basis.reference_attention_value,
                    ),
                    "profile_attention_loss": profile_basis.L_att,
                    "comparison_direction": (
                        "BALANCED_BASIS:REFERENCE=BALANCED,COMPARATOR="
                        f"{profile_id};PROFILE_BASIS:REFERENCE={profile_id},"
                        "COMPARATOR=BALANCED"
                    ),
                    "status": str(balanced_basis.status),
                    "reason_codes": _joined(balanced_basis.reason_codes),
                }
            )
    return rows


def build_stage1_delay_rows(
    *,
    stage1_grid: Mapping[tuple[str, str, str], Stage1Basis],
    profile_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Delay versus consequence screening inside each domain-weight profile."""

    rows: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        for stage in STAGES:
            basis = stage1_grid[(profile_id, REFERENCE_VARIANT, stage)]
            priority = basis.priority
            a_consequence = sum(priority[node_id] for node_id in basis.shortlist)
            a_delay = sum(priority[node_id] for node_id in basis.delay_shortlist)
            consequence_set = set(basis.shortlist)
            delay_set = set(basis.delay_shortlist)
            entered = sorted(delay_set - consequence_set)
            displaced = sorted(consequence_set - delay_set)
            loss = _ratio(a_consequence - a_delay, a_consequence)
            loss_note = ""
            if (
                not entered
                and not displaced
                and loss is not None
                and abs(loss) <= 1e-15
            ):
                loss_note = (
                    "MACHINE_PRECISION_ONLY_IDENTICAL_SHORTLIST_SUMMATION_ORDER_"
                    "ARTIFACT_NOT_A_DECISION_LOSS"
                )
            rows.append(
                {
                    "profile_id": profile_id,
                    "aggregation_view": PROFILE_BY_ID[profile_id].aggregation_view,
                    "stage": stage,
                    "stage_class": STAGE_CLASS[stage],
                    "N": basis.cohort_size,
                    "K": basis.k,
                    "delay_consequence_overlap": len(consequence_set & delay_set),
                    "delay_consequence_overlap_rate": _ratio(
                        len(consequence_set & delay_set), basis.k
                    ),
                    "delay_consequence_changed_positions": len(entered),
                    "delay_entered_count": len(entered),
                    "delay_displaced_count": len(displaced),
                    "delay_entered_node_ids": _joined(entered),
                    "delay_displaced_node_ids": _joined(displaced),
                    "profile_reference_consequence_value": a_consequence,
                    "delay_shortlist_consequence_value": a_delay,
                    "retained_value": _ratio(a_delay, a_consequence),
                    "attention_loss": loss,
                    "attention_loss_note": loss_note,
                    "eta_att": _ratio(a_delay, a_consequence),
                    "comparison_direction": (
                        f"REFERENCE=CONSEQUENCE({profile_id}),"
                        f"COMPARATOR=DELAY({profile_id})"
                    ),
                    "interpretation_scope": (
                        "PROFILE_SPECIFIC_DELAY_VS_CONSEQUENCE_NOT_PRIMARY_HEADLINE"
                    ),
                    "status": str(basis.consequence_decision.status),
                    "reason_codes": "",
                }
            )
    return rows


def build_stage1_information_rows(
    *,
    m4: Mapping[str, Any],
    stage1_grid: Mapping[tuple[str, str, str], Stage1Basis],
    profile_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """The headline reference structure (CJ / HP / HM versus HJ) per profile."""

    rows: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        for stage in STAGES:
            reference = stage1_grid[(profile_id, REFERENCE_VARIANT, stage)]
            for variant in S.COMPARATOR_VARIANTS:
                comparator = stage1_grid[(profile_id, variant, stage)]
                reference_candidates = {
                    entry.node_id for entry in reference.consequence_decision.entries
                }
                comparator_candidates = {
                    entry.node_id for entry in comparator.consequence_decision.entries
                }
                common = reference_candidates & comparator_candidates
                row: dict[str, Any] = {
                    "profile_id": profile_id,
                    "aggregation_view": PROFILE_BY_ID[profile_id].aggregation_view,
                    "stage": stage,
                    "stage_class": STAGE_CLASS[stage],
                    "reference_variant": REFERENCE_VARIANT,
                    "comparator_variant": variant,
                    "N_common": len(common),
                    "N_reference": len(reference_candidates),
                    "N_comparator": len(comparator_candidates),
                    "K": reference.k,
                    "comparison_direction": (
                        f"REFERENCE=CONSEQUENCE({REFERENCE_VARIANT}),"
                        f"COMPARATOR=CONSEQUENCE({variant})"
                    ),
                }
                if reference_candidates != comparator_candidates:
                    row.update(
                        {
                            "shortlist_identical": None,
                            "shortlist_set_identical": None,
                            "changed_positions": None,
                            "entered_count": None,
                            "displaced_count": None,
                            "entered_node_ids": "",
                            "displaced_node_ids": "",
                            "overlap_rate": None,
                            "reference_value": None,
                            "comparator_value": None,
                            "retained_value": None,
                            "attention_loss": None,
                            "status": "NOT_EVALUATED_COMMON_BASIS_NOT_IDENTICAL",
                            "reason_codes": (
                                "M4_ATTENTION_CANDIDATE_QUEUE_MISMATCH_MIRRORED_"
                                "NOT_INVENTED"
                            ),
                        }
                    )
                    rows.append(row)
                    continue
                evaluation = _attention_evaluation(
                    m4=m4, stage=stage, reference=reference, comparator=comparator
                )
                reference_shortlist = list(evaluation.reference_shortlist)
                comparator_shortlist = list(evaluation.comparator_shortlist)
                row.update(
                    {
                        "shortlist_identical": reference_shortlist
                        == comparator_shortlist,
                        "shortlist_set_identical": set(reference_shortlist)
                        == set(comparator_shortlist),
                        "changed_positions": len(evaluation.entered),
                        "entered_count": len(evaluation.entered),
                        "displaced_count": len(evaluation.displaced),
                        "entered_node_ids": _joined(evaluation.entered),
                        "displaced_node_ids": _joined(evaluation.displaced),
                        "overlap_rate": _ratio(evaluation.overlap_count, reference.k),
                        "reference_value": evaluation.reference_attention_value,
                        "comparator_value": evaluation.comparator_attention_value,
                        "retained_value": _ratio(
                            evaluation.comparator_attention_value,
                            evaluation.reference_attention_value,
                        ),
                        "attention_loss": evaluation.L_att,
                        "status": str(evaluation.status),
                        "reason_codes": _joined(evaluation.reason_codes),
                    }
                )
                rows.append(row)
    return rows


def build_stage1_chain_records(
    *,
    stage1_grid: Mapping[tuple[str, str, str], Stage1Basis],
    profile_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Per candidate chain, per variant, per profile: score, rank, screening."""

    records: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        for variant in S.PRIMARY_STATE_VARIANTS:
            for stage in STAGES:
                basis = stage1_grid[(profile_id, variant, stage)]
                delay_rank = {
                    entry.node_id: (int(entry.rank), bool(entry.selected))
                    for entry in basis.delay_decision.entries
                }
                for entry in basis.consequence_decision.entries:
                    rank, selected = delay_rank[entry.node_id]
                    records.append(
                        {
                            "profile_id": profile_id,
                            "aggregation_view": PROFILE_BY_ID[profile_id].aggregation_view,
                            "is_reference_variant": variant == REFERENCE_VARIANT,
                            "variant": variant,
                            "stage": stage,
                            "stage_class": STAGE_CLASS[stage],
                            "node_id": entry.node_id,
                            "chain_id": entry.chain_id,
                            "episode_id": entry.episode_id,
                            "priority_score": float(entry.score),
                            "priority_rank": int(entry.rank),
                            "priority_selected": bool(entry.selected),
                            "delay_score": float(
                                basis.delay_decision.entries[rank - 1].score
                            ),
                            "delay_rank": rank,
                            "delay_selected": selected,
                        }
                    )
    return records


# ----------------------------------------------------------------------
# Stage-II actions and objective evaluations
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Stage2Action:
    profile_id: str
    variant: str
    node_id: str
    episode_id: str
    chain_id: str
    stage: str
    u_star: float
    j_zero: float
    j_star: float
    recoverable_value: float
    u_max: float
    tie_break_applied: bool | None
    near_tie_candidate_count: int | None
    solver_status: str
    action_grid: tuple[float, ...]
    reason_codes: tuple[str, ...]


class Stage2Engine:
    """Frozen Stage-II services, parameterized only by the aggregation view."""

    def __init__(
        self,
        *,
        nodes_payload: Mapping[str, Any],
        state_variants: Mapping[str, Any],
        services: Any,
    ) -> None:
        self.nodes = nodes_by_id(nodes_payload)
        self.states = {
            variant: state_sets_by_node(state_variants, variant)
            for variant in S.PRIMARY_STATE_VARIANTS
        }
        self.services = services
        self.headroom = services.headroom_summary
        self._service_by_node: dict[str, Any] = {}
        self._context_by_node: dict[str, TransitionContext] = {}
        self._objective_cache: dict[tuple[str, str, str, float], float] = {}

    def node(self, node_id: str) -> Any:
        node = self.nodes.get(node_id)
        _require(
            node is not None,
            "CONSEQUENCE_DOMAIN_EMPHASIS_NODE_NOT_MATERIALIZED",
            node_id,
        )
        return node

    def context(self, node_id: str) -> TransitionContext:
        if node_id not in self._context_by_node:
            node = self.node(node_id)
            self._context_by_node[node_id] = TransitionContext(
                sobt_minutes=float(node.sobt_minutes),
                turnaround_lower_bound_minutes=float(
                    self.headroom.turnaround_lower_bound_q
                ),
            )
        return self._context_by_node[node_id]

    def service(self, node_id: str) -> Any:
        if node_id not in self._service_by_node:
            node = self.node(node_id)
            self._service_by_node[node_id] = self.services.consequence_service(
                {node.node_id: binding_from_node(node)}
            )
        return self._service_by_node[node_id]

    def state_set(self, *, variant: str, node_id: str) -> Any:
        state_set = self.states[variant].get(node_id)
        _require(
            state_set is not None,
            "CONSEQUENCE_DOMAIN_EMPHASIS_STATE_SET_MISSING",
            {"variant": variant, "node_id": node_id},
        )
        return state_set

    def policy(self, profile: DomainWeightProfile) -> RecoveryPolicy:
        return RecoveryPolicy(
            lambda_policy=C.NOMINAL_LAMBDA, aggregation_view=profile.aggregation_view
        ).validate()

    def solve(
        self,
        *,
        profile: DomainWeightProfile,
        variant: str,
        node_id: str,
    ) -> RecoveryDecision:
        return solve_production_recovery(
            self.state_set(variant=variant, node_id=node_id),
            context=self.context(node_id),
            service=self.service(node_id),
            headroom_summary=self.headroom,
            policy=self.policy(profile),
        )

    def objective_at(
        self,
        *,
        profile: DomainWeightProfile,
        variant: str,
        node_id: str,
        u: float,
    ) -> float:
        key = (profile.profile_id, variant, node_id, float(u))
        if key not in self._objective_cache:
            self._objective_cache[key] = float(
                expected_objective(
                    self.state_set(variant=variant, node_id=node_id),
                    context=self.context(node_id),
                    service=self.service(node_id),
                    u=float(u),
                    u_max=float(self.headroom.u_max),
                    lambda_policy=float(C.NOMINAL_LAMBDA),
                    view=profile.aggregation_view,
                )
            )
        return self._objective_cache[key]


def _stage2_action(
    *,
    profile: DomainWeightProfile,
    variant: str,
    node_id: str,
    decision: RecoveryDecision,
    engine: Stage2Engine,
) -> Stage2Action:
    node = engine.node(node_id)
    _require(
        decision.u_star is not None
        and decision.j_zero is not None
        and decision.j_star is not None
        and decision.recoverable_value is not None,
        "CONSEQUENCE_DOMAIN_EMPHASIS_DECISION_INCOMPLETE",
        {"profile_id": profile.profile_id, "variant": variant, "node_id": node_id},
    )
    return Stage2Action(
        profile_id=profile.profile_id,
        variant=variant,
        node_id=node_id,
        episode_id=str(node.episode_id),
        chain_id=str(node.chain_id),
        stage=str(node.stage),
        u_star=float(decision.u_star),
        j_zero=float(decision.j_zero),
        j_star=float(decision.j_star),
        recoverable_value=float(decision.recoverable_value),
        u_max=float(decision.u_max or 0.0),
        tie_break_applied=decision.tie_break_applied,
        near_tie_candidate_count=decision.near_tie_candidate_count,
        solver_status=str(decision.solver_status),
        action_grid=tuple(float(value) for value in decision.action_grid),
        reason_codes=tuple(str(code) for code in decision.reason_codes),
    )


def build_stage2_actions(
    *,
    profile: DomainWeightProfile,
    variant: str,
    cohort: Sequence[str],
    engine: Stage2Engine,
) -> dict[str, Stage2Action]:
    return {
        node_id: _stage2_action(
            profile=profile,
            variant=variant,
            node_id=node_id,
            decision=engine.solve(profile=profile, variant=variant, node_id=node_id),
            engine=engine,
        )
        for node_id in cohort
    }


# ----------------------------------------------------------------------
# Stage-II result tables
# ----------------------------------------------------------------------
def _taxonomy(reference_action: float, comparator_action: float) -> str:
    tolerance = 1e-9
    if abs(comparator_action - reference_action) <= tolerance:
        return "SAME_ACTION"
    if reference_action > 0.0 and comparator_action == 0.0:
        return "MISSED_ACTIVATION"
    if reference_action == 0.0 and comparator_action > 0.0:
        return "FALSE_ACTIVATION"
    if comparator_action < reference_action:
        return "UNDER_RECOVERY"
    return "OVER_RECOVERY"


def _count(value: Sequence[Any]) -> int:
    return int(len(value))


def build_stage2_hj_rows(
    *,
    cohort: Sequence[str],
    actions: Mapping[tuple[str, str], Mapping[str, Stage2Action]],
    emphasis_ids: Sequence[str],
    engine: Stage2Engine,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """HJ recovery-action sensitivity and its per-chain audit records."""

    balanced = actions[(BALANCED_PROFILE.profile_id, REFERENCE_VARIANT)]
    summary_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    for profile_id in emphasis_ids:
        profile = PROFILE_BY_ID[profile_id]
        profile_actions = actions[(profile_id, REFERENCE_VARIANT)]
        balanced_actions = {node_id: balanced[node_id].u_star for node_id in cohort}
        emphasis_actions = {node_id: profile_actions[node_id].u_star for node_id in cohort}
        balanced_values = {
            node_id: balanced[node_id].recoverable_value for node_id in cohort
        }
        profile_values = {
            node_id: profile_actions[node_id].recoverable_value for node_id in cohort
        }
        balanced_regret = evaluate_recovery_loss(
            cohort_id=f"{CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID}__{profile_id}",
            reference_id=BALANCED_PROFILE.profile_id,
            comparator_id=profile_id,
            fixed_cohort=tuple(cohort),
            reference_actions=balanced_actions,
            comparator_actions=emphasis_actions,
            reference_objectives={
                (node_id, balanced_actions[node_id]): balanced[node_id].j_star
                for node_id in cohort
            }
            | {
                (node_id, emphasis_actions[node_id]): engine.objective_at(
                    profile=BALANCED_PROFILE,
                    variant=REFERENCE_VARIANT,
                    node_id=node_id,
                    u=emphasis_actions[node_id],
                )
                for node_id in cohort
            },
            reference_recoverable_values=balanced_values,
        )
        profile_regret = evaluate_recovery_loss(
            cohort_id=f"{CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID}__{profile_id}",
            reference_id=profile_id,
            comparator_id=BALANCED_PROFILE.profile_id,
            fixed_cohort=tuple(cohort),
            reference_actions=emphasis_actions,
            comparator_actions=balanced_actions,
            reference_objectives={
                (node_id, emphasis_actions[node_id]): profile_actions[node_id].j_star
                for node_id in cohort
            }
            | {
                (node_id, balanced_actions[node_id]): engine.objective_at(
                    profile=profile,
                    variant=REFERENCE_VARIANT,
                    node_id=node_id,
                    u=balanced_actions[node_id],
                )
                for node_id in cohort
            },
            reference_recoverable_values=profile_values,
        )
        differences = [
            emphasis_actions[node_id] - balanced_actions[node_id] for node_id in cohort
        ]
        activation_agreement = _count(
            [
                node_id
                for node_id in cohort
                if (balanced_actions[node_id] > 0.0)
                == (emphasis_actions[node_id] > 0.0)
            ]
        )
        action_changed = _count(
            [value for value in differences if abs(value) > 1e-9]
        )
        summary_rows.append(
            {
                "profile_id": profile_id,
                "aggregation_view": profile.aggregation_view,
                "reference_profile_id": BALANCED_PROFILE.profile_id,
                "variant": REFERENCE_VARIANT,
                "N": len(cohort),
                "exact_action_count": balanced_regret.exact_action_count,
                "exact_action_rate": balanced_regret.A0,
                "within_five_count": balanced_regret.within_five_count,
                "within_five_rate": balanced_regret.A5,
                "activation_agreement_count": activation_agreement,
                "activation_disagreement_count": len(cohort) - activation_agreement,
                "N_action_changed": action_changed,
                "N_activation_changed": len(cohort) - activation_agreement,
                "N_increased_recovery": _count(
                    [value for value in differences if value > 1e-9]
                ),
                "N_decreased_recovery": _count(
                    [value for value in differences if value < -1e-9]
                ),
                "median_abs_action_change": float(
                    median([abs(value) for value in differences])
                ),
                "max_abs_action_change": float(
                    max([abs(value) for value in differences])
                ),
                "balanced_total_recoverable_value": sum(balanced_values.values()),
                "profile_total_recoverable_value": sum(profile_values.values()),
                "balanced_objective_regret_of_profile_action": (
                    balanced_regret.delta_recovery_objective
                ),
                "profile_objective_regret_of_balanced_action": (
                    profile_regret.delta_recovery_objective
                ),
                "primary_metric": (
                    "ACTION_AGREEMENT_AND_BIDIRECTIONAL_OBJECTIVE_REGRET"
                ),
                "recoverable_value_interpretation": (
                    "DESCRIPTIVE_ONLY_EACH_PROFILE_DEFINES_ITS_OWN_CONSEQUENCE_"
                    "OBJECTIVE_NOT_COMPARABLE_ACROSS_PROFILES"
                ),
                "status": str(balanced_regret.status),
                "reason_codes": _joined(
                    tuple(balanced_regret.reason_codes) + tuple(profile_regret.reason_codes)
                ),
            }
        )
        for node_id in cohort:
            record_rows.append(
                {
                    "record_kind": "HJ_PREFERENCE",
                    "profile_id": profile_id,
                    "aggregation_view": profile.aggregation_view,
                    "variant": REFERENCE_VARIANT,
                    "stage": profile_actions[node_id].stage,
                    "chain_id": profile_actions[node_id].chain_id,
                    "episode_id": profile_actions[node_id].episode_id,
                    "node_id": node_id,
                    "u_balanced": balanced_actions[node_id],
                    "u_profile": emphasis_actions[node_id],
                    "action_changed": abs(
                        emphasis_actions[node_id] - balanced_actions[node_id]
                    )
                    > 1e-9,
                    "action_difference_minutes": emphasis_actions[node_id]
                    - balanced_actions[node_id],
                    "taxonomy": _taxonomy(
                        balanced_actions[node_id], emphasis_actions[node_id]
                    ),
                    "balanced_objective_regret_of_profile_action": float(
                        balanced_regret.delta_objectives[node_id]
                    ),
                    "profile_objective_regret_of_balanced_action": float(
                        profile_regret.delta_objectives[node_id]
                    ),
                }
            )
    return summary_rows, record_rows


CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID = "FIXED_REFERENCE_STAGE_II_COHORT"


def build_stage2_information_rows(
    *,
    profile: DomainWeightProfile,
    cohort: Sequence[str],
    actions: Mapping[tuple[str, str], Mapping[str, Stage2Action]],
    engine: Stage2Engine,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The headline reference structure (CJ / HP / HM versus HJ) on one basis."""

    reference_actions_map = actions[(profile.profile_id, REFERENCE_VARIANT)]
    cohort_id = f"{CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID}__{profile.profile_id}"
    reference_actions = {
        node_id: reference_actions_map[node_id].u_star for node_id in cohort
    }
    reference_values = {
        node_id: reference_actions_map[node_id].recoverable_value for node_id in cohort
    }
    summary_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    for variant in S.COMPARATOR_VARIANTS:
        comparator_actions_map = actions[(profile.profile_id, variant)]
        comparator_actions = {
            node_id: comparator_actions_map[node_id].u_star for node_id in cohort
        }
        comparator_objectives = {
            (node_id, comparator_actions[node_id]): engine.objective_at(
                profile=profile,
                variant=REFERENCE_VARIANT,
                node_id=node_id,
                u=comparator_actions[node_id],
            )
            for node_id in cohort
        }
        reference_objectives = {
            (node_id, reference_actions[node_id]): reference_actions_map[node_id].j_star
            for node_id in cohort
        }
        evaluation = evaluate_recovery_loss(
            cohort_id=cohort_id,
            reference_id=REFERENCE_VARIANT,
            comparator_id=variant,
            fixed_cohort=tuple(cohort),
            reference_actions=reference_actions,
            comparator_actions=comparator_actions,
            reference_objectives=reference_objectives | comparator_objectives,
            reference_recoverable_values=reference_values,
        )
        comparator_total_reference_value = sum(
            reference_actions_map[node_id].j_zero - comparator_objectives[
                (node_id, comparator_actions[node_id])
            ]
            for node_id in cohort
        )
        total_reference_value = sum(reference_values.values())
        retained = _ratio(comparator_total_reference_value, total_reference_value)
        events = evaluation.activation_events
        summary_rows.append(
            {
                "profile_id": profile.profile_id,
                "aggregation_view": profile.aggregation_view,
                "reference_variant": REFERENCE_VARIANT,
                "comparator_variant": variant,
                "N": len(cohort),
                "exact_action_count": evaluation.exact_action_count,
                "exact_action_rate": evaluation.A0,
                "within_five_count": evaluation.within_five_count,
                "within_five_rate": evaluation.A5,
                "reference_activation_rate": evaluation.diagnostics.get(
                    "reference_activation_rate"
                ),
                "comparator_activation_rate": evaluation.diagnostics.get(
                    "comparator_activation_rate"
                ),
                "missed_activation_count": events.get("MISSED_ACTIVATION"),
                "false_activation_count": events.get("FALSE_ACTIVATION"),
                "under_recovery_count": events.get("UNDER_RECOVERY"),
                "over_recovery_count": events.get("OVER_RECOVERY"),
                "L_rec": evaluation.L_rec,
                "delta_recovery_objective": evaluation.delta_recovery_objective,
                "reference_recoverable_value": evaluation.reference_recoverable_value,
                "comparator_total_reference_value": comparator_total_reference_value,
                "retained_value": retained,
                "attention_loss": evaluation.L_rec,
                "comparison_direction": (
                    f"REFERENCE=CONSEQUENCE({REFERENCE_VARIANT}),"
                    f"COMPARATOR=CONSEQUENCE({variant})"
                ),
                "field_aliases": (
                    "attention_loss==L_rec;retained_value==1-L_rec;"
                    "exact_action_rate==A0;within_five_rate==A5"
                ),
                "status": str(evaluation.status),
                "reason_codes": _joined(evaluation.reason_codes),
            }
        )
        for node_id in cohort:
            reference_action = reference_actions[node_id]
            comparator_action = comparator_actions[node_id]
            record_rows.append(
                {
                    "record_kind": "COMPARATOR_ACTION",
                    "profile_id": profile.profile_id,
                    "aggregation_view": profile.aggregation_view,
                    "variant": variant,
                    "information_variant": variant,
                    "stage": reference_actions_map[node_id].stage,
                    "chain_id": reference_actions_map[node_id].chain_id,
                    "episode_id": reference_actions_map[node_id].episode_id,
                    "node_id": node_id,
                    "u_reference": reference_action,
                    "u_comparator": comparator_action,
                    "action_changed": abs(comparator_action - reference_action) > 1e-9,
                    "action_difference_minutes": comparator_action - reference_action,
                    "taxonomy": _taxonomy(reference_action, comparator_action),
                    "reference_regret_of_comparator_action": float(
                        evaluation.delta_objectives[node_id]
                    ),
                }
            )
    return summary_rows, record_rows


def build_stage2_profile_records(
    *,
    cohort: Sequence[str],
    actions: Mapping[tuple[str, str], Mapping[str, Stage2Action]],
    profile_ids: Sequence[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        for variant in S.PRIMARY_STATE_VARIANTS:
            for node_id in cohort:
                action = actions[(profile_id, variant)][node_id]
                records.append(
                    {
                        "record_kind": "PROFILE_ACTION",
                        "profile_id": profile_id,
                        "aggregation_view": PROFILE_BY_ID[profile_id].aggregation_view,
                        "variant": variant,
                        "information_variant": variant,
                        "stage": action.stage,
                        "chain_id": action.chain_id,
                        "episode_id": action.episode_id,
                        "node_id": node_id,
                        "u_star": action.u_star,
                        "j_zero": action.j_zero,
                        "j_star": action.j_star,
                        "recoverable_value": action.recoverable_value,
                        "activation": action.u_star > 0.0,
                        "u_max": action.u_max,
                        "tie_break_applied": action.tie_break_applied,
                        "near_tie_candidate_count": action.near_tie_candidate_count,
                        "solver_status": action.solver_status,
                    }
                )
    return records


# ----------------------------------------------------------------------
# Gate C - Stage-II Balanced replay
# ----------------------------------------------------------------------
def gate_stage2_replay(
    *,
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    engine: Stage2Engine,
    balanced_actions: Mapping[tuple[str, str], Mapping[str, Stage2Action]],
    balanced_information_rows: Sequence[Mapping[str, Any]],
    m4: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay the sealed Stage-II authority before any emphasis result exists."""

    cohort = tuple(
        str(value) for value in reference_cohort["stage2_actionable_node_ids"]
    )
    _require(
        len(cohort) == EXPECTED_STAGE2_N,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
        {"reason": "R_STAR_NOT_16", "cohort_size": len(cohort)},
    )

    # -- Level 1: the sealed HISTORY_JOINT objective curve, point by point ----
    level1_points = 0
    level1_max_deviation = 0.0
    for node_id in cohort:
        sealed = recovery_decisions["reference_objectives"][node_id]
        table = objective_by_grid(
            engine.state_set(variant=REFERENCE_VARIANT, node_id=node_id),
            context=engine.context(node_id),
            service=engine.service(node_id),
            u_max=float(engine.headroom.u_max),
            policy=engine.policy(BALANCED_PROFILE),
            floor_to_minutes=float(engine.headroom.floor_to_minutes),
        )
        sealed_grid = tuple(float(action) for action, _ in sealed["objective_by_action"])
        replay_grid = tuple(float(action) for action, _ in table)
        _require(
            sealed_grid == replay_grid,
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
            {"reason": "GRID_IDENTITY_MISMATCH", "node_id": node_id},
        )
        for (_, replay_value), (_, sealed_value) in zip(table, sealed["objective_by_action"]):
            deviation = abs(float(replay_value) - float(sealed_value))
            level1_max_deviation = max(level1_max_deviation, deviation)
            _require(
                deviation <= REPLAY_TOLERANCE,
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
                {
                    "reason": "SEALED_OBJECTIVE_POINT",
                    "node_id": node_id,
                    "sealed": float(sealed_value),
                    "replay": float(replay_value),
                },
            )
            level1_points += 1
    _require(
        level1_points == EXPECTED_STAGE2_REPLAY_POINTS,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
        {
            "reason": "LEVEL1_POINT_COUNT",
            "points": level1_points,
            "expected": EXPECTED_STAGE2_REPLAY_POINTS,
        },
    )

    # -- Level 2: the frozen default selector, per variant -------------------
    level2_cases = 0
    for variant in S.PRIMARY_STATE_VARIANTS:
        sealed_rows = recovery_rows_by_variant(recovery_decisions, variant)
        for node_id in cohort:
            sealed = recovery_decision_from_payload(sealed_rows[node_id]["decision"])
            replay = solve_production_recovery(
                engine.state_set(variant=variant, node_id=node_id),
                context=engine.context(node_id),
                service=engine.service(node_id),
                headroom_summary=engine.headroom,
            )
            mismatches: dict[str, Any] = {}
            for field in ("u_star", "j_zero", "j_star", "recoverable_value", "u_max"):
                if not _close(
                    _finite_or_none(getattr(replay, field)),
                    _finite_or_none(getattr(sealed, field)),
                ):
                    mismatches[field] = {
                        "sealed": getattr(sealed, field),
                        "replay": getattr(replay, field),
                    }
            for field in ("tie_break_applied", "near_tie_candidate_count"):
                if getattr(replay, field) != getattr(sealed, field):
                    mismatches[field] = {
                        "sealed": getattr(sealed, field),
                        "replay": getattr(replay, field),
                    }
            _require(
                not mismatches,
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
                {
                    "reason": "SEALED_ACTION",
                    "variant": variant,
                    "node_id": node_id,
                    "mismatches": mismatches,
                },
            )
            level2_cases += 1
    _require(
        level2_cases == EXPECTED_STAGE2_SEALED_CASES,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
        {
            "reason": "LEVEL2_CASE_COUNT",
            "cases": level2_cases,
            "expected": EXPECTED_STAGE2_SEALED_CASES,
        },
    )

    # -- Level 3: the profile-parameterized path at equal weights ------------
    level3_cases = 0
    for variant in S.PRIMARY_STATE_VARIANTS:
        sealed_rows = recovery_rows_by_variant(recovery_decisions, variant)
        for node_id in cohort:
            sealed = recovery_decision_from_payload(sealed_rows[node_id]["decision"])
            action = balanced_actions[(BALANCED_PROFILE.profile_id, variant)][node_id]
            _require(
                _close(action.u_star, _finite_or_none(sealed.u_star))
                and _close(action.j_zero, _finite_or_none(sealed.j_zero))
                and _close(action.j_star, _finite_or_none(sealed.j_star))
                and _close(
                    action.recoverable_value,
                    _finite_or_none(sealed.recoverable_value),
                ),
                "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
                {
                    "reason": "PROFILE_PATH_AT_EQUAL_WEIGHTS",
                    "variant": variant,
                    "node_id": node_id,
                },
            )
            level3_cases += 1

    # -- Level 4: the sealed Stage-II information comparators ----------------
    sealed_recovery = m4["recovery"]["comparators"]
    level4: list[dict[str, Any]] = []
    for row in balanced_information_rows:
        variant = row["comparator_variant"]
        sealed = sealed_recovery[variant]
        _require(
            sealed.get("record_kind") == "EVALUATED",
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
            {"reason": "SEALED_RECOVERY_COMPARATOR_TYPED", "variant": variant},
        )
        mismatches: dict[str, Any] = {}
        for field, replay_value in (
            ("L_rec", row["L_rec"]),
            ("A0", row["exact_action_rate"]),
            ("A5", row["within_five_rate"]),
            ("delta_recovery_objective", row["delta_recovery_objective"]),
            ("reference_recoverable_value", row["reference_recoverable_value"]),
        ):
            if not _close(replay_value, sealed.get(field)):
                mismatches[field] = {"sealed": sealed.get(field), "replay": replay_value}
        for field, key in (
            ("exact_action_count", "exact_action_count"),
            ("within_five_count", "within_five_count"),
        ):
            if int(sealed.get(field, -1)) != int(row[key]):
                mismatches[field] = {"sealed": sealed.get(field), "replay": row[key]}
        for event in RECOVERY_EVENT_KEYS:
            sealed_value = int(sealed.get("activation_events", {}).get(event, -1))
            replay_value = int(row[f"{event.lower()}_count"])
            if sealed_value != replay_value:
                mismatches[f"activation_events.{event}"] = {
                    "sealed": sealed_value,
                    "replay": replay_value,
                }
        _require(
            not mismatches,
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_BALANCED_STAGE2_REPLAY",
            {
                "reason": "SEALED_RECOVERY_COMPARATOR",
                "variant": variant,
                "mismatches": mismatches,
            },
        )
        level4.append({"comparator_variant": variant, "L_rec": row["L_rec"]})

    return {
        "gate": "C",
        "status": "PASS",
        "level1_points_matched": level1_points,
        "level1_points_expected": EXPECTED_STAGE2_REPLAY_POINTS,
        "level1_max_abs_deviation": level1_max_deviation,
        "level2_cases_matched": level2_cases,
        "level2_cases_expected": EXPECTED_STAGE2_SEALED_CASES,
        "level3_cases_matched": level3_cases,
        "level3_cases_expected": EXPECTED_STAGE2_SEALED_CASES,
        "level4_comparators": level4,
        "replay_path": (
            "SEALED_STATE_VARIANTS_VIA_FROZEN_M3_OBJECTIVE_AND_ENUMERATION_WITH_"
            "THE_PROFILE_PARAMETERIZED_AGGREGATION_VIEW"
        ),
    }


# ----------------------------------------------------------------------
# Gate D - primary invariance
# ----------------------------------------------------------------------
def _implementation_authority() -> dict[str, Any]:
    """Rule R1: the implementation-authority record of the edited source.

    ``model/M2/comparison_support.py`` is edited *on purpose* by this Step, so
    its pre-implementation and post-implementation hashes are not expected to
    match. The post-implementation hash recorded here is the implementation
    authority: it must stay stable for the whole analysis run.
    """

    path = C.ROOT / IMPLEMENTATION_MODIFIED_SOURCE_PATH
    return {
        "path": IMPLEMENTATION_MODIFIED_SOURCE_PATH,
        "sealed_tree_blob_canonical_lf_sha256": _git_blob_canonical_sha256(
            IMPLEMENTATION_MODIFIED_SOURCE_PATH
        ),
        "implementation_authority_file_sha256": _sha256_file(path),
        "primary_view_identifier": PRIMARY_AGGREGATION_VIEW,
        "primary_default_view_unchanged": True,
        "note": (
            "INTENTIONAL_ADDITIVE_IMPLEMENTATION_EDIT_PRE_AND_POST_HASHES_ARE_NOT_"
            "EXPECTED_TO_MATCH_BALANCED_VIEW_BRANCH_UNCHANGED"
        ),
    }


def gate_primary_invariance(
    *,
    input_paths: Mapping[str, str],
    input_hashes: Mapping[str, str],
    implementation_authority: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    authority: Mapping[str, Any],
    paper_results_before: Mapping[str, str],
    paper_results_after: Mapping[str, str],
) -> dict[str, Any]:
    """Re-assert that the sealed and frozen inputs are exactly as consumed."""

    input_mismatches = {
        name: {
            "expected": digest,
            "observed": _sha256_file(Path(input_paths[name])),
        }
        for name, digest in input_hashes.items()
        if _sha256_file(Path(input_paths[name])) != digest
    }
    _require(
        not input_mismatches,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_PRIMARY_ARTIFACT_CHANGED",
        input_mismatches,
    )
    implementation_authority_end = _sha256_file(
        C.ROOT / IMPLEMENTATION_MODIFIED_SOURCE_PATH
    )
    _require(
        implementation_authority_end
        == implementation_authority["implementation_authority_file_sha256"],
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_IMPLEMENTATION_AUTHORITY_CHANGED_DURING_RUN",
        {
            "path": IMPLEMENTATION_MODIFIED_SOURCE_PATH,
            "at_run_start": implementation_authority[
                "implementation_authority_file_sha256"
            ],
            "at_run_end": implementation_authority_end,
        },
    )
    cohort = tuple(
        str(value) for value in reference_cohort["stage2_actionable_node_ids"]
    )
    stage_by_node = {
        str(row["node_id"]): str(row["stage"])
        for row in recovery_decisions["rows"]
        if row["variant"] == REFERENCE_VARIANT
    }
    counts: dict[str, int] = {}
    for node_id in cohort:
        counts[stage_by_node[node_id]] = counts.get(stage_by_node[node_id], 0) + 1
    _require(
        len(cohort) == EXPECTED_STAGE2_N and counts == EXPECTED_STAGE2_STAGE_COUNTS,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_R_STAR_CHANGED",
        {"total": len(cohort), "by_stage": counts},
    )
    head_end = _git_head()
    _require(
        head_end == authority["head_start"],
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY",
        {
            "reason": "HEAD_CHANGED_DURING_RUN",
            "head_start": authority["head_start"],
            "head_end": head_end,
        },
    )
    changed = {
        path: {"before": paper_results_before.get(path), "after": digest}
        for path, digest in paper_results_after.items()
        if paper_results_before.get(path) != digest
    }
    changed.update(
        {
            path: {"before": digest, "after": None}
            for path, digest in paper_results_before.items()
            if path not in paper_results_after
        }
    )
    _require(
        not changed,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_PAPER_RESULTS_ROOT_MODIFIED",
        changed,
    )
    return {
        "gate": "D",
        "status": "PASS",
        "primary_balanced_artifacts_unchanged": True,
        "sealed_input_hashes_unchanged": True,
        "frozen_science_source_hashes_unchanged": True,
        "implementation_source_hashes_unchanged": True,
        "implementation_authority_unchanged_during_run": True,
        "implementation_authority_file_sha256_at_run_end": implementation_authority_end,
        "r_star_unchanged": {"total": len(cohort), "by_stage": counts},
        "nominal_q_unchanged": NOMINAL_Q,
        "head_stable": True,
        "paper_results_roots_unchanged": True,
        "paper_results_files_fingerprinted": len(paper_results_after),
        "paper_results_snapshot_digest": _snapshot_digest(paper_results_after),
    }


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def _md_table(records: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for record in records:
        cells: list[str] = []
        for column in columns:
            value = record.get(column)
            if isinstance(value, float):
                cells.append(f"{value:.6g}")
            elif value is None:
                cells.append("")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _pattern(values: Mapping[str, float | None]) -> tuple[str, ...]:
    """Exact ordering pattern of a named set of values (ties share a rank)."""

    present = {key: value for key, value in values.items() if value is not None}
    ordered = sorted(present, key=lambda key: (-float(present[key]), key))
    return tuple(ordered)


def build_exception_scan(
    *,
    profile_ids: Sequence[str],
    stage1_information_rows: Sequence[Mapping[str, Any]],
    stage2_information_rows: Sequence[Mapping[str, Any]],
    stage2_chain_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Exact ordering facts, per profile, plus the profile-level exceptions.

    No threshold is applied anywhere: every flag is an exact comparison between
    observed values, and the exceptions list names only pattern changes relative
    to the primary ``BALANCED`` reference.
    """

    stage1_pattern: dict[str, tuple[str, ...]] = {}
    stage2_pattern: dict[str, tuple[str, ...]] = {}
    facts: dict[str, Any] = {}
    for profile_id in profile_ids:
        stage1_losses = {
            str(row["comparator_variant"]): _finite_or_none(row["attention_loss"])
            for row in stage1_information_rows
            if row["profile_id"] == profile_id
        }
        stage2_losses = {
            str(row["comparator_variant"]): _finite_or_none(row["L_rec"])
            for row in stage2_information_rows
            if row["profile_id"] == profile_id
        }
        actions = [
            row
            for row in stage2_chain_records
            if row["record_kind"] == "PROFILE_ACTION"
            and row["profile_id"] == profile_id
            and row["variant"] == REFERENCE_VARIANT
        ]
        zero_action_shortlisted = sorted(
            str(row["chain_id"]) for row in actions if float(row["u_star"]) == 0.0
        )
        positive_recovery = sorted(
            str(row["chain_id"])
            for row in actions
            if float(row["recoverable_value"]) > 0.0
        )
        activated = sorted(
            str(row["chain_id"]) for row in actions if float(row["u_star"]) > 0.0
        )
        stage1_pattern[profile_id] = _pattern(stage1_losses)
        stage2_pattern[profile_id] = _pattern(stage2_losses)
        facts[profile_id] = {
            "stage1_information_loss_ordering_worst_to_best": list(
                stage1_pattern[profile_id]
            ),
            "stage2_information_loss_ordering_worst_to_best": list(
                stage2_pattern[profile_id]
            ),
            "stage2_shortlisted_chains_with_zero_action": len(zero_action_shortlisted),
            "stage2_shortlisted_chains_with_zero_action_ids": zero_action_shortlisted,
            "stage2_shortlisted_chains_with_positive_recoverable_value": len(
                positive_recovery
            ),
            "stage2_activated_chains": len(activated),
            "stage2_activated_chains_ids": activated,
        }

    reference_stage1 = stage1_pattern.get(BALANCED_PROFILE.profile_id)
    reference_stage2 = stage2_pattern.get(BALANCED_PROFILE.profile_id)
    exceptions: list[str] = []
    for profile_id in profile_ids:
        if profile_id == BALANCED_PROFILE.profile_id:
            continue
        if stage1_pattern[profile_id] != reference_stage1:
            exceptions.append(
                "STAGE1_INFORMATION_LOSS_ORDERING_CHANGED:"
                f"{profile_id}:{list(stage1_pattern[profile_id])}"
                f":BALANCED:{list(reference_stage1 or ())}"
            )
        if stage2_pattern[profile_id] != reference_stage2:
            exceptions.append(
                "STAGE2_INFORMATION_LOSS_ORDERING_CHANGED:"
                f"{profile_id}:{list(stage2_pattern[profile_id])}"
                f":BALANCED:{list(reference_stage2 or ())}"
            )
        profile_facts = facts[profile_id]
        if (
            profile_facts["stage2_shortlisted_chains_with_zero_action"] == 0
            or profile_facts["stage2_shortlisted_chains_with_positive_recoverable_value"]
            == 0
        ):
            exceptions.append(f"PRIORITY_RECOVERABILITY_DISTINCTION_ABSENT:{profile_id}")
        if profile_facts["stage2_activated_chains"] == 0:
            exceptions.append(f"ACTIVATION_COLLAPSE:{profile_id}")

    return {
        "policy": "EXACT_ORDERING_FACTS_NO_THRESHOLD_APPLIED",
        "per_profile": facts,
        "exceptions": exceptions,
    }


def render_report(
    *, manifest: Mapping[str, Any], frames: Mapping[str, pd.DataFrame]
) -> str:
    """The report is organised by managerial question, not by code module."""

    profile_rows = frames[STAGE1_PROFILE_SUMMARY_NAME].to_dict("records")
    delay_rows = frames[STAGE1_DELAY_NAME].to_dict("records")
    info_rows = frames[STAGE1_INFORMATION_NAME].to_dict("records")
    hj_rows = frames[STAGE2_HJ_ACTION_NAME].to_dict("records")
    stage2_rows = frames[STAGE2_INFORMATION_NAME].to_dict("records")
    chain_records = frames[STAGE2_RECORDS_NAME].to_dict("records")
    scan = build_exception_scan(
        profile_ids=list(manifest["weight_profiles"]),
        stage1_information_rows=info_rows,
        stage2_information_rows=stage2_rows,
        stage2_chain_records=chain_records,
    )
    gates = manifest["gates"]
    lines: list[str] = []
    lines.append("# Consequence-domain emphasis robustness (post-hoc)")
    lines.append("")
    lines.append(
        "`CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS` -- a read-only projection over "
        "the sealed canonical-v2 Final-Test epoch. Descriptive robustness only: no "
        "significance testing, no confidence interval, no threshold and no claim."
    )
    lines.append("")
    lines.append("## Declarations")
    lines.append("")
    for key in (
        "primary_profile",
        "primary_weight_profile_changed",
        "weights_reselected",
        "weights_learned",
        "weights_calibrated",
        "expert_elicitation_used",
        "model_retrained",
        "model_recalibrated",
        "parameter_reselected",
        "final_test_cohort_changed",
        "stage2_reference_cohort",
        "stage2_N",
        "stage1_q",
        "stage1_stage_q_grid_rerun",
        "consequence_components_changed",
        "component_normalization_changed",
        "bootstrap_used",
        "significance_testing_used",
        "robustness_threshold_defined",
        "decision_margin_quantities_reported",
    ):
        lines.append(f"* `{key}` = `{manifest[key]}`")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    lines.append(
        _md_table(
            [
                {
                    "gate": gates["gate_b"]["gate"],
                    "status": gates["gate_b"]["status"],
                    "evidence": (
                        f"{gates['gate_b']['consequence_priority_points_matched']}/"
                        f"{gates['gate_b']['consequence_priority_points_expected']} "
                        "sealed consequence priorities; "
                        f"{len(gates['gate_b']['information_comparators'])} sealed "
                        "Stage-I comparators; PRE 29/3, TURN 127/13"
                    ),
                },
                {
                    "gate": gates["gate_c"]["gate"],
                    "status": gates["gate_c"]["status"],
                    "evidence": (
                        f"{gates['gate_c']['level1_points_matched']}/"
                        f"{gates['gate_c']['level1_points_expected']} objective points; "
                        f"{gates['gate_c']['level2_cases_matched']}/"
                        f"{gates['gate_c']['level2_cases_expected']} sealed actions; "
                        f"{gates['gate_c']['level3_cases_matched']} profile-basis cases; "
                        f"{len(gates['gate_c']['level4_comparators'])} sealed recovery "
                        "comparators"
                    ),
                },
                {
                    "gate": gates["gate_d"]["gate"],
                    "status": gates["gate_d"]["status"],
                    "evidence": (
                        "PRIMARY_BALANCED_ARTIFACTS_UNCHANGED; R* 16 (PRE 3 / TURN 13); "
                        f"head stable {gates['gate_d']['head_stable']}; "
                        f"{gates['gate_d']['paper_results_files_fingerprinted']} "
                        "paper-result files fingerprinted unchanged"
                    ),
                },
            ],
            ["gate", "status", "evidence"],
        )
    )
    lines.append("")
    lines.append(
        "Gate A status: `"
        + ("PASS" if manifest["gate_statuses"]["gate_a_passed"] else "BLOCKED")
        + "` (unexpected tracked modifications at run start: "
        + str(len(gates["gate_a"]["preexisting_unexpected_tracked_modifications"]))
        + "; declared implementation modifications: "
        + str(len(gates["gate_a"]["preexisting_implementation_modifications"]))
        + ")."
    )
    lines.append("")
    lines.append("## A. Do domain emphases materially change the consequence shortlist?")
    lines.append("")
    lines.append(
        _md_table(
            profile_rows,
            [
                "stage",
                "profile_id",
                "N",
                "K",
                "shortlist_overlap_count",
                "shortlist_overlap_rate",
                "changed_positions",
                "entered_count",
                "displaced_count",
                "balanced_retained_value",
                "balanced_attention_loss",
                "profile_retained_value",
                "profile_attention_loss",
            ],
        )
    )
    lines.append("")
    lines.append(
        "Both directions are reported per row: the balanced basis evaluates the "
        "emphasis shortlist (`balanced_*`), and the profile basis evaluates the "
        "balanced shortlist (`profile_*`)."
    )
    lines.append("")
    lines.append("## B. Does the Delay-vs-Consequence finding persist?")
    lines.append("")
    lines.append(
        _md_table(
            delay_rows,
            [
                "stage",
                "profile_id",
                "N",
                "K",
                "delay_consequence_overlap",
                "delay_consequence_changed_positions",
                "profile_reference_consequence_value",
                "delay_shortlist_consequence_value",
                "retained_value",
                "attention_loss",
                "attention_loss_note",
            ],
        )
    )
    lines.append("")
    lines.append(
        "These `attention_loss` values are profile-specific Delay-vs-Consequence "
        "attention losses. They do **not** replace the primary `BALANCED` headline, "
        "which Gate B reproduced against the sealed projection."
    )
    lines.append("")
    lines.append("## C. Does priority remain distinct from local recoverability?")
    lines.append("")
    lines.append(
        _md_table(
            hj_rows,
            [
                "profile_id",
                "exact_action_count",
                "exact_action_rate",
                "N_action_changed",
                "N_increased_recovery",
                "N_decreased_recovery",
                "median_abs_action_change",
                "max_abs_action_change",
                "balanced_objective_regret_of_profile_action",
                "profile_objective_regret_of_balanced_action",
                "balanced_total_recoverable_value",
                "profile_total_recoverable_value",
            ],
        )
    )
    lines.append("")
    lines.append(
        _md_table(
            [
                {
                    "profile_id": profile_id,
                    **{
                        key: value
                        for key, value in facts.items()
                        if not key.endswith("_ids")
                    },
                }
                for profile_id, facts in scan["per_profile"].items()
            ],
            [
                "profile_id",
                "stage2_shortlisted_chains_with_zero_action",
                "stage2_shortlisted_chains_with_positive_recoverable_value",
                "stage2_activated_chains",
            ],
        )
    )
    lines.append("")
    lines.append(
        "Interpretation priority for this section: action agreement and the two "
        "directional objective regrets. `total_recoverable_value` is descriptive "
        "only -- each profile defines its own consequence objective, so a larger "
        "total under one profile is not superior welfare across profiles."
    )
    lines.append("")
    lines.append("## D. Does the information-value ordering persist?")
    lines.append("")
    lines.append("### Stage-I screening (`P^C` retention of each comparator shortlist)")
    lines.append("")
    lines.append(
        _md_table(
            info_rows,
            [
                "stage",
                "profile_id",
                "comparator_variant",
                "N_common",
                "K",
                "shortlist_identical",
                "changed_positions",
                "overlap_rate",
                "retained_value",
                "attention_loss",
            ],
        )
    )
    lines.append("")
    lines.append("### Stage-II local recovery (`HISTORY_JOINT` reference)")
    lines.append("")
    lines.append(
        _md_table(
            stage2_rows,
            [
                "profile_id",
                "comparator_variant",
                "N",
                "exact_action_count",
                "exact_action_rate",
                "within_five_count",
                "within_five_rate",
                "missed_activation_count",
                "false_activation_count",
                "under_recovery_count",
                "over_recovery_count",
                "L_rec",
                "delta_recovery_objective",
                "reference_recoverable_value",
                "comparator_total_reference_value",
                "retained_value",
            ],
        )
    )
    lines.append("")
    lines.append("## E. Exceptions")
    lines.append("")
    if scan["exceptions"]:
        for item in scan["exceptions"]:
            lines.append(f"* `{item}`")
    else:
        lines.append(
            "* No qualitative reversal was detected: every profile reproduces the "
            "primary information-loss ordering, the priority-versus-recoverability "
            "distinction is present in every profile, and no profile shows an "
            "activation collapse. This is an exact-ordering statement, not a "
            "thresholded robustness verdict."
        )
    lines.append("")
    lines.append("## Robustness interpretation questions")
    lines.append("")
    lines.append(
        "**RQ-R1 -- Does Delay-vs-Consequence screening retain the same qualitative "
        "stage pattern under all three domain-emphasis scenarios?** Facts: "
        + "; ".join(
            f"{row['profile_id']}/{row['stage']} overlap="
            f"{row['delay_consequence_overlap']} of {row['K']}, changed="
            f"{row['delay_consequence_changed_positions']}, retained="
            f"{row['retained_value']}"
            for row in delay_rows
        )
        + "."
    )
    lines.append("")
    lines.append(
        "**RQ-R2 -- Does the distinction between recovery priority and positive local "
        "recoverability remain present?** Facts: "
        + "; ".join(
            f"{profile_id}: shortlisted chains with u*=0 = "
            f"{facts['stage2_shortlisted_chains_with_zero_action']}, "
            "positive-recovery chains = "
            f"{facts['stage2_shortlisted_chains_with_positive_recoverable_value']}, "
            f"activated = {facts['stage2_activated_chains']}"
            for profile_id, facts in scan["per_profile"].items()
        )
        + "."
    )
    lines.append("")
    lines.append(
        "**RQ-R3 -- Does HISTORY_POINT remain materially less decision-preserving "
        "than the richer distributional representations?** Facts (Stage-II L_rec): "
        + "; ".join(
            f"{profile_id}: HP={row_hp}, HJ=0, HM={row_hm}, CJ={row_cj}"
            for profile_id in manifest["weight_profiles"]
            for row_hp, row_hm, row_cj in [
                (
                    next(
                        (
                            row["L_rec"]
                            for row in stage2_rows
                            if row["profile_id"] == profile_id
                            and row["comparator_variant"] == "HISTORY_POINT"
                        ),
                        None,
                    ),
                    next(
                        (
                            row["L_rec"]
                            for row in stage2_rows
                            if row["profile_id"] == profile_id
                            and row["comparator_variant"] == "HISTORY_MARGINAL"
                        ),
                        None,
                    ),
                    next(
                        (
                            row["L_rec"]
                            for row in stage2_rows
                            if row["profile_id"] == profile_id
                            and row["comparator_variant"] == "CURRENT_JOINT"
                        ),
                        None,
                    ),
                )
            ]
        )
        + "."
    )
    lines.append("")
    lines.append(
        "**RQ-R4 -- Does HISTORY_MARGINAL remain close to HISTORY_JOINT?** Facts: "
        + "; ".join(
            f"{profile_id}: L_rec(HM) = "
            + str(
                next(
                    (
                        row["L_rec"]
                        for row in stage2_rows
                        if row["profile_id"] == profile_id
                        and row["comparator_variant"] == "HISTORY_MARGINAL"
                    ),
                    None,
                )
            )
            + f", action agreement = "
            + str(
                next(
                    (
                        f"{row['exact_action_count']}/{row['N']}"
                        for row in stage2_rows
                        if row["profile_id"] == profile_id
                        and row["comparator_variant"] == "HISTORY_MARGINAL"
                    ),
                    "n/a",
                )
            )
            for profile_id in manifest["weight_profiles"]
        )
        + "."
    )
    lines.append("")
    lines.append("## Reading rules")
    lines.append("")
    lines.append(
        "* `BALANCED` is the only primary specification and the only primary "
        "headline; every emphasis row is a symmetric stress-test scenario."
    )
    lines.append(
        "* Field aliases: `attention_loss` equals the canonical `L_att` (Stage-I) "
        "and the canonical `L_rec` (Stage-II); `retained_value` equals "
        "`1 - attention_loss`; `exact_action_rate` is `A0` and `within_five_rate` "
        "is `A5`. Canonical names are used wherever the repository defines one."
    )
    lines.append(
        "* `RESOURCE_EMPHASIS` emphasises the `R_operating` domain. It is "
        "formula-identical to the legacy development-lane `OPERATING_EMPHASIS` "
        "view, but it is computed on the sealed M2 CU vector under the v2 "
        "aggregation interface; the two are not interchangeable."
    )
    lines.append(
        "* No stability certificate, margin, epsilon, span or perturbation "
        "quantity is produced here, and no robustness threshold is applied."
    )
    lines.append(
        "* Per-chain audit: see `DOMAIN_EMPHASIS_STAGE2_CHAIN_RECORDS.parquet` "
        "(`PROFILE_ACTION`, `COMPARATOR_ACTION`, `HJ_PREFERENCE`) and "
        "`DOMAIN_EMPHASIS_STAGE1_CHAIN_RECORDS.parquet`."
    )
    lines.append("")
    lines.append("## Interpretation boundary for the manuscript")
    lines.append("")
    lines.append(
        "> We examined three symmetric domain-emphasis scenarios that placed "
        "greater weight on flight, passenger, or operating-resource consequences "
        "while leaving the underlying consequence construction unchanged."
    )
    lines.append("")
    lines.append(
        "> These scenarios are robustness checks rather than empirically elicited "
        "airline utility weights."
    )
    lines.append("")
    lines.append(
        "* No manuscript claim is emitted by this artifact. The qualitative "
        "stability, magnitude and direction of the observed differences are "
        "reported as facts only."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# publish and orchestration
# ----------------------------------------------------------------------
def publish(
    *,
    out_dir: Path,
    frames: Mapping[str, pd.DataFrame],
    report: str,
    manifest: dict[str, Any],
) -> str:
    """Stage every artifact, then materialize the tree transactionally."""

    out_dir = Path(out_dir)
    staging = staging_path(out_dir)
    _require(
        not staging.exists(),
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_STAGING_RESIDUE",
        {"staging_path": str(staging)},
    )
    manifest["materialization_mode"] = planned_materialization_mode(out_dir)
    try:
        write_staging(staging=staging, frames=frames, report=report, out_dir=out_dir)
        hashes = {name: _sha256_file(staging / name) for name in PAYLOAD_ARTIFACTS}
        manifest["output_artifact_hashes"] = dict(hashes)
        manifest["output_artifact_tracking"] = {
            "committed_to_git": [
                name for name in PAYLOAD_ARTIFACTS if name not in LOCAL_ONLY_ARTIFACTS
            ]
            + [MANIFEST_NAME],
            "local_only_regenerable": {
                name: {
                    "path": str(out_dir / name),
                    "sha256": hashes[name],
                    "reason": (
                        "PROJECT_ARTIFACT_POLICY: paper-results roots track "
                        "CSV/JSON/MD only; row-level parquet stays local and is "
                        "reproducible by re-running this entrypoint"
                    ),
                }
                for name in LOCAL_ONLY_ARTIFACTS
            },
        }
        manifest["head_end"] = _git_head()
        manifest["head_stable"] = manifest["head_end"] == manifest["head_start"]
        _require(
            manifest["head_stable"],
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY",
            {
                "reason": "HEAD_CHANGED_DURING_RUN",
                "head_start": manifest["head_start"],
                "head_end": manifest["head_end"],
            },
        )
        tracked_modifications_end = _git_tracked_modifications()
        manifest["tracked_modifications_end"] = tracked_modifications_end
        introduced = sorted(
            set(tracked_modifications_end)
            - set(manifest["tracked_modifications_start"])
        )
        manifest["tracked_modifications_introduced_by_analysis_run"] = introduced
        _require(
            not introduced,
            "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_REPO_AUTHORITY",
            {
                "reason": "TRACKED_MODIFICATIONS_INTRODUCED_BY_ANALYSIS_RUN",
                "entries": introduced,
            },
        )
        write_manifest(staging=staging, manifest=manifest, out_dir=out_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    mode = materialize(staging=staging, out_dir=out_dir, hashes=hashes)
    _require(
        mode == manifest["materialization_mode"],
        "CONSEQUENCE_DOMAIN_EMPHASIS_MATERIALIZATION_MODE_MISMATCH",
        {"planned": manifest["materialization_mode"], "observed": mode},
    )
    return mode


def run(
    *, epoch_root: Path, out_dir: Path, profiles: Sequence[str] | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Execute Gates A-D and return the artifact frames plus the manifest."""

    epoch_root = Path(epoch_root)
    out_dir = Path(out_dir)
    _require(
        epoch_root.is_dir(),
        "CONSEQUENCE_DOMAIN_EMPHASIS_EPOCH_ROOT_MISSING",
        str(epoch_root),
    )
    scope = resolve_profile_scope(profiles)
    profile_ids = [profile.profile_id for profile in scope]
    emphasis_profiles = tuple(
        profile for profile in scope if not profile.is_primary_reference
    )

    authority = gate_repository_authority(out_dir=out_dir)
    provenance = _verify_epoch_identity(epoch_root)
    implementation_authority = _implementation_authority()
    input_paths = collect_input_paths(epoch_root)
    input_hashes = {
        name: _sha256_file(Path(path)) for name, path in input_paths.items()
    }
    source = C.ROOT / SOURCE_RELATIVE_PATH
    analysis_source_sha256 = _sha256_file(source) if source.is_file() else None
    test_source = C.ROOT / TEST_RELATIVE_PATH
    test_source_sha256 = _sha256_file(test_source) if test_source.is_file() else None
    collision = check_output_collision(
        out_dir=out_dir,
        head=authority["head_start"],
        input_hashes=input_hashes,
        analysis_source_sha256=analysis_source_sha256,
    )
    excluded = (out_dir, staging_path(out_dir), previous_path(out_dir))
    paper_results_before = paper_results_snapshot(excluded=excluded)

    services = load_frozen_services()
    store = CheckpointStore(epoch_root / "checkpoints")
    attention = store.read(S.ATTENTION_DECISIONS)
    nodes_payload = store.read(S.CANONICAL_NODES)
    consequence_variants = store.read(S.CONSEQUENCE_VARIANTS)
    m4 = store.read(S.M4_COMPARISONS)
    recovery_decisions = store.read(S.RECOVERY_DECISIONS)
    reference_cohort = store.read(S.REFERENCE_RECOVERY_COHORT)
    state_variants = store.read(S.STATE_VARIANTS)
    cohort = tuple(
        str(value) for value in reference_cohort["stage2_actionable_node_ids"]
    )

    # -- Gate B: Stage-I Balanced replay, before any emphasis result ---------
    stage1_grid = build_stage1_grid(
        profiles=(BALANCED_PROFILE,),
        attention=attention,
        consequence_variants=consequence_variants,
    )
    gate_b = gate_stage1_replay(
        epoch_root=epoch_root,
        attention=attention,
        consequence_variants=consequence_variants,
        m4=m4,
        stage1_grid=stage1_grid,
    )

    # -- Gate C: Stage-II Balanced replay ------------------------------------
    engine = Stage2Engine(
        nodes_payload=nodes_payload, state_variants=state_variants, services=services
    )
    actions: dict[tuple[str, str], dict[str, Stage2Action]] = {}
    for variant in S.PRIMARY_STATE_VARIANTS:
        actions[(BALANCED_PROFILE.profile_id, variant)] = build_stage2_actions(
            profile=BALANCED_PROFILE, variant=variant, cohort=cohort, engine=engine
        )
    balanced_information_rows, balanced_comparator_records = (
        build_stage2_information_rows(
            profile=BALANCED_PROFILE, cohort=cohort, actions=actions, engine=engine
        )
    )
    gate_c = gate_stage2_replay(
        nodes_payload=nodes_payload,
        state_variants=state_variants,
        recovery_decisions=recovery_decisions,
        reference_cohort=reference_cohort,
        engine=engine,
        balanced_actions=actions,
        balanced_information_rows=balanced_information_rows,
        m4=m4,
    )

    # -- emphasis profiles ---------------------------------------------------
    if emphasis_profiles:
        stage1_grid.update(
            build_stage1_grid(
                profiles=emphasis_profiles,
                attention=attention,
                consequence_variants=consequence_variants,
            )
        )
        for profile in emphasis_profiles:
            for variant in S.PRIMARY_STATE_VARIANTS:
                actions[(profile.profile_id, variant)] = build_stage2_actions(
                    profile=profile, variant=variant, cohort=cohort, engine=engine
                )

    emphasis_profile_ids = [profile.profile_id for profile in emphasis_profiles]
    profile_summary_rows = build_stage1_profile_rows(
        m4=m4, stage1_grid=stage1_grid, emphasis_ids=emphasis_profile_ids
    )
    delay_summary_rows = build_stage1_delay_rows(
        stage1_grid=stage1_grid, profile_ids=profile_ids
    )
    information_summary_rows = build_stage1_information_rows(
        m4=m4, stage1_grid=stage1_grid, profile_ids=profile_ids
    )
    stage1_chain_records = build_stage1_chain_records(
        stage1_grid=stage1_grid, profile_ids=profile_ids
    )
    hj_action_rows, hj_action_records = build_stage2_hj_rows(
        cohort=cohort,
        actions=actions,
        emphasis_ids=emphasis_profile_ids,
        engine=engine,
    )
    stage2_information_rows: list[dict[str, Any]] = [
        dict(row) for row in balanced_information_rows
    ]
    stage2_comparator_records: list[dict[str, Any]] = [
        dict(row) for row in balanced_comparator_records
    ]
    for profile in emphasis_profiles:
        rows, records = build_stage2_information_rows(
            profile=profile, cohort=cohort, actions=actions, engine=engine
        )
        stage2_information_rows.extend(dict(row) for row in rows)
        stage2_comparator_records.extend(dict(row) for row in records)
    stage2_chain_records = build_stage2_profile_records(
        cohort=cohort, actions=actions, profile_ids=profile_ids
    )
    stage2_chain_records.extend(hj_action_records)
    stage2_chain_records.extend(stage2_comparator_records)

    frames = {
        STAGE1_PROFILE_SUMMARY_NAME: pd.DataFrame(profile_summary_rows),
        STAGE1_DELAY_NAME: pd.DataFrame(delay_summary_rows),
        STAGE1_INFORMATION_NAME: pd.DataFrame(information_summary_rows),
        STAGE2_HJ_ACTION_NAME: pd.DataFrame(hj_action_rows),
        STAGE2_INFORMATION_NAME: pd.DataFrame(stage2_information_rows),
        STAGE1_RECORDS_NAME: pd.DataFrame(stage1_chain_records),
        STAGE2_RECORDS_NAME: pd.DataFrame(stage2_chain_records),
    }
    expected_counts = expected_row_counts(profile_ids=profile_ids)
    observed_counts = {
        name: int(len(frames[name])) for name in expected_counts
    }
    _require(
        observed_counts == expected_counts,
        "CONSEQUENCE_DOMAIN_EMPHASIS_BLOCKED_ROW_COUNT",
        {"expected": expected_counts, "observed": observed_counts},
    )

    # -- Gate D: primary invariance -----------------------------------------
    paper_results_after = paper_results_snapshot(excluded=excluded)
    gate_d = gate_primary_invariance(
        input_paths=input_paths,
        input_hashes=input_hashes,
        implementation_authority=implementation_authority,
        reference_cohort=reference_cohort,
        recovery_decisions=recovery_decisions,
        authority=authority,
        paper_results_before=paper_results_before,
        paper_results_after=paper_results_after,
    )

    manifest: dict[str, Any] = {
        "analysis_name": ANALYSIS_NAME,
        "analysis_type": ANALYSIS_TYPE,
        "experiment": ANALYSIS_NAME,
        "split": SPLIT,
        "primary_profile": BALANCED_PROFILE.profile_id,
        "primary_weight_profile": BALANCED_PROFILE.profile_id,
        "primary_weight_profile_changed": False,
        "primary_default_view_unchanged": True,
        "weight_profiles": profile_ids,
        "domain_weight_profiles": [profile.as_manifest_block() for profile in PROFILES],
        "weights_reselected": False,
        "weights_learned": False,
        "weights_calibrated": False,
        "expert_elicitation_used": False,
        "weight_search_performed": False,
        "weight_optimization_performed": False,
        "model_retrained": False,
        "model_recalibrated": False,
        "parameter_reselected": False,
        "final_test_cohort_changed": False,
        "consequence_components_changed": False,
        "component_normalization_changed": False,
        "component_availability_changed": False,
        "consequence_mapping_changed": False,
        "in_domain_aggregation_changed": False,
        "scenario_weights_changed": False,
        "effort_cost_changed": False,
        "recovery_grid_changed": False,
        "stage1_q_changed": False,
        "stage1_stage_q_grid_rerun": False,
        "stage1_pooled_stages": False,
        "stage1_q": NOMINAL_Q,
        "stage1_actionable_stages": list(STAGES),
        "stage1_selector_id": "M3_STAGE1_SHARED_SELECTOR",
        "stage1_capacity_rule": "K = ceil(q * N)",
        "stage1_tie_break": "(-score, episode_id, node_id)",
        "stage2_reference_cohort": "R_STAR",
        "stage2_cohort_id": CONSEQUENCE_DOMAIN_EMPHASIS_COHORT_ID,
        "stage2_reference_cohort_changed": False,
        "stage2_N": EXPECTED_STAGE2_N,
        "stage2_r_star_stage_counts": EXPECTED_STAGE2_STAGE_COUNTS,
        "stage2_lambda": float(C.NOMINAL_LAMBDA),
        "stage2_u_max": float(C.NOMINAL_U_MAX),
        "stage2_turnaround_lower_bound_q": float(C.NOMINAL_TURNAROUND_Q20),
        "stage2_action_floor_minutes": 5.0,
        "stage2_action_selector": "EXACT_ENUMERATION_OVER_FINITE_ACTION_GRID",
        "stage2_tie_break": "SMALLEST_U",
        "bootstrap_used": False,
        "significance_testing_used": False,
        "confidence_intervals_reported": False,
        "robustness_threshold_defined": False,
        "decision_margin_quantities_reported": False,
        "manuscript_claim_emitted": False,
        "expected_row_counts": expected_counts,
        "observed_row_counts": observed_counts,
        "row_counts_are_exact": True,
        "write_mode": WRITE_MODE,
        "partial_output_exposed": False,
        "staging_directory": str(staging_path(out_dir)),
        "manifest_self_hash_included": False,
        "manifest_self_hash_reason": "SELF_REFERENTIAL_HASH_NOT_DEFINED",
        "git_head": authority["head_start"],
        "branch": authority["branch"],
        "head_start": authority["head_start"],
        "preexisting_untracked": authority["preexisting_untracked"],
        "tracked_modifications_start": authority["tracked_modifications_start"],
        "preexisting_implementation_modifications": authority[
            "preexisting_implementation_modifications"
        ],
        "preexisting_known_test_side_effects": authority[
            "preexisting_known_test_side_effects"
        ],
        "preexisting_unexpected_tracked_modifications": authority[
            "preexisting_unexpected_tracked_modifications"
        ],
        "unexpected_tracked_modification_policy": authority[
            "unexpected_tracked_modification_policy"
        ],
        "mutation_statement": (
            "The robustness implementation extended the codebase (see "
            "preexisting_implementation_modifications), but executing the "
            "robustness analysis introduced no additional tracked modifications "
            "and did not mutate any sealed or primary artifact."
        ),
        "analysis_entrypoint": SOURCE_RELATIVE_PATH,
        "analysis_source_path": SOURCE_RELATIVE_PATH,
        "analysis_source_sha256": analysis_source_sha256,
        "test_source_path": TEST_RELATIVE_PATH,
        "test_source_sha256": test_source_sha256,
        "implementation_authority": implementation_authority,
        "implementation_source_hashes": _implementation_source_hashes(),
        "frozen_science_source_paths": list(FROZEN_SCIENCE_SOURCE_PATHS),
        "frozen_science_source_hashes": _frozen_science_source_hashes(),
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "epoch_root": str(epoch_root),
        "epoch_provenance": provenance,
        "output_collision": collision,
        "input_artifact_paths": input_paths,
        "input_artifact_hashes": input_hashes,
        "paper_results_read_only_scope": {
            "roots": list(PAPER_RESULTS_ROOTS),
            "designated_transaction_paths": [str(item) for item in excluded],
            "files_fingerprinted": len(paper_results_after),
            "snapshot_digest": _snapshot_digest(paper_results_after),
            "snapshot_unchanged_during_run": True,
            "other_paper_result_artifacts_may_be_created_changed_or_deleted": False,
        },
        "output_artifact_paths": {
            name: str(out_dir / name) for name in (*PAYLOAD_ARTIFACTS, MANIFEST_NAME)
        },
        "gates": {
            "gate_a": authority,
            "gate_b": gate_b,
            "gate_c": gate_c,
            "gate_d": gate_d,
        },
        "gate_statuses": {
            "gate_a_passed": True,
            "gate_b_passed": gate_b["status"] == "PASS",
            "gate_c_passed": gate_c["status"] == "PASS",
            "gate_d_passed": gate_d["status"] == "PASS",
        },
        "prohibited_column_policy": (
            "NO_P_VALUE_NO_CONFIDENCE_INTERVAL_NO_BOOTSTRAP_NO_PERMUTATION_NO_"
            "REGRESSION_NO_MARGIN_NO_CERTIFICATE_NO_ROBUSTNESS_THRESHOLD"
        ),
        "all_gates_passed": True,
    }
    manifest["head_stable"] = True
    return frames, manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Consequence-domain emphasis robustness over the sealed canonical-v2 "
            "Final-Test epoch (read-only)."
        )
    )
    parser.add_argument(
        "--epoch-root", type=Path, default=C.STAGE_MATCHED_FINAL_TEST_ROOT
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=C.ROOT
        / "artifacts"
        / "paper_results_v2_final_test_rmb"
        / "consequence_domain_emphasis_robustness",
    )
    parser.add_argument(
        "--profiles",
        type=str,
        default=None,
        help=(
            "comma-separated profile ids; BALANCED is always included "
            f"(known: {', '.join(ALL_PROFILE_IDS)})"
        ),
    )
    args = parser.parse_args(argv)
    profiles = None if args.profiles is None else args.profiles.split(",")

    out_dir = Path(args.out_dir)
    frames, manifest = run(
        epoch_root=Path(args.epoch_root), out_dir=out_dir, profiles=profiles
    )
    assert_no_prohibited_columns(frames=frames)
    manifest["materialization_mode"] = planned_materialization_mode(out_dir)
    report = render_report(manifest=manifest, frames=frames)
    mode = publish(out_dir=out_dir, frames=frames, report=report, manifest=manifest)
    for name in (*PAYLOAD_ARTIFACTS, MANIFEST_NAME):
        print(f"wrote {out_dir / name}")
    print(f"materialization mode: {mode}")
    print(f"gate B: {manifest['gates']['gate_b']['status']}")
    print(f"gate C: {manifest['gates']['gate_c']['status']}")
    print(f"observed row counts: {manifest['observed_row_counts']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ALL_PROFILE_IDS",
    "ANALYSIS_NAME",
    "ANALYSIS_TYPE",
    "BALANCED_PROFILE",
    "CheckFailure",
    "EMPHASIS_PROFILE_IDS",
    "MANIFEST_NAME",
    "PAYLOAD_ARTIFACTS",
    "PROFILES",
    "REPORT_NAME",
    "STAGE1_DELAY_NAME",
    "STAGE1_INFORMATION_NAME",
    "STAGE1_PROFILE_SUMMARY_NAME",
    "STAGE1_RECORDS_NAME",
    "STAGE2_HJ_ACTION_NAME",
    "STAGE2_INFORMATION_NAME",
    "STAGE2_RECORDS_NAME",
    "Stage1Basis",
    "Stage2Engine",
    "assert_no_prohibited_columns",
    "build_exception_scan",
    "build_stage1_basis",
    "build_stage1_chain_records",
    "build_stage1_delay_rows",
    "build_stage1_grid",
    "build_stage1_information_rows",
    "build_stage1_profile_rows",
    "build_stage2_actions",
    "build_stage2_hj_rows",
    "build_stage2_information_rows",
    "build_stage2_profile_records",
    "check_output_collision",
    "expected_row_counts",
    "gate_primary_invariance",
    "gate_repository_authority",
    "gate_stage1_replay",
    "gate_stage2_replay",
    "main",
    "materialize",
    "paper_results_snapshot",
    "previous_path",
    "publish",
    "render_report",
    "resolve_profile_scope",
    "run",
    "staging_path",
    "write_manifest",
    "write_staging",
]
