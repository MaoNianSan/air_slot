import numpy as np

def summarize_formal(outputs):
    values=[x.formal_estimand_value.value_cu for x in outputs
            if x.formal_estimand_value.value_cu is not None]
    if not values:return {"count":0,"mean":None,"median":None,"q90":None}
    return {"count":len(values),"mean":float(np.mean(values)),"median":float(np.median(values)),"q90":float(np.quantile(values,.9))}

def reconstruct_realized(realized:dict,context:dict):
    return {"artifact_layer":"EVALUATION","realized_inputs":tuple(sorted(realized)),"context_version":context.get("version")}
