"""Rebuild the narrow semantic-audit source index; reads no protected splits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


REPO_FILES = (
    "REPOSITORY_AUTHORITY.md",
    "docs/HUMAN_DECISION_LOG.md",
    "docs/V2_FREEZE_PRECHECK_REPORT.md",
    "model/PRE/transform/rules.py",
    "model/M1/semantics.py",
    "model/M1/contracts.py",
    "model/M1/scenario_layer/sampler.py",
    "model/M1/marginal_distribution.py",
    "model/M2/consequence_service.py",
    "model/M2/context.py",
    "model/M2/comparison_support.py",
    "model/M2/cu/registry.py",
    "registries/m2_data2_formal_cu_v1.json",
    "model/M3/transition.py",
    "model/M3/stage1.py",
    "model/M3/stage2.py",
    "model/M4/evaluation.py",
    "validation/v2_phase5/common.py",
    "exp/jatm_section5/contracts.py",
    "exp/jatm_section5/recovery_value.py",
    "exp/jatm_s34/annual_bridge.py",
    "exp/jatm_s34/annual_cu.py",
    "exp/jatm_s34/annual_tail.py",
    "exp/jatm_s34/canonical_preselection.py",
    "exp/jatm_s34/exact_stream.py",
    "exp/jatm_s34/shared_science.py",
    "exp/jatm_s34/shared_populations.py",
    "exp/jatm_s34/shared_actions.py",
    "exp/jatm_s34/shared_statistics.py",
    "exp/jatm_s34/shared_run.py",
    "exp/jatm_s34/e1_shared_evaluation.py",
    "exp/jatm_s34/e4_shared_aggregate.py",
    "exp/jatm_s34/mechanisms.py",
    "exp/jatm_s34/scientific_tracks.py",
    "exp/jatm_s34/policy_sensitivity.py",
    "data2/scripts/build_year_references.py",
    "tests/contract/test_jatm_p0_acceptance.py",
    "tests/contract/test_jatm_p1_closure.py",
    "artifacts/experiment/jatm_s34/shared_cloud_delivery_20261012/LEGACY_2017_CLASSIFICATION.json",
    "artifacts/experiment/jatm_s34/independent_review_p0_20261012/ANNUAL_GAPS_CURRENT.json",
    "artifacts/experiment/jatm_s34/independent_review_p0_20261012/current_tail_golden/NUMERICAL_EQUIVALENCE.json",
    "artifacts/experiment/jatm_s34/annual_2017_bounded_v2_20261012/E1/E1_SUMMARY.json",
    "artifacts/experiment/jatm_s34/annual_2017_bounded_v2_20261012/SHARED_V1/SHARED_ANNUAL_MANIFEST.json",
    "artifacts/experiment/jatm_s34/shared_cloud_integration_20261012/shared/CACHE_MANIFEST.json",
    "artifacts/experiment/jatm_s34/e2_e3_exact_development_v2/E2_E3_SUMMARY.json",
    "artifacts/experiment/jatm_s34/independent_review_p0_20261012/real_cache_final/evaluation/E2_E3_SUMMARY.json",
    "tmp/p1_cached_acceptance_probe.json",
    "tmp/p1_policy_cached_acceptance_probe.json",
)

ARCHIVES = {
    "initial_archive": "Rolling_Airline_Recovery.zip",
    "corrected_20260825": "Rolling_Airline_Recovery_full_corrected_20260825.zip",
    "intermediate_8": "Rolling_Airline_Recovery (8).zip",
    "current_62": "Rolling_Airline_Recovery (62).zip",
}

EXCERPT_RANGES = {
    "initial_archive": {"sections/04_implement.tex": ((57, 64), (126, 140))},
    "corrected_20260825": {"sections/04_implement.tex": ((90, 90), (197, 210), (297, 297))},
    "intermediate_8": {"sections/04_implement.tex": ((206, 219),)},
    "current_62": {
        "sections/03_methodology.tex": ((41, 45), (84, 98), (124, 149), (188, 197)),
        "sections/04_implement.tex": ((35, 49), (76, 89), (123, 135)),
        "sections/05_experiment.tex": ((90, 95), (174, 199)),
        "SUPPLEMENT.tex": ((148, 160), (192, 211), (279, 292), (304, 313)),
    },
}


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def run(repo: Path, archives: Path, output: Path) -> None:
    repo, archives, output = repo.resolve(), archives.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for rel in REPO_FILES:
        p = repo / rel
        files[rel] = (
            {"status": "PRESENT", "bytes": p.stat().st_size, "sha256": hash_bytes(p.read_bytes())}
            if p.is_file()
            else {"status": "MISSING"}
        )
    archive_rows, excerpts = {}, {}
    for key, name in ARCHIVES.items():
        p = archives / name
        if not p.is_file():
            archive_rows[key] = {"status": "MISSING", "path": str(p)}
            continue
        archive_rows[key] = {
            "status": "PRESENT", "path": str(p), "bytes": p.stat().st_size,
            "sha256": hash_bytes(p.read_bytes()), "sections": {},
        }
        excerpts[key] = {}
        with zipfile.ZipFile(p) as z:
            for section, spans in EXCERPT_RANGES[key].items():
                data = z.read(section)
                archive_rows[key]["sections"][section] = hash_bytes(data)
                lines = data.decode("utf-8").splitlines()
                excerpts[key][section] = [
                    {"line": i, "text": lines[i - 1]}
                    for first, last in spans
                    for i in range(first, min(last, len(lines)) + 1)
                ]
    historical_commits = {}
    for commit, rel, needles in (
        (
            "8aa01f9866d12fd7cdf01148087db7e5fb688b8b",
            "model/M2/drivers.py",
            ("F_continuity", "turnaround_compression", "rib -"),
        ),
        (
            "1acfd29e3142d4bc5e9830aa875c544f89761962",
            "registries/m2_data2_formal_cu_v1.json",
            ("F_continuity", "turnaround_compression", "R_IB - turnaround_reference"),
        ),
    ):
        data = subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=repo)
        lines = data.decode("utf-8").splitlines()
        historical_commits[f"{commit}:{rel}"] = {
            "sha256": hash_bytes(data),
            "matched_lines": [
                {"line": i, "text": text}
                for i, text in enumerate(lines, 1)
                if any(needle in text for needle in needles)
            ],
        }
    excerpts["git_snapshots"] = historical_commits
    excerpt_path = output / "HISTORICAL_EXCERPTS.json"
    excerpt_path.write_bytes((json.dumps(excerpts, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    index = {
        "schema_version": "JATM_P1_SEMANTIC_SOURCE_INDEX_V1",
        "git_head_at_generation": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "scope": "SOURCE_AND_EXISTING_DEVELOPMENT_EVIDENCE_ONLY",
        "repo_files": files,
        "manuscript_archives": archive_rows,
        "historical_excerpts_sha256": hash_bytes(excerpt_path.read_bytes()),
        "active_model_retrained": False,
        "full_annual_experiment_run": False,
        "cloud_connected": False,
        "final_test_access_count_this_audit": 0,
    }
    index_path = output.parent / "EVIDENCE_INDEX.json"
    index_path.write_bytes((json.dumps(index, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.repo, args.archives, args.output)
