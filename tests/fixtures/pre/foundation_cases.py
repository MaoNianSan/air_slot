from datetime import datetime, timezone
from model.PRE.foundation import PREBuildRequest, build_pre_state


def build_request(dataset_instance_id: str = "data1_2019") -> PREBuildRequest:
    return PREBuildRequest(episode_id="fixture-episode", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=timezone.utc),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=timezone.utc),
        config_hash="sha256:fixture-config", registry_hash="sha256:fixture-registry",
        legal_record_ids=("weather-1", "motion-1"), dataset_instance_id=dataset_instance_id)


def build_data1_case():
    return build_pre_state(build_request("data1_2019"))
