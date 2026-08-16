from datetime import datetime, timezone
from typing import Any
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel

class ExperimentRunManifest(FrozenModel):
    experiment:str;dataset_instance_id:str;dataset_role:str;variant_ids:tuple[str,...]
    input_manifest_hash:str;config_hash:str;status:str;paper_result:bool=False;smoke:bool=False
    git_commit_sha:str="UNSET"
    scientific_config_hash:str="UNSET"
    evaluation_config_hash:str="UNSET"
    registry_manifest_hash:str="UNSET"
    split_contract_hash:str="UNSET"
    cohort_hash:str="UNSET"
    variant_hashes:dict[str,str]={}
    model_artifact_hashes:dict[str,str]={}
    scenario_count:int=0
    random_seed:int=0
    timestamp:str=""
    split:str="DEVELOPMENT"
    primary_metric:str="UNSET"
    tuning_events:tuple[str,...]=()
    paper_eligible:bool=False

    def final_test_guard(self, previous: "ExperimentRunManifest | None" = None) -> None:
        if self.split != "FINAL_TEST":
            return
        if self.tuning_events:
            raise ContractError("FINAL_TEST_TUNING_INVALIDATES_PROMOTION")
        if previous is None:
            return
        frozen = ("scientific_config_hash", "evaluation_config_hash", "registry_manifest_hash",
                  "split_contract_hash", "cohort_hash", "primary_metric", "scenario_count")
        if any(getattr(self, name) != getattr(previous, name) for name in frozen):
            raise ContractError("FINAL_TEST_IMMUTABILITY_VIOLATION")

class BootstrapResult(FrozenModel):
    metric:str;estimate:float;ci_lower:float;ci_upper:float;replicates:int;unit:str="episode"

class ExperimentResult(FrozenModel):
    manifest:ExperimentRunManifest;rows:tuple[dict[str,Any],...]


def assert_final_test_immutable(before: ExperimentRunManifest, after: ExperimentRunManifest) -> None:
    after.final_test_guard(before)
