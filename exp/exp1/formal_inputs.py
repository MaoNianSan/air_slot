"""Exact cache -> canonical node -> frozen PRE state evaluation bridge."""

import json
from hashlib import sha256
import numpy as np
import pandas as pd
import torch

from exp.exp2 import development_inputs as source
from model.PRE.contracts.pre_state import PREState
from model.PRE.development import materialize_preselected_cohorts
from model.common.config import load_config_layers
from model.M1.data import encode_pre_sequence
from model.M1.semantics import EVALUATION_LEAD_TIMES_MINUTES

ROOT = source.PROJECT_ROOT
PRE_ROOT = ROOT / "artifacts/models/pre/PRE_FORMAL_DEVELOPMENT_V1"


def file_hash(path):
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def nearest_lead(lead):
    if lead is None or not np.isfinite(lead):
        return None, "ABSTAIN_REALIZED_EVENT_UNAVAILABLE"
    if lead < 0 or lead > max(EVALUATION_LEAD_TIMES_MINUTES):
        return None, "EXCLUDE_OUTSIDE_EVALUATION_RANGE"
    return min(EVALUATION_LEAD_TIMES_MINUTES, key=lambda x: (abs(x-lead), x)), "PASS"


def load_exact_inputs():
    manifest, cohort, _, cache = source._load_authorities()
    pm = source._read_json(PRE_ROOT / "PRE_FORMAL_DEVELOPMENT_MANIFEST.json")
    pa = source._read_json(PRE_ROOT / "PRE_FORMAL_DEVELOPMENT_AUDIT.json")
    states_path = PRE_ROOT / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl"
    if (pm["status"] != "PASS" or pa["status"] != "PASS"
            or pm["final_test_access_count"] != 0
            or file_hash(states_path) != pm["states_sha256"]
            or file_hash(PRE_ROOT / "PRE_FORMAL_DEVELOPMENT_AUDIT.json") != pm["audit_sha256"]):
        raise ValueError("EXP1_FORMAL_PRE_HASH_OR_STATUS_FAILED")
    frozen = {}
    with states_path.open(encoding="utf-8") as stream:
        for line in stream:
            state = PREState.model_validate_json(line)
            node = state.decision_node
            if node.information_cutoff > node.decision_time:
                raise ValueError("EXP1_FUTURE_INFORMATION")
            key = (node.episode_id, node.node_index)
            if key in frozen:
                raise ValueError("EXP1_DUPLICATE_PRE_STATE")
            frozen[key] = state
    prep = torch.load(source.PREP_STATE, map_location="cpu", weights_only=False)
    if prep["reservoirs"].get("test"):
        raise ValueError("FINAL_TEST_RESERVOIR_REJECTED")
    episodes = tuple(sorted(prep["reservoirs"]["development"], key=lambda x: x.episode_id))
    if {e.episode_id for e in episodes} != set(cohort["development_episode_ids"]):
        raise ValueError("EXP1_COHORT_MISMATCH")
    taxi, turnaround, _ = source._load_references(ROOT)
    published = materialize_preselected_cohorts(
        load_config_layers(ROOT / "configs").scientific, root=ROOT,
        partitions={"train": (), "calibration": (), "development": episodes},
        selection_audit={"selection_reperformed": False},
        taxi_reference=taxi, turnaround_reference=turnaround,
    )
    prepared = {e.episode.episode_id: e for e in published.development}
    rows, mapping = [], []
    for example in cache.partition("development"):
        ep = prepared[example.episode_id]
        position = len(example.values) - 1
        canonical = ep.nodes[position]
        state = ep.states[position]
        saved = frozen[(example.episode_id, position)]
        if canonical.decision_node_id != example.decision_node_id:
            raise ValueError("EXP1_CACHE_CANONICAL_ID_MISMATCH")
        if saved.model_dump(mode="json") != state.model_dump(mode="json"):
            raise ValueError("EXP1_FROZEN_PRE_STATE_MISMATCH")
        prefix = ep.states[:position+1]
        encoded = encode_pre_sequence(prefix, cache.normalization)
        if not torch.equal(encoded, example.values):
            raise ValueError("EXP1_PRE_CACHE_FEATURE_MISMATCH")
        if not ("2019-08-01" <= canonical.decision_time.date().isoformat() < "2019-10-01"):
            raise ValueError("FINAL_TEST_OR_NON_DEVELOPMENT_NODE")
        info = {
            "episode_id": example.episode_id,
            "decision_node_id": example.decision_node_id,
            "pre_decision_node_id": state.decision_node.decision_node_id,
            "decision_time": canonical.decision_time.isoformat(),
            "node_index": position,
        }
        events = {
            "R_IB": ep.predecessor_outcome.actual_arrival_utc,
            "D_OB": ep.successor_outcome.actual_departure_utc,
            "D_TX": ep.successor_outcome.wheels_off_utc,
        }
        for target, event in events.items():
            lead = None if event is None else (event-canonical.decision_time).total_seconds()/60
            grid, status = nearest_lead(lead)
            info.update({f"{target}_event_time": None if event is None else event.isoformat(),
                         f"{target}_lead_minutes": lead, f"{target}_lead_grid": grid,
                         f"{target}_lead_status": status})
        mapping.append(info)
        rows.append((example, ep, prefix))
    if len(rows) != 1769 or len({r[0].decision_node_id for r in rows}) != 1769:
        raise ValueError("EXP1_EXACT_MATCHED_NODE_COUNT")
    return cache, rows, pd.DataFrame(mapping), taxi, manifest
