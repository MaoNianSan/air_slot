from pathlib import Path
import yaml
from pydantic import model_validator
from model.common.errors import RegistryError
from model.common.value_objects import FrozenModel
from .contracts import ActionTemplate

class ActionRegistry(FrozenModel):
    schema_version:str; templates:tuple[ActionTemplate,...]; enforce_principal_ids:bool=True
    @classmethod
    def load(cls,path:Path):return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    @model_validator(mode="after")
    def exact_principal_registry(self):
        ids=tuple(item.template_id for item in self.templates)
        if len(ids)!=len(set(ids)): raise RegistryError("DUPLICATE_ACTION_ID")
        principal=("A00","A11","A13","A21","A22","A23","A31","A32","A33","A41","A42","A43",
                   "A51","A52","A53","A54","A55","A61","A62","A63","A64","A71","A72")
        if self.enforce_principal_ids and ids!=principal: raise RegistryError("PRINCIPAL_ACTION_SET_MISMATCH")
        return self
