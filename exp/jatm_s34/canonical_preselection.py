"""PRE identity selection using the existing Section-5 canonical authority."""
from exp.jatm_section5.cohorts import canonical_stage_cohort


def canonical_preselection(rows):
    metadata = []
    for _example, _episode, prefix in rows:
        node = prefix[-1].decision_node
        metadata.append(dict(episode_id=node.episode_id,
                             node_id=node.decision_node_id,
                             stage=node.operational_stage,
                             decision_time=node.decision_time))
    stages = sorted({row["stage"] for row in metadata}, key=lambda stage: stage.value)
    selected = tuple(row.node["node_id"] for stage in stages
                     for row in canonical_stage_cohort(metadata, stage=stage,
                                                       eligibility=lambda _: True))
    return selected


def canonical_bridge(bridge):
    ids = set(canonical_preselection(bridge["rows"]))
    return dict(bridge, rows=tuple(row for row in bridge["rows"]
                                  if row[2][-1].decision_node.decision_node_id in ids))
