from collections import Counter
from typing import Literal
from pydantic import computed_field

from model.common.value_objects import FrozenModel


Status = Literal["PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_IMPLEMENTED_BY_SCOPE"]


class ValidationFinding(FrozenModel):
    check_id: str
    status: Status
    message: str
    path: str | None = None


class ValidationRun(FrozenModel):
    run_id: str
    command: Literal["contracts", "adapters", "pre", "all"]
    findings: tuple[ValidationFinding, ...]
    FIXTURE_ONLY: bool = True
    paper_result: bool = False
    evaluation_scope: Literal["FOUNDATION_ONLY"] = "FOUNDATION_ONLY"

    @computed_field
    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(finding.status for finding in self.findings)
        return {status: counts.get(status, 0) for status in
                ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_IMPLEMENTED_BY_SCOPE")}


def exit_code(run: ValidationRun) -> int:
    return 1 if run.summary["FAIL"] or run.summary["BLOCKED"] else 0
