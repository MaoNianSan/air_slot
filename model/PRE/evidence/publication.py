from collections import defaultdict
from datetime import datetime
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.value_objects import SupportedValue
from model.PRE.contracts.pre_state import EvidenceLedgerEntry, VariableLineageEntry


def select_and_publish(
    records: tuple[dict, ...], *, cutoff: datetime, decision_node_id: str
):
    legal = [
        record
        for record in records
        if record.get("episode_member") is True
        and record.get("availability_time") is not None
        and record["availability_time"] <= cutoff
        and record.get("availability_basis") != "POSTHOC_ONLY"
    ]
    grouped = defaultdict(list)
    for record in legal:
        grouped[record["scientific_variable"]].append(record)
    state, ledger, lineage, ids = {}, [], [], []
    for variable in sorted(grouped):
        candidates = sorted(
            grouped[variable],
            key=lambda item: (item["availability_time"], item["canonical_record_id"]),
        )
        selected = candidates[-1]
        same_time = [
            item
            for item in candidates
            if item["availability_time"] == selected["availability_time"]
        ]
        if len({repr(item["value"]) for item in same_time}) > 1:
            raise ContractError("EQUAL_PRIORITY_CONFLICT")
        evidence = EvidenceClass(selected["evidence_class"])
        ceiling = EvidenceClass(selected["support_ceiling"])
        value = SupportedValue(
            value=selected["value"],
            unit=selected["unit"],
            evidence_class=evidence,
            support_ceiling=ceiling,
            support_state=SupportState.SUPPORTED,
        )
        state[variable] = value
        ids.append(selected["canonical_record_id"])
        common = dict(
            decision_node_id=decision_node_id,
            source_name=selected["source_path"],
            source_record_id=selected["canonical_record_id"],
            event_time=selected["event_time"],
            availability_time=selected["availability_time"],
            availability_basis=selected["availability_basis"],
        )
        ledger.append(
            EvidenceLedgerEntry(
                **common,
                scientific_object=variable,
                decision_time_role="INFERENCE_EVIDENCE",
                evidence_class=evidence,
                support_ceiling=ceiling,
                episode_support=SupportState.SUPPORTED,
                freshness_seconds=(
                    cutoff - selected["availability_time"]
                ).total_seconds(),
            )
        )
        lineage.append(
            VariableLineageEntry(
                **common,
                scientific_variable=variable,
                supported_value=value,
                canonical_variable=variable,
                rule_id=selected["provenance_rule_id"],
                age_seconds=(cutoff - selected["availability_time"]).total_seconds(),
            )
        )
    return state, tuple(ledger), tuple(lineage), tuple(sorted(ids))
