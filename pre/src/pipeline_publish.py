from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:
    pq = None

from .input import object_hash, sha256_file, write_parquet
from .target_contract import FORMAL_TARGET_COLUMN, target_contract_metadata
from .validate import PreBundle


def _output_hashes(root: Path) -> dict[str, str]:
    names = ["episodes", "snapshots", "calibration", "rules", "evidence_audit"]
    return {name: sha256_file(root / f"{name}.parquet") for name in names}


def _stable_id(*values: Any) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()[:24]


def _enrich_contract(bundle: PreBundle, cfg: dict[str, Any]) -> PreBundle:
    """Publish the v3 facts required downstream without changing raw-source semantics."""
    episodes = bundle.episodes.copy()
    episodes["anchor_date"] = pd.to_datetime(episodes["firstseen_utc"], utc=True).dt.strftime("%Y-%m-%d")
    episodes["departure_airport"] = episodes["origin"]
    episodes["arrival_airport"] = episodes["destination"]
    episodes["aircraft_id"] = episodes["icao24"]
    episodes["planned_departure_time"] = pd.NaT
    episodes["planned_arrival_time"] = pd.NaT
    episodes["realized_departure_time"] = episodes["firstseen_utc"]
    episodes["realized_arrival_time"] = episodes["lastseen_utc"]
    episodes["m1_outcome_label"] = episodes[FORMAL_TARGET_COLUMN]
    episodes["subset_role"] = episodes["split"].map({"train": "model", "validation": "audit", "test": "final_test"}).fillna("excluded")
    episodes["train_eligible"] = episodes["episode_valid"].fillna(False) & episodes["split"].eq("train")
    episodes["evaluation_only"] = episodes["episode_valid"].fillna(False) & ~episodes["split"].eq("train")
    episodes["formal_eligible"] = episodes["episode_valid"].fillna(False)
    episodes["debug_only"] = cfg["mode"] == "fast"
    episodes["trigger_event_group_id"] = [
        _stable_id(d, a) for d, a in zip(episodes["anchor_date"], episodes["airport"])
    ]
    episodes["recovery_event_level"] = "AIRPORT_DAY"

    snapshots = bundle.snapshots.copy()
    episode_cols = episodes[["episode_id", "flight_id", "aircraft_id", "anchor_date", "trigger_event_group_id", "formal_eligible", "debug_only"]]
    # ``_formal_frame`` deliberately creates missing contract columns as null
    # placeholders.  Remove those placeholders before joining the episode
    # authority table; otherwise pandas suffixes the authoritative values and
    # leaves the published canonical columns null.
    snapshots = snapshots.drop(
        columns=[column for column in episode_cols.columns if column != "episode_id" and column in snapshots.columns]
    )
    snapshots = snapshots.merge(episode_cols, on="episode_id", how="left", validate="many_to_one")
    snapshots["snapshot_time"] = snapshots["decision_time_utc"]
    snapshots["airport_id"] = snapshots["airport"]
    snapshots["source_available"] = ~snapshots["state_source_coverage_status"].eq("SOURCE_COVERAGE_GAP")
    snapshots["state_history_available"] = snapshots["state_record_count"].fillna(0).gt(0)
    snapshots["aircraft_sequence_available"] = snapshots["continuity_exposure"].notna()
    snapshots["passenger_handling_available"] = snapshots["estimated_passenger_load"].notna()
    snapshots["state_missing"] = ~snapshots["state_history_available"]
    snapshots["weather_missing"] = ~snapshots["weather_observed"].fillna(False)
    snapshots["flow_missing"] = snapshots["airport_flow_pressure"].isna()
    snapshots["passenger_proxy_missing"] = snapshots["estimated_passenger_load"].isna()
    passenger_supported = (
        snapshots[
            [
                "estimated_passenger_load",
                "connection_pressure_proxy",
                "rebooking_scarcity_proxy",
            ]
        ]
        .notna()
        .all(axis=1)
        & pd.to_numeric(
            snapshots["passenger_proxy_support"], errors="coerce"
        ).gt(0)
        & snapshots["passenger_proxy_evidence_status"].isin(
            ["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]
        )
    )
    snapshots["m4_passenger_input_supported"] = passenger_supported
    snapshots["m4_eligible"] = passenger_supported
    snapshots["m4_ineligibility_reason"] = np.where(
        passenger_supported, "", "PASSENGER_PROXY_UNSUPPORTED"
    )
    snapshots["reference_level"] = snapshots["passenger_proxy_level"].fillna("MISSING")
    snapshots["fallback_level"] = snapshots["passenger_proxy_fallback_reason"].fillna("")
    snapshots["exclusion_reason"] = snapshots["snapshot_exclusion_reason"]

    rules = bundle.rules.copy()
    rules["airport_resource_available"] = rules["resource_available_r"]
    rules["aircraft_sequence_available"] = rules["resource_available_f"]
    rules["passenger_handling_available"] = rules["resource_available_p"]
    rules["deprecated_alias_mapping_version"] = "legacy-fpr-to-afp-v1"

    audit = bundle.evidence_audit
    audit["source_name"] = audit["source"]
    audit["source_available"] = ~audit["evidence_status"].isin(["UNOBSERVED", "UNSUPPORTED"])
    audit["observation_age"] = (pd.to_datetime(audit["decision_time"], utc=True) - pd.to_datetime(audit["event_time"], utc=True)).dt.total_seconds() / 60.0
    audit["interpolation_used"] = ~audit["imputation_status"].eq("NOT_IMPUTED")
    audit["proxy_level"] = np.where(
        audit["evidence_status"].isin(["AGGREGATE_PROXY", "SUPPORTED_PROXY", "FALLBACK_PROXY"]),
        audit["fallback_level"],
        "NONE",
    )
    audit["reference_level"] = audit["fallback_level"]
    audit = audit.drop(
        columns=[column for column in ["formal_eligible", "debug_only", "exclusion_reason"] if column in audit.columns]
    )
    audit = audit.merge(episodes[["episode_id", "formal_eligible", "debug_only", "exclusion_reason"]], on="episode_id", how="left", validate="many_to_one")
    return PreBundle(episodes, snapshots, bundle.calibration.copy(), rules, audit)


def _write_fast_manifest(bundle: PreBundle, paths: dict[str, Path], cfg: dict[str, Any]) -> pd.DataFrame:
    ep = bundle.episodes
    manifest = ep.groupby(["anchor_date", "split", "subset_role"], as_index=False, observed=True).agg(
        episode_count=("episode_id", "count"), formal_eligible=("formal_eligible", "all")
    )
    manifest["debug_only"] = cfg["mode"] == "fast"
    manifest["formal_result"] = False if cfg["mode"] == "fast" else True
    manifest["selection_reason"] = "DATE_SOURCE_COMPLETENESS_FROZEN_FAST" if cfg["mode"] == "fast" else "FROZEN_FORMAL_MANIFEST"
    manifest["selection_seed"] = int(cfg["base_seed"])
    name = "fast_subset_manifest" if cfg["mode"] == "fast" else "model_subset"
    write_parquet(manifest, paths["manifests"] / f"{name}.parquet")
    manifest.to_csv(paths["manifests"] / f"{name}.csv", index=False)
    return manifest


def _artifact_registry(root: Path, cfg: dict[str, Any], stage: str) -> dict[str, Any]:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"artifact_registry.json", "run_state.json"}:
            continue
        rows = None
        if path.suffix == ".parquet":
            rows = int(pq.ParquetFile(path).metadata.num_rows) if pq is not None else None
        entries.append({
            "artifact_name": path.stem,
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "row_count": rows,
            "schema_version": cfg["schema_version"],
            "contract_version": "pre-contract-v3",
            "parameter_version": cfg["project_version"],
            "input_hash": object_hash(cfg.get("raw_hashes", {})),
            "config_hash": cfg["config_hash"],
            "implementation_hash": sha256_file(Path(__file__)),
            "mode": cfg["mode"],
            "created_by_stage": stage,
            "created_at": str(pd.Timestamp.now(tz="UTC")),
        })
    return {
        "mode": cfg["mode"],
        **target_contract_metadata(cfg),
        "formal_target_contract": "PASS",
        "artifacts": entries,
        "stale_artifacts": 0,
    }


def _validate_published_target_metadata(root: Path, cfg: dict[str, Any]) -> None:
    expected = target_contract_metadata(cfg)
    metadata_paths = {
        "run_summary": root / "run_summary.json",
        "acceptance": root / "acceptance.json",
        "artifact_registry": root / "artifact_registry.json",
    }
    for name, path in metadata_paths.items():
        if not path.exists():
            raise FileNotFoundError(f"FORMAL_TARGET_CONTRACT_BLOCKED: missing {name}: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for field, value in expected.items():
            if payload.get(field) != value:
                raise ValueError(
                    f"FORMAL_TARGET_CONTRACT_BLOCKED: {name}.{field}="
                    f"{payload.get(field)!r}, expected {value!r}"
                )
        if payload.get("formal_target_contract") != "PASS":
            raise ValueError(f"FORMAL_TARGET_CONTRACT_BLOCKED: {name} does not declare PASS")


def _write_bundle(bundle: PreBundle, paths: dict[str, Path]) -> None:
    for name, frame in bundle.tables().items():
        write_parquet(frame, paths["root"] / f"{name}.parquet")


def _publish(staging: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    backup = output / f".backup-{uuid.uuid4().hex[:8]}"
    backup.mkdir(parents=True, exist_ok=True)
    targets = [
        "episodes.parquet", "snapshots.parquet", "calibration.parquet", "rules.parquet",
        "evidence_audit.parquet", "intermediate", "artifacts", "manifests", "reports", "checkpoints",
        "artifact_registry.json", "run_state.json", "run_summary.json",
        "acceptance.json",
        "passenger_support_by_split.parquet",
        "passenger_support_by_airport.parquet",
        "passenger_support_by_source_period.parquet",
        "passenger_fallback_distribution.parquet",
        "fast_month_selection_audit.csv",
        "PASSENGER_MONTH_FAST_REPORT.md",
        "PASSENGER_MONTH_FAST_SUMMARY.json",
    ]
    moved_old: list[str] = []
    moved_new: list[str] = []
    try:
        for name in targets:
            old = output / name
            if old.exists():
                old.rename(backup / name)
                moved_old.append(name)
        for name in targets:
            new = staging / name
            if new.exists():
                new.rename(output / name)
                moved_new.append(name)
        # External process redirection may keep console log handles open on
        # Windows. Preserve that directory and merge only the pipeline log.
        new_logs = staging / "logs"
        if new_logs.exists():
            destination_logs = output / "logs"
            destination_logs.mkdir(parents=True, exist_ok=True)
            for source in new_logs.iterdir():
                destination = destination_logs / source.name
                if destination.exists():
                    try:
                        destination.unlink()
                    except PermissionError:
                        # A caller may be teeing console output to run.log on
                        # Windows.  Keep that live external log; all formal
                        # artifacts have already been moved atomically.
                        if source.name == "run.log":
                            continue
                        raise
                source.rename(destination)
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        for name in reversed(moved_new):
            current = output / name
            if current.exists():
                # Restore newly published artifacts to staging so a publish
                # failure never destroys an otherwise completed long run.
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                current.rename(destination)
        for name in reversed(moved_old):
            saved = backup / name
            if saved.exists():
                saved.rename(output / name)
        raise


