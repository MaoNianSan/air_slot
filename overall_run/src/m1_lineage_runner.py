from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from .m1_lineage_contract import (
    AUDIT_ROOT,
    FAST_ROOT,
    LOG_ROOT,
    PROJECT_ROOT,
    AuditStop,
    _write_json,
    _write_parquet,
    _write_text,
    registered_artifact_snapshot,
    sha256_file,
    verify_frozen_baseline,
)
from .m1_lineage_dictionary import build_metric_dictionary, build_prediction_layer_mapping
from .m1_lineage_figures import generate_figures
from .m1_lineage_history import (
    build_historical_deprecation_registry,
    build_historical_tables,
    scan_formal_materials_for_deprecated_claims,
)
from .m1_lineage_identity import build_current_identity
from .m1_lineage_lineage import (
    build_bootstrap_lineage,
    build_cohort_lineage,
    build_metric_version_registry,
)
from .m1_lineage_reconstruction import reconstruct_current_metrics
from .m1_lineage_reports import (
    build_audit_markdown,
    build_cloud_markdown,
    build_code_study,
    cloud_readiness,
)


def run_audit(*, deep_inputs: bool = True, make_figures: bool = True) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_id = f"M1_D6_LINEAGE_AUDIT_{timestamp}"
    before_registry_hash = sha256_file(FAST_ROOT / "artifact_registry.json")
    before_artifacts = registered_artifact_snapshot()
    baseline = verify_frozen_baseline(deep_inputs=deep_inputs)
    context = reconstruct_current_metrics()

    dictionary = build_metric_dictionary()
    identity = build_current_identity(context, dictionary)
    cohort_lineage = build_cohort_lineage(context, dictionary)
    version_registry = build_metric_version_registry(dictionary)
    bootstrap_lineage = build_bootstrap_lineage(context, dictionary)
    layer_mapping = build_prediction_layer_mapping()
    deprecation = build_historical_deprecation_registry()
    historical_inventory, historical_identity, cross_run = build_historical_tables(deprecation)
    formal_deprecated_hits = scan_formal_materials_for_deprecated_claims()
    if formal_deprecated_hits:
        raise AuditStop("DEPRECATED_HISTORICAL_VALUES_IN_FORMAL_REPORTS:" + ",".join(formal_deprecated_hits))

    outputs = {
        "m1_metric_dictionary.parquet": dictionary,
        "m1_metric_cohort_lineage.parquet": cohort_lineage,
        "m1_d6_historical_artifact_inventory.parquet": historical_inventory,
        "m1_d6_current_metric_identity.parquet": identity,
        "m1_d6_historical_metric_identity.parquet": historical_identity,
        "m1_d6_cross_run_comparison.parquet": cross_run,
        "m1_d6_metric_version_registry.parquet": version_registry,
        "m1_d6_bootstrap_lineage.parquet": bootstrap_lineage,
        "m1_d6_prediction_layer_mapping.parquet": layer_mapping,
        "m1_d6_historical_deprecation_registry.parquet": deprecation,
    }
    for name, frame in outputs.items():
        _write_parquet(AUDIT_ROOT / name, frame)

    deprecation_summary = {
        "audit_id": audit_id,
        "researcher_disposition": "DEPRECATE_UNRECOVERABLE_HISTORICAL_D6_NUMBERS",
        "historical_reconciliation_status": "DEPRECATED_UNRECOVERABLE",
        "historical_disposition_status": "PASS",
        "registered_value_count": len(deprecation),
        "authority_status": "NON_AUTHORITATIVE",
        "manuscript_use_status": "PROHIBITED",
        "formal_report_prohibited_reference_count": len(formal_deprecated_hits),
        "statement": "Deprecation is an evidence-governance decision. It is not a reconstruction or scientific reconciliation of the historical values.",
        "future_recovery_policy": "NEW_RETROSPECTIVE_AUDIT_REQUIRED_DO_NOT_OVERWRITE",
    }
    _write_json(AUDIT_ROOT / "m1_d6_historical_deprecation_summary.json", deprecation_summary)

    figure_outputs = generate_figures(context) if make_figures else {}
    readiness = cloud_readiness(baseline, audit_id)
    cloud_json_path = LOG_ROOT / f"CLOUD_FULL_READINESS_{timestamp}.json"
    cloud_md_path = LOG_ROOT / f"CLOUD_FULL_READINESS_{timestamp}.md"
    _write_json(cloud_json_path, readiness)
    _write_text(cloud_md_path, build_cloud_markdown(readiness))

    reported_identity = identity[identity["reported_value"].notna()]
    summary = {
        "audit_id": audit_id,
        "status": "M1_D6_CURRENT_LINEAGE_AUDIT_PASS",
        "D6_AUDIT_ENGINEERING_STATUS": "PASS",
        "CURRENT_METRIC_IDENTITY_STATUS": "PASS",
        "CURRENT_AUTHORITATIVE_LINEAGE_STATUS": "PASS",
        "HISTORICAL_RECONCILIATION_STATUS": "DEPRECATED_UNRECOVERABLE",
        "HISTORICAL_DISPOSITION_STATUS": "PASS",
        "FORMAL_DIAGNOSTIC_SEPARATION_STATUS": "PASS",
        "METRIC_VERSIONING_STATUS": "PASS",
        "Q95_FINAL_CLASSIFICATION": "SYSTEMATIC_CALIBRATION_CONCERN_CURRENT_FAST",
        "Q95_CERTIFICATION": "METRIC_SUPPORT_LIMITED",
        "Q99_FINAL_CLASSIFICATION": "METRIC_SUPPORT_LIMITED_CURRENT_FAST_ONLY",
        "TAIL_SUPPORT_STATUS": "LIMITED_CURRENT_FAST_ONLY",
        "M1_SCIENTIFIC_STATUS": "STOP_AND_REVIEW",
        "D6_LINEAGE_STATUS": "PASS_CURRENT_AUTHORITATIVE_LINEAGE_ONLY",
        "cloud_ready": readiness["cloud_ready"],
        "cloud_start_stage": readiness["cloud_start_stage"],
        "FULL_RECOMMENDED": False,
        "metric_value_mismatch_count": int(reported_identity["value_match"].eq(False).sum()),
        "support_mismatch_count": int(reported_identity["support_match"].eq(False).sum()),
        "cohort_hash_mismatch_count": int(identity["cohort_hash_match"].eq(False).sum()),
        "prediction_layer_mismatch_count": int(identity["prediction_layer_match"].eq(False).sum()),
        "formal_report_prohibited_reference_count": len(formal_deprecated_hits),
        "formal_cohort_hash": context["formal_cohort_hash"],
        "tail_cohort_hash": context["tail_cohort_hash"],
        "current_values": context["values"],
        "prediction_identity": {
            "overall_vs_part_prop_max_abs_delta": context["prediction_layer_max_abs_delta"],
            "predictive_sample_max_abs_delta": context["predictive_sample_max_abs_delta"],
        },
        "baseline": baseline,
        "figures": figure_outputs,
        "run_started": False,
    }
    _write_json(AUDIT_ROOT / "m1_d6_lineage_summary.json", summary)

    report_md_path = LOG_ROOT / f"M1_D6_METRIC_LINEAGE_AUDIT_{timestamp}.md"
    report_json_path = LOG_ROOT / f"M1_D6_METRIC_LINEAGE_AUDIT_{timestamp}.json"
    study_path = LOG_ROOT / f"M1_D6_CODE_STUDY_{timestamp}.md"
    _write_text(report_md_path, build_audit_markdown(summary, context))
    _write_json(report_json_path, summary)
    _write_text(study_path, build_code_study(context, audit_id, dictionary))

    after_registry_hash = sha256_file(FAST_ROOT / "artifact_registry.json")
    after_artifacts = registered_artifact_snapshot()
    registered_unchanged = before_registry_hash == after_registry_hash and before_artifacts == after_artifacts
    if not registered_unchanged:
        raise AuditStop("AUDIT_MODIFIED_REGISTERED_FORMAL_ARTIFACT")
    summary["formal_registry_hash_before"] = before_registry_hash
    summary["formal_registry_hash_after"] = after_registry_hash
    summary["registered_formal_artifacts_unchanged"] = True
    _write_json(AUDIT_ROOT / "m1_d6_lineage_summary.json", summary)
    _write_json(report_json_path, summary)

    audit_files = [
        *[AUDIT_ROOT / name for name in outputs],
        AUDIT_ROOT / "m1_d6_historical_deprecation_summary.json",
        AUDIT_ROOT / "m1_d6_lineage_summary.json",
        report_md_path, report_json_path, study_path, cloud_md_path, cloud_json_path,
    ]
    for paths in figure_outputs.values():
        audit_files.extend(PROJECT_ROOT / path for path in paths)
    registry = {
        "audit_id": audit_id,
        "baseline_formal_registry_hash": baseline["formal_registry_hash"],
        "scientific_implementation_hash": baseline["scientific_implementation_hash"],
        "registered_formal_artifacts_unchanged": True,
        "artifacts": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in audit_files
            if path.is_file()
        ],
    }
    _write_json(AUDIT_ROOT / "m1_d6_audit_registry.json", registry)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--skip-deep-input-hash",
        action="store_true",
        help="Skip the 167-file payload rehash for development only; never use for final audit.",
    )
    command.add_argument("--skip-figures", action="store_true")
    return command


def main() -> int:
    args = parser().parse_args()
    try:
        run_audit(
            deep_inputs=not args.skip_deep_input_hash,
            make_figures=not args.skip_figures,
        )
        return 0
    except AuditStop as exc:
        payload = {
            "status": "M1_D6_LINEAGE_AUDIT_STOPPED_FOR_CONFIRMATION",
            "error": str(exc),
            "M1_SCIENTIFIC_STATUS": "STOP_AND_REVIEW",
            "FULL_RECOMMENDED": False,
            "run_started": False,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


