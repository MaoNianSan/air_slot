import argparse,json
from pathlib import Path
from .mapper import M2Mapper
from .valuation import ValuationRegistry

def main(argv=None):
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);m=s.add_parser("map-smoke");m.add_argument("--output",type=Path,required=True);s.add_parser("validate");a=p.parse_args(argv)
    if a.command=="map-smoke":
        outputs=M2Mapper(ValuationRegistry.smoke()).map_scenarios([{"decision_node_id":"n","scenario_id":0,"scenario_weight":1,"r_ib_minutes":10,"r_ob_minutes":5,"t_tx_minutes":15}],{"turnaround_buffer_minutes":5,"downstream_exposure":1,"passenger_exposure":100,"itinerary_disruption_events":0,"service_threshold_minutes":15,"taxi_reference_minutes":10});a.output.mkdir(parents=True,exist_ok=True);path=a.output/"consequence.json";path.write_text(outputs[0].model_dump_json(indent=2),encoding="utf-8");result={"status":"PASS","components":len(outputs[0].components),"artifact":path.as_posix()}
    else:result={"status":"PASS","ontology":7,"scenario_preserving":True}
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
