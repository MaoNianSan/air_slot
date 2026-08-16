import argparse,json
from pathlib import Path
from exp.exp1.runner import Exp1Runner
from exp.exp2.runner import Exp2Runner
from exp.exp3.runner import Exp3Runner
from exp.exp4.runner import Exp4Runner
from exp.reporting.figures import generate_figure_bundle
from exp.reporting.tables import generate_table_bundle
from exp.common.contracts import RuntimeMode, write_cross_contract
from exp.status import write_status_manifests

RUNNERS={"exp1":Exp1Runner,"exp2":Exp2Runner,"exp3":Exp3Runner,"exp4":Exp4Runner}

def main(argv=None):
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True)
    smoke=s.add_parser("smoke-all");smoke.add_argument("--output",type=Path,required=True)
    run=s.add_parser("run");run.add_argument("--experiment",choices=RUNNERS,required=True);run.add_argument("--input",type=Path,required=True);run.add_argument("--output",type=Path,required=True);run.add_argument("--smoke",action="store_true");run.add_argument("--mode",choices=[item.value for item in RuntimeMode],default="development");run.add_argument("--approve-paper-full",action="store_true");run.add_argument("--protocol-variants",action="store_true")
    report=s.add_parser("report");report.add_argument("--input",type=Path,required=True);report.add_argument("--output",type=Path,required=True)
    status=s.add_parser("status");status.add_argument("--output",type=Path,default=Path("."))
    args=p.parse_args(argv)
    if args.command=="smoke-all":
        args.output.mkdir(parents=True,exist_ok=True);summary={}
        for name,cls in RUNNERS.items():
            result=cls().run([{"episode_id":"smoke-e1","metric":1.0}],smoke=True,runtime_mode="smoke");path=args.output/f"{name}.json";path.write_text(result.model_dump_json(indent=2),encoding="utf-8");summary[name]=len(result.rows)
        out={"status":"PASS","paper_result":False,"smoke":True,"rows":summary}
    elif args.command=="run":
        rows=json.loads(args.input.read_text(encoding="utf-8"));result=RUNNERS[args.experiment]().run(rows,smoke=args.smoke,runtime_mode=args.mode,paper_full_approved=args.approve_paper_full,protocol_variants=args.protocol_variants,split="FINAL_TEST" if args.mode=="paper_full" else "DEVELOPMENT");args.output.mkdir(parents=True,exist_ok=True);(args.output/"result.json").write_text(result.model_dump_json(indent=2),encoding="utf-8");(args.output/"manifest.json").write_text(result.manifest.model_dump_json(indent=2),encoding="utf-8");out={"status":"PASS","rows":len(result.rows),"paper_result":result.manifest.paper_result,"runtime_mode":result.manifest.runtime_mode}
    elif args.command=="report":
        args.output.mkdir(parents=True,exist_ok=True);generate_figure_bundle([{"variant":0,"metric":1},{"variant":1,"metric":.8}],"fig_smoke",args.output,{"experiment":"smoke","dataset_id":"synthetic","dataset_role":"NOT_PAPER","cohort":"smoke","metric_definition":"diagnostic","filters":[],"CI_method":"none","source_artifacts":[],"config_hash":"smoke"});generate_table_bundle([{"variant":"a","metric":1}],"tab_smoke",args.output,{"experiment":"smoke","scientific_question":"none","dataset_id":"synthetic","dataset_role":"NOT_PAPER","cohort":"smoke","primary_metric":"diagnostic","bootstrap_unit":"episode","source_artifact":"smoke","caption_candidate":"Smoke","notes":"not paper"});out={"status":"PASS","paper_result":False}
    else:
        write_cross_contract(args.output/"EXPERIMENT_CROSS_CONTRACT.json")
        cross,implementation=write_status_manifests(args.output)
        out={"status":"PASS","cross_contract":str(cross),"implementation_status":str(implementation)}
    print(json.dumps(out,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
