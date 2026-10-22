"""Shared annual compact data for E1--E3 evaluation.

This adapter consumes already materialized bounded E1 chunks.  It does not
implement a second M1--M4 model.  Canonical identity is resolved before any
support filtering, preserving the frozen ``(decision_time, node_id)`` rule.
The resulting compact table is intentionally explicit about representations
that were not present in the source chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA_VERSION = "JATM_S34_SHARED_ANNUAL_V1"
NODE_SCHEMA_VERSION = "JATM_S34_SHARED_NODE_V1"
REQUIRED_REPRESENTATIONS = (
    "HISTORY_JOINT",
    "CURRENT_JOINT",
    "HISTORY_POINT",
    "HISTORY_MARGINAL_EXACT",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _json_hash(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SharedNodeRecord:
    episode_id: str
    chain_id: str
    node_id: str
    stage: str
    decision_time: str
    delay_score: float | None
    consequence_score: float | None
    domain_scores: dict
    support: dict
    exposure: dict | None
    source_chunk: str
    representations: dict[str, str]

    def as_dict(self) -> dict:
        return {
            "schema_version": NODE_SCHEMA_VERSION,
            "episode_id": self.episode_id,
            "chain_id": self.chain_id,
            "node_id": self.node_id,
            "stage": self.stage,
            "decision_time": self.decision_time,
            "delay_score": self.delay_score,
            "consequence_score": self.consequence_score,
            "domain_scores": self.domain_scores,
            "support": self.support,
            "exposure": self.exposure,
            "source_chunk": self.source_chunk,
            "representations": self.representations,
        }


def _decision_key(record: SharedNodeRecord) -> tuple[datetime, str]:
    return datetime.fromisoformat(record.decision_time), record.node_id


def _iter_chunk_paths(chunks_root: Path) -> list[Path]:
    paths = sorted(chunks_root.glob("chunk_*.json"))
    if not paths:
        raise FileNotFoundError(f"SHARED_ANNUAL_CHUNKS_MISSING:{chunks_root}")
    expected = list(range(len(paths)))
    actual = [int(path.stem.split("_")[-1]) for path in paths]
    if actual != expected:
        raise ValueError(f"SHARED_ANNUAL_CHUNKS_NONCONTIGUOUS:{actual[:8]}")
    return paths


def iter_e1_compact_nodes(chunks_root: Path, *, year: int) -> Iterator[SharedNodeRecord]:
    """Read legacy E1 chunks with strict source and ordering checks."""

    chunks_root = Path(chunks_root).resolve()
    input_hashes: dict | None = None
    for path in _iter_chunk_paths(chunks_root):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("complete") is not True:
            raise ValueError(f"SHARED_ANNUAL_INCOMPLETE_CHUNK:{path.name}")
        if int(payload.get("year")) != int(year):
            raise ValueError(f"SHARED_ANNUAL_YEAR_MISMATCH:{path.name}")
        current_hashes = payload.get("input_hashes")
        if input_hashes is None:
            input_hashes = current_hashes
        elif current_hashes != input_hashes:
            raise ValueError(f"SHARED_ANNUAL_INPUT_HASH_DRIFT:{path.name}")
        factors = payload.get("factors", {})
        for item in payload.get("nodes", []):
            support = dict(item.get("support") or {})
            node_id = str(item["node_id"])
            factor = factors.get(node_id)
            exposure = None
            if factor is not None:
                exposure = {
                    "expected_passengers_per_flight": float(factor[0]),
                    "expected_downstream_exposure": float(factor[1]),
                    "source": "E1_NATIVE_M2_BINDING_OR_VERIFIED_RATIO",
                }
            yield SharedNodeRecord(
                episode_id=str(item["episode_id"]),
                chain_id=str(item["chain_id"]),
                node_id=node_id,
                stage=str(item["stage"]),
                decision_time=str(item["decision_time"]),
                delay_score=(None if item.get("delay_scores", {}).get("HISTORY_JOINT") is None
                             else float(item["delay_scores"]["HISTORY_JOINT"])),
                consequence_score=(None if item.get("consequence_scores", {}).get("HISTORY_JOINT") is None
                                   else float(item["consequence_scores"]["HISTORY_JOINT"])),
                domain_scores=dict(item.get("domain_scores", {}).get("HISTORY_JOINT") or {}),
                support=support,
                exposure=exposure,
                source_chunk=path.name,
                representations={
                    "HISTORY_JOINT": "PRESENT",
                    "CURRENT_JOINT": "MISSING_INCREMENTAL_COMPUTE",
                    "HISTORY_POINT": "MISSING_INCREMENTAL_COMPUTE",
                    "HISTORY_MARGINAL_EXACT": "MISSING_INCREMENTAL_COMPUTE",
                },
            )


def canonicalize(records: Iterable[SharedNodeRecord]) -> tuple[SharedNodeRecord, ...]:
    """Select canonical identity before support filtering."""

    by_key: dict[tuple[str, str], SharedNodeRecord] = {}
    for record in records:
        key = (record.episode_id, record.stage)
        previous = by_key.get(key)
        if previous is None or _decision_key(record) < _decision_key(previous):
            by_key[key] = record
    return tuple(sorted(by_key.values(), key=lambda row: (_decision_key(row), row.episode_id, row.stage)))


def build_shared_from_e1(
    *,
    e1_root: Path,
    output_root: Path,
    year: int,
    git_head: str | None = None,
) -> dict:
    """Persist a compact canonical annual table from existing E1 chunks."""

    e1_root = Path(e1_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    chunk_paths = _iter_chunk_paths(e1_root / "chunks")
    source_hashes = {path.name: _sha256(path) for path in chunk_paths}
    source_count = 0
    def counted_records():
        nonlocal source_count
        for record in iter_e1_compact_nodes(e1_root / "chunks", year=year):
            source_count += 1
            yield record
    canonical_records = canonicalize(counted_records())

    node_path = output_root / "SHARED_ANNUAL_NODES.jsonl"
    temporary = node_path.with_suffix(node_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in canonical_records:
            handle.write(json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(node_path)

    stage_counts = Counter(record.stage for record in canonical_records)
    support_counts = Counter(
        "INCLUDED" if bool(record.support.get("included")) else "ABSTAIN"
        for record in canonical_records
    )
    representation_counts = {
        representation: sum(
            record.representations.get(representation) == "PRESENT"
            for record in canonical_records
        )
        for representation in REQUIRED_REPRESENTATIONS
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "READY_SHARED_HISTORY_JOINT_INCREMENTAL_REPRESENTATIONS_PENDING",
        "year": int(year),
        "source": {
            "e1_root": str(e1_root),
            "chunk_count": len(chunk_paths),
            "chunk_hashes": source_hashes,
            "source_node_records": source_count,
            "source_input_hashes": json.loads(chunk_paths[0].read_text(encoding="utf-8")).get("input_hashes"),
        },
        "canonical": {
            "rule": "episode_id x operational_stage; minimum (decision_time, node_id)",
            "canonical_records": len(canonical_records),
            "stage_counts": dict(stage_counts),
            "support_counts_after_identity_selection": dict(support_counts),
        },
        "representations": representation_counts,
        "missing_incremental_compute": [
            "CURRENT_JOINT", "HISTORY_POINT", "HISTORY_MARGINAL_EXACT", "STAGE_II_ACTION_OUTCOME"
        ],
        "node_table": {
            "path": node_path.name,
            "sha256": _sha256(node_path),
            "records": len(canonical_records),
        },
        "git_head": git_head,
        "final_test_access_count": 0,
    }
    manifest["artifact_hash"] = _json_hash(manifest)
    (output_root / "SHARED_ANNUAL_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def load_shared_nodes(manifest_root: Path) -> Iterator[dict]:
    manifest_root = Path(manifest_root).resolve()
    manifest = json.loads((manifest_root / "SHARED_ANNUAL_MANIFEST.json").read_text(encoding="utf-8"))
    node_path = manifest_root / manifest["node_table"]["path"]
    if _sha256(node_path) != manifest["node_table"]["sha256"]:
        raise ValueError("SHARED_ANNUAL_NODE_TABLE_HASH_MISMATCH")
    with node_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--e1-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--git-head", default=None)
    args = parser.parse_args()
    manifest = build_shared_from_e1(
        e1_root=args.e1_root, output_root=args.output_root, year=args.year, git_head=args.git_head
    )
    print(json.dumps({"status": manifest["status"], "canonical_records": manifest["canonical"]["canonical_records"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
