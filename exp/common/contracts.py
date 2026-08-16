from typing import Any
from model.common.value_objects import FrozenModel

class ExperimentRunManifest(FrozenModel):
    experiment:str;dataset_instance_id:str;dataset_role:str;variant_ids:tuple[str,...]
    input_manifest_hash:str;config_hash:str;status:str;paper_result:bool=False;smoke:bool=False

class BootstrapResult(FrozenModel):
    metric:str;estimate:float;ci_lower:float;ci_upper:float;replicates:int;unit:str="episode"

class ExperimentResult(FrozenModel):
    manifest:ExperimentRunManifest;rows:tuple[dict[str,Any],...]
