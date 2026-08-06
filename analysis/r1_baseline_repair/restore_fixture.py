from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


MODULES = ("overall_run", "overall_adv", "part_adv")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def validate_historical_registries(source: Path) -> dict[str, Any]:
    results: dict[str, Any] = {}
    failures: list[str] = []
    for module in MODULES:
        root = source / module / "fast"
        registry_path = root / "artifact_registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        checked = 0
        for entry in registry.get("artifacts", []):
            relative = str(entry.get("relative_path") or entry["artifact_name"])
            path = root / Path(relative)
            if not path.is_file():
                failures.append(f"{module}:MISSING:{relative}")
                continue
            actual = sha256(path)
            if actual != entry.get("sha256"):
                failures.append(f"{module}:HASH_MISMATCH:{relative}")
                continue
            checked += 1
        results[module] = {
            "run_id": registry.get("run_id"),
            "config_hash": registry.get("config_hash"),
            "registry_entry_count": len(registry.get("artifacts", [])),
            "registry_entries_verified": checked,
            "registry_sha256": sha256(registry_path),
        }
    if failures:
        raise RuntimeError("HISTORICAL_REGISTRY_VALIDATION_FAILED:" + "|".join(failures))
    return results


def write_inventory(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "relative_path",
                "size_bytes",
                "source_sha256",
                "destination_sha256",
                "copy_status",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(f"FIXTURE_DESTINATION_ALREADY_EXISTS:{destination}")

    registry_results = validate_historical_registries(source)
    source_rows = inventory(source)
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    destination_rows = inventory(destination)

    source_by_path = {row["relative_path"]: row for row in source_rows}
    destination_by_path = {row["relative_path"]: row for row in destination_rows}
    all_paths = sorted(set(source_by_path) | set(destination_by_path))
    comparison = []
    for relative in all_paths:
        left = source_by_path.get(relative)
        right = destination_by_path.get(relative)
        status = "PASS" if left == right else "FAIL"
        comparison.append(
            {
                "relative_path": relative,
                "size_bytes": left["size_bytes"] if left else right["size_bytes"],
                "source_sha256": left["sha256"] if left else "MISSING",
                "destination_sha256": right["sha256"] if right else "MISSING",
                "copy_status": status,
            }
        )
    write_inventory(args.inventory, comparison)

    failures = [row["relative_path"] for row in comparison if row["copy_status"] != "PASS"]
    payload = {
        "status": "PASS" if not failures else "FAIL_FIXTURE_PROVENANCE",
        "source": str(source),
        "destination": str(destination),
        "file_count": len(source_rows),
        "total_bytes": sum(int(row["size_bytes"]) for row in source_rows),
        "copy_mismatch_count": len(failures),
        "copy_mismatches": failures,
        "historical_registries": registry_results,
    }
    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
