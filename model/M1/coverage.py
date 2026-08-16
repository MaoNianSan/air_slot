"""M1 training coverage: all rolling grid decision nodes as training samples.

Frozen rule M1_TRAINING_COVERAGE@1.0.0:
one M1 training example per decision node (node-level equal weight), stage-gated
labels, frozen rolling-grid anchors unchanged. Episodes whose grid has no PRE_IB node (early
arrival: actual arrival <= CRSArr, t0 already after IB) still contribute their
POST_IB_PRE_OB / POST_OB_PRE_TO nodes. Nodes with no active target (all three
targets already realized, e.g. COMPLETED) are excluded because they carry no
supervision. Dataset isolation is enforced by typed episode/source identity
checks in the generic target builder; raw schema remains in PRE adapters.
"""
from __future__ import annotations

from typing import Any, Iterator

from model.M1.data import encode_pre_sequence
from model.M1.lifecycle import M1TrainingExample
from model.M1.target_builder import build_target_labels
from model.M1.contracts import M1TargetLabel
from model.PRE.contracts.canonical import FlightRecord, OperationalEventRecord
from model.PRE.contracts.pre_state import DecisionNodeRecord, EpisodeRecord, PREState


def active_node_prefixes(*, episode: EpisodeRecord,
                         nodes: tuple[DecisionNodeRecord, ...],
                         states: tuple[PREState, ...],
                         successor_schedule: FlightRecord,
                         predecessor_outcome: OperationalEventRecord,
                         successor_outcome: OperationalEventRecord,
                         ) -> Iterator[tuple[DecisionNodeRecord, tuple[PREState, ...],
                                             tuple[M1TargetLabel, ...]]]:
    """Yield (node, prefix_states, labels) for every node with >=1 active target.

    Prefix states run from the frozen rolling-grid anchor through the node;
    labels are stage-gated by build_target_labels. Nodes whose
    targets are all realized (all labels inactive) are skipped.
    """
    if len(nodes) != len(states):
        raise ValueError("M1_COVERAGE_NODES_STATES_LENGTH_MISMATCH")
    for index, node in enumerate(nodes):
        labels = build_target_labels(
            episode=episode, node=node,
            predecessor_outcome=predecessor_outcome,
            successor_schedule=successor_schedule,
            successor_outcome=successor_outcome,
            target_support=states[index].target_support)
        if any(label.active for label in labels):
            yield node, states[: index + 1], labels


def build_all_node_examples(*, episode: EpisodeRecord,
                            nodes: tuple[DecisionNodeRecord, ...],
                            states: tuple[PREState, ...],
                            successor_schedule: FlightRecord,
                            predecessor_outcome: OperationalEventRecord,
                            successor_outcome: OperationalEventRecord,
                            normalization: Any, bins: Any) -> list[M1TrainingExample]:
    """Build one M1 training example per active node, in node order."""
    return [M1TrainingExample.from_target_labels(
                values=encode_pre_sequence(prefix, normalization),
                labels=labels, bins=bins)
            for _, prefix, labels in active_node_prefixes(
                episode=episode, nodes=nodes, states=states,
                successor_schedule=successor_schedule,
                predecessor_outcome=predecessor_outcome,
                successor_outcome=successor_outcome)]
