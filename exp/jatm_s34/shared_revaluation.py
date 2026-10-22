"""Linear CU revaluation of expected native consequences; no model inference."""
from dataclasses import replace
from model.M2.comparison_support import phi_c
from exp.jatm_section5.run_development import _domain_vector


def revalue_nodes(nodes,source,target):
    result=[]
    for node in nodes:
        components={};scores={};domains={}
        for rep,vector in node.component_scores.items():
            value=None if vector is None else {k:v*source.scales[k]/target.scales[k] for k,v in vector.items()}
            components[rep]=value
            scores[rep]=None if value is None else phi_c(value)
            domains[rep]=None if value is None else _domain_vector(value)
        result.append(replace(node,component_scores=components,consequence_scores=scores,domain_scores=domains))
    return tuple(result)
