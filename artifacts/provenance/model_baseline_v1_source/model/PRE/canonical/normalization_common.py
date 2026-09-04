import math
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from model.common.value_objects import ProvenanceRef

_MISSING = {"", "M", "NA", "N/A", "NAN", "NONE", "NULL"}


def missing(value: object) -> bool:
    return value is None or str(value).strip().upper() in _MISSING


def number(value: object) -> float | None:
    if missing(value):
        return None
    result = float(str(value).strip())
    return None if math.isnan(result) else result


def deterministic_id(prefix: str, parts: dict[str, Any]) -> str:
    payload = "|".join(f"{key}={parts[key]}" for key in sorted(parts))
    return f"{prefix}:{sha256(payload.encode('utf-8')).hexdigest()}"


def parse_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif (
        isinstance(value, (int, float))
        or str(value).strip().replace(".", "", 1).isdigit()
    ):
        parsed = datetime.fromtimestamp(float(value), timezone.utc)
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def provenance(
    dataset: str, logical_source: str, source_record_id: str, rule_id: str
) -> ProvenanceRef:
    return ProvenanceRef(
        dataset_instance_id=dataset,
        logical_source=logical_source,
        source_record_id=source_record_id,
        rule_id=rule_id,
        source_version="2019",
    )
