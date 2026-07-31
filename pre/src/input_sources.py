from __future__ import annotations

import gzip
import hashlib
import tarfile
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd


def sha256_file(path: str | Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_airport(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip().upper()


def resolve_source_root(project_root: Path, data_root: Path, configured_root: str | Path) -> Path:
    path = Path(configured_root)
    if path.is_absolute():
        return path
    parts = path.parts
    if len(parts) >= 2 and parts[0] == ".." and parts[1] == "data":
        return data_root.joinpath(*parts[2:]).resolve()
    return (project_root / path).resolve()


def discover_files(project_root: Path, data_root: Path, spec: dict[str, Any]) -> list[Path]:
    root = resolve_source_root(project_root, data_root, spec["root"])
    files: list[Path] = []
    for pattern in spec.get("patterns", []):
        files.extend(path for path in root.glob(pattern) if path.is_file())
    excluded = spec.get("exclude_patterns", ["*.part", "*.tmp", "*.url.txt"])
    files = [p for p in files if not any(p.match(pattern) for pattern in excluded)]
    return sorted(set(files))


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".parquet"):
        return pd.read_parquet(path)
    if suffixes.endswith(".tsv") or suffixes.endswith(".tsv.gz"):
        return pd.read_csv(path, sep="\t", low_memory=False)
    if suffixes.endswith(".json"):
        return pd.read_json(path)
    if suffixes.endswith(".csv.tar") or suffixes.endswith(".tar"):
        frames = list(iter_csv_tar(path, chunksize=None))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def iter_csv_tar(
    path: str | Path,
    *,
    chunksize: int | None = 250_000,
    usecols: Iterable[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield CSV members from a tar archive without extracting them to raw/."""
    path = Path(path)
    with tarfile.open(path, mode="r:*") as archive:
        members = [m for m in archive.getmembers() if m.isfile() and m.name.lower().endswith((".csv", ".csv.gz"))]
        if not members:
            raise ValueError(f"tar archive contains no CSV member: {path}")
        for member in members:
            handle = archive.extractfile(member)
            if handle is None:
                continue
            stream = gzip.GzipFile(fileobj=handle) if member.name.lower().endswith(".csv.gz") else handle
            reader = pd.read_csv(stream, low_memory=False, usecols=usecols, chunksize=chunksize)
            if chunksize is None:
                yield reader
            else:
                yield from reader


def mapped(frame: pd.DataFrame, mapping: dict[str, str], required: Iterable[str]) -> pd.DataFrame:
    required = list(required)
    missing_config = [name for name in required if name not in mapping]
    if missing_config:
        raise ValueError(f"source mapping missing canonical fields: {missing_config}")
    missing_columns = [mapping[name] for name in required if mapping[name] not in frame.columns]
    if missing_columns:
        raise ValueError(f"source file missing configured columns: {missing_columns}")
    out = pd.DataFrame(index=frame.index)
    for canonical, source in mapping.items():
        out[canonical] = frame[source] if source in frame.columns else pd.NA
    return out


def attach_provenance(frame: pd.DataFrame, path: Path, file_hash: str | None = None) -> pd.DataFrame:
    out = frame.copy()
    out["raw_source_file"] = str(path)
    out["raw_source_hash"] = file_hash or sha256_file(path)
    out["source_record_id"] = [f"{path.name}:{i}" for i in range(len(out))]
    return out


