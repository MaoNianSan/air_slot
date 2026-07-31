"""Read-only M1 D6 current-authoritative metric-lineage audit."""
from __future__ import annotations

from src.m1_lineage_contract import (
    AuditStop,
    cohort_hash,
    pinball_loss,
    quantile_crps,
    sha256_file,
    twcrps_value,
    verify_frozen_baseline,
)
from src.m1_lineage_dictionary import build_metric_dictionary
from src.m1_lineage_history import build_historical_deprecation_registry
from src.m1_lineage_reconstruction import reconstruct_current_metrics
from src.m1_lineage_runner import main, parser, run_audit

__all__ = [
    "AuditStop",
    "build_historical_deprecation_registry",
    "build_metric_dictionary",
    "cohort_hash",
    "main",
    "parser",
    "pinball_loss",
    "quantile_crps",
    "reconstruct_current_metrics",
    "run_audit",
    "sha256_file",
    "twcrps_value",
    "verify_frozen_baseline",
]

if __name__ == "__main__":
    raise SystemExit(main())
