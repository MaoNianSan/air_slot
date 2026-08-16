import csv
import gzip
import io
import json
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from model.common.errors import ContractError
from .registry import RawReadRequest, SourceAdapterDefinition


@dataclass(frozen=True)
class RawRow:
    values: dict[str, str]
    source_path: str
    source_fingerprint: str
    row_number: int


def source_files(request: RawReadRequest, definition: SourceAdapterDefinition) -> list[Path]:
    files: set[Path] = set()
    for template in definition.relative_globs:
        pattern = template.format(year=request.year or "*", month=f"{request.month:02d}" if request.month else "*", date=request.date or "*")
        files.update(path for path in request.raw_root.glob(pattern) if path.is_file())
    ordered = sorted(files)
    return ordered[:request.max_files] if request.max_files else ordered


def iter_csv_rows(request: RawReadRequest, definition: SourceAdapterDefinition) -> Iterator[RawRow]:
    emitted = 0
    for path in source_files(request, definition):
        with path.open("rb") as fingerprint_stream:
            prefix = fingerprint_stream.read(1_048_576)
        fingerprint = f"sha256:{sha256(prefix + str(path.stat().st_size).encode()).hexdigest()}"
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            missing_columns = set(definition.required_columns) - set(payload)
            if missing_columns: raise ContractError(f"RAW_SCHEMA_MISMATCH:{sorted(missing_columns)}")
            yield RawRow(values={"payload": payload}, source_path=path.relative_to(request.raw_root).as_posix(),
                         source_fingerprint=fingerprint, row_number=1)
            emitted += 1
            if request.max_rows and emitted >= request.max_rows: return
            continue
        if definition.format == "csv_tar":
            yield from _iter_tar_rows(path, request, definition, fingerprint, emitted)
            emitted += request.max_rows or 0
            if request.max_rows and emitted >= request.max_rows: return
            continue
        opener = gzip.open if definition.format == "csv_gzip" else open
        with opener(path, "rt", encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            missing_columns = set(definition.required_columns) - set(reader.fieldnames or ())
            if missing_columns: raise ContractError(f"RAW_SCHEMA_MISMATCH:{sorted(missing_columns)}")
            for row_number, row in enumerate(reader, start=2):
                values = {key: row.get(key, "") for key in (definition.projected_columns or tuple(row))}
                yield RawRow(values=values, source_path=path.relative_to(request.raw_root).as_posix(),
                    source_fingerprint=fingerprint, row_number=row_number)
                emitted += 1
                if request.max_rows and emitted >= request.max_rows: return


def _iter_tar_rows(path: Path, request: RawReadRequest, definition: SourceAdapterDefinition,
                   fingerprint: str, already_emitted: int) -> Iterator[RawRow]:
    with tarfile.open(path, "r") as archive:
        members = [member for member in archive.getmembers() if member.isfile()
                   and (member.name.endswith(".csv") or member.name.endswith(".csv.gz"))]
        if not members: raise ContractError("ARCHIVE_HAS_NO_REGISTERED_CSV_MEMBER")
        emitted = already_emitted
        for member in sorted(members, key=lambda item: item.name):
            raw = archive.extractfile(member)
            if raw is None: continue
            binary = gzip.GzipFile(fileobj=raw) if member.name.endswith(".gz") else raw
            with io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="") as stream:
                reader = csv.DictReader(stream)
                missing_columns = set(definition.required_columns) - set(reader.fieldnames or ())
                if missing_columns: raise ContractError(f"RAW_SCHEMA_MISMATCH:{sorted(missing_columns)}")
                for row_number, row in enumerate(reader, start=2):
                    values = {key: row.get(key, "") for key in (definition.projected_columns or tuple(row))}
                    yield RawRow(values=values,
                        source_path=f"{path.relative_to(request.raw_root).as_posix()}::{member.name}",
                        source_fingerprint=fingerprint, row_number=row_number)
                    emitted += 1
                    if request.max_rows and emitted >= request.max_rows: return
