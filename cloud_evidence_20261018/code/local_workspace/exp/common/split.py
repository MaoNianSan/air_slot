def chronological_episode_split(rows,train_end,calibration_end):
    output={"train":[],"calibration":[],"test":[]};episode_membership={}
    for row in sorted(rows,key=lambda x:(x["episode_date"],x["episode_id"])):
        split="train" if row["episode_date"]<=train_end else "calibration" if row["episode_date"]<=calibration_end else "test"
        previous=episode_membership.setdefault(row["episode_id"],split)
        if previous!=split:raise ValueError("episode crosses split")
        output[split].append(row)
    return output
