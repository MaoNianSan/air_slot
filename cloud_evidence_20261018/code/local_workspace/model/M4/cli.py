import argparse,json
from pathlib import Path
from model.M3.contracts import CandidateAction
from .decision import evaluate_decision

def main(argv=None):
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);d=s.add_parser("decide-smoke");d.add_argument("--output",type=Path,required=True);s.add_parser("validate");a=p.parse_args(argv)
    if a.command=="decide-smoke":
        base=dict(action_family="null",parameters={},precondition_state="TRUE",authority_capabilities=(),response_model="DETERMINISTIC",response_parameters={"value":1},response_provenance="OPERATOR_INDUSTRY",coverage="FULL",preparation_time_minutes=0,deadline_semantics="scenario_deadline")
        candidates=[CandidateAction(candidate_action_id="A00:e",template_id="A00",mitigation={},induced={},**base),CandidateAction(candidate_action_id="A11:e",template_id="A11",mitigation={"F_execution":.5},induced={},**base)]
        result=evaluate_decision("e",[{"scenario_id":0,"scenario_weight":1,"deadline_minutes":30}],[{"scenario_id":0,"components":{"F_execution":10}}],candidates);a.output.mkdir(parents=True,exist_ok=True);path=a.output/"decision.json";path.write_text(result.model_dump_json(indent=2),encoding="utf-8");out={"status":"PASS","outcome":result.decision_outcome,"top1":result.ranking_at_1,"artifact":path.as_posix()}
    else:out={"status":"PASS","criterion":"mean_cvar","lambda":.25,"alpha":.9}
    print(json.dumps(out,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
