from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Failure:
    code: str
    module: str
    message: str
    severity: str = "ERROR"
    episode_id: str | None = None
    snapshot_id: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FormalRunBlocked(RuntimeError):
    pass


class M2ContractMismatch(FormalRunBlocked):
    pass


class M2ParameterNotFrozen(FormalRunBlocked):
    pass


class M3ContractMismatch(FormalRunBlocked):
    pass


class M3ParameterNotFrozen(FormalRunBlocked):
    pass


class M3FormalLibraryNotReady(FormalRunBlocked):
    pass


class M4ContractMismatch(FormalRunBlocked):
    pass
