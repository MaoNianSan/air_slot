from datetime import datetime, timezone
import json
from pathlib import Path

import torch
from pydantic import ValidationError

from model.M1.pipeline import M1Pipeline
from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.M3.contracts import CandidateAction
from model.M4.contracts import M4DecisionRequest
from model.M4.decision import evaluate_request
from model.PRE.foundation import PREBuildRequest, build_pre_state


def _pre(dataset):
    return build_pre_state(PREBuildRequest(episode_id=f"smoke-{dataset}",predecessor_id="P",successor_id="S",
        decision_time=datetime(2019,1,1,12,tzinfo=timezone.utc),information_cutoff=datetime(2019,1,1,11,55,tzinfo=timezone.utc),
        config_hash="sha256:smoke",registry_hash="sha256:smoke",dataset_instance_id=dataset)).pre_state


def _candidate(episode):
    return CandidateAction(candidate_action_id=f"A00:{episode}",template_id="A00",action_family="null",parameters={},
        precondition_state="TRUE",authority_capabilities=(),mitigation={},induced={},response_model="DETERMINISTIC",
        response_parameters={"value":0.0},response_provenance="OPERATOR_INDUSTRY",coverage="FULL",
        preparation_time_minutes=0,deadline_semantics="scenario_deadline")


def run_scientific_smoke(output_root:Path,*,scenario_count=64,seed=0):
    output={"evaluation_scope":"BOUNDED_SCIENTIFIC_SMOKE","paper_result":False}
    for dataset in ("data2_2019","data1_2019"):
        pre=_pre(dataset); pipe=M1Pipeline.smoke(4); scenarios=pipe.sample_from_pre(pre,torch.zeros(1,3,4),torch.tensor([3]),observed={},count=scenario_count,seed=seed)
        m2=M2Mapper(ValuationRegistry.smoke()).map_scenarios([row.model_dump(mode="json") for row in scenarios],{
            "turnaround_buffer_minutes":5,"downstream_exposure":1,"passenger_exposure":100,
            "itinerary_disruption_events":0,"service_threshold_minutes":15,"taxi_reference_minutes":10})
        support={item.target_name:(item.support_state.value if hasattr(item.support_state,"value") else str(item.support_state)) for item in pre.target_support}
        try:
            decision=evaluate_request(M4DecisionRequest(pre_state=pre,m1_scenarios=scenarios,m2_consequences=m2,
                candidates=(_candidate(pre.decision_node.episode_id),),seed=seed))
            decision_status=decision.decision_outcome
        except ValidationError as exc:
            if dataset!="data1_2019" or "M4_M2_FORMAL_TOTAL_UNAVAILABLE" not in str(exc): raise
            decision_status="NO_AUTHORITATIVE_DECISION_SUPPORT"
        output[dataset]={"status":"PASS","decision_node_status":pre.decision_node.status,"r_ob_support":support["R_OB"],
            "scenarios":len(scenarios),"m2_rows":len(m2),"decision":decision_status}
    output_root.mkdir(parents=True,exist_ok=True); (output_root/"scientific_smoke.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return output


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--scenario-count",type=int,default=64);parser.add_argument("--seed",type=int,default=0)
    args=parser.parse_args();print(json.dumps(run_scientific_smoke(args.output,scenario_count=args.scenario_count,seed=args.seed),sort_keys=True))


if __name__=="__main__":main()

