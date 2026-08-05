from __future__ import annotations

from typing import Any


def build_run_report(
    manifest: dict[str, Any],
    validation: dict[str, Any],
    readiness: dict[str, Any],
    cache: dict[str, Any],
) -> str:
    event = validation["events"]
    chains = validation["chains"]
    observations = validation["observations"]
    lines = [
        "# PRE Core Run Report",
        "",
        f"- Contract: `{manifest['contract_id']}`",
        f"- Schema: `{manifest['schema_version']}`",
        f"- Mode: `{manifest['mode']}`",
        f"- Core data hash: `{manifest['core_data_hash']}`",
        f"- Validation: `{validation['status']}`",
        f"- Readiness: `{readiness['status']}`",
        "",
        "## Rows",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in manifest["row_counts"].items())
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- `EVENT_CONTRACT_VALID={'YES' if event['status'] == 'PASS' else 'NO'}`",
            f"- `EVENT_ORDER_ERROR_RATE={event['event_order_error_rate']}`",
            f"- `OFFICIAL_PROXY_CONFUSION={'NO' if event['official_proxy_confusion'] == 0 else 'YES'}`",
            f"- `CHAIN_BUILD_STATUS={chains['status']}`",
            f"- `AMBIGUOUS_CHAIN_EXCLUDED={'YES' if chains['ambiguous_formal_eligible'] == 0 else 'NO'}`",
            f"- `CHAIN_SPLIT_LEAKAGE={'NO' if chains['chain_split_leakage'] == 0 else 'YES'}`",
            f"- `NATIVE_RESOLUTION_PRESERVED={'YES' if observations['native_resolution_preserved'] else 'NO'}`",
            f"- `SNAPSHOT_RATIO_DEPENDENCY_REMOVED_FROM_CORE={'YES' if not observations['ratio_dependency_columns'] else 'NO'}`",
            f"- `ON_DEMAND_EVIDENCE_SUPPORTED={'YES' if observations['on_demand_evidence_supported'] else 'NO'}`",
            f"- `STATE_CACHE_REUSED_WHERE_VALID={'YES' if cache.get('legacy_candidate_reused') or cache.get('legacy_flow_reused') or cache.get('cache_status') == 'CORE_HIT' else 'NO_VALID_FULL_REUSE'}`",
            f"- `TRAIN_ONLY_REFERENCE={'YES' if validation['references']['status'] == 'PASS' else 'NO'}`",
            f"- `FUTURE_LEAKAGE={'NO' if validation['leakage']['future_information_used'] == 0 else 'YES'}`",
            f"- `MISSING_ZERO_CONFUSION={'NO' if validation['leakage']['missing_zero_confusion'] == 0 else 'YES'}`",
            f"- `TARGET_IDENTITY_{validation['leakage']['target_identity_status']}=YES`",
            "",
            "## Known Limitation",
            "",
            "Local flightlist data has no official AOBT, AIBT, ATOT, ALDT, SOBT, cancellation, diversion, swap, or rotation fields. Proxy events remain explicitly marked and chain delay labels remain null.",
        ]
    )
    return "\n".join(lines) + "\n"
