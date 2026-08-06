from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class RunProfile:
    run_profile: str
    data_design_id: str
    source_semantics: str
    episode_interval: tuple[str, str]
    outcome_buffer: str
    full_scope_type: str | None
    full_start_date: str | None
    full_end_date: str | None
    required_hour_coverage: int
    required_airport_coverage: int
    allow_partial_day: bool
    executable_now: bool


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_profiles(root: Path) -> tuple[dict[str, RunProfile], dict[str, object]]:
    formal72 = root / "data/manifests/formal_72_day_manifest.csv"
    current = root / "data/manifests/current_data_adapt_full_manifest.csv"
    profiles = {
        "fast": RunProfile(
            "fast", "FAST_CURRENT_UNCHANGED_V1", "existing fast selection unchanged",
            ("2022-05-02", "2022-05-31"), "successor outcome outside episode interval allowed",
            None, None, None, 24, 6, False, True,
        ),
        "middle": RunProfile(
            "middle", "FORMAL_72_V1_20260724", "legacy 72-day full calendar migrated without resampling",
            ("calendar-defined", "calendar-defined"), "separate successor observation buffer",
            None, None, None, 24, 19, False, False,
        ),
        "full": RunProfile(
            "full", "FULL_ALL_AVAILABLE_OR_CONTIGUOUS_MONTHS_V1", "all eligible data or predeclared contiguous complete months",
            ("predeclared", "predeclared"), "separate successor observation buffer",
            "all_available", None, None, 24, 19, False, False,
        ),
    }
    mapping = {
        "legacy_full72": "middle",
        "legacy_full_when_72_day": "middle",
        "fast": "fast",
        "new_full": "full",
        "formal_72_manifest": str(formal72),
        "formal_72_manifest_sha256": sha256(formal72),
        "current_manifest": str(current),
        "current_manifest_sha256": sha256(current),
        "warning": "The formal CLIs are not changed in this audit; migration is a prototype contract only.",
    }
    return profiles, mapping


def write_profiles(root: Path, output: Path) -> dict[str, object]:
    profiles, mapping = build_profiles(root)
    output.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": {key: asdict(value) for key, value in profiles.items()}, "legacy_mapping": mapping}
    (output / "run_profile_contracts.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
