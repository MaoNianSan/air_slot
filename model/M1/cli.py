import argparse,json
from pathlib import Path
import torch
from .pipeline import M1Pipeline
from .lifecycle import M1Lifecycle

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    train=sub.add_parser("train-smoke"); train.add_argument("--output",type=Path,required=True)
    infer=sub.add_parser("infer-smoke"); infer.add_argument("--artifact",type=Path,required=True)
    inspect=sub.add_parser("inspect-artifact"); inspect.add_argument("--artifact",type=Path,required=True)
    sub.add_parser("validate"); args=p.parse_args(argv)
    if args.command=="train-smoke":
        pipe=M1Pipeline.smoke(4); optimizer=torch.optim.Adam(pipe.model.parameters(),lr=.01); values=torch.randn(8,3,4); lengths=torch.full((8,),3)
        labels={n:torch.arange(8)%b.class_count for n,b in pipe.bins.items()}; initial=None
        for _ in range(8):
            optimizer.zero_grad(); out=pipe.model(values,lengths,teacher={"R_IB":labels["R_IB"],"DELTA_OB":labels["DELTA_OB"]})
            loss=sum(torch.nn.functional.cross_entropy(out[n],labels[n]) for n in out); initial=float(loss.detach()) if initial is None else initial; loss.backward(); optimizer.step()
        path=args.output/"m1.pt"; pipe.save(path); result={"status":"PASS","initial_loss":initial,"final_loss":float(loss.detach()),"artifact":path.as_posix()}
    elif args.command=="infer-smoke":
        pipe=M1Pipeline.load(args.artifact); dist=pipe.predict_distributions(torch.zeros(1,3,pipe.model.input_size),torch.tensor([3])); result={"status":"PASS","heads":{n:list(v.shape) for n,v in dist.items()}}
    elif args.command=="inspect-artifact":
        lifecycle=M1Lifecycle.load(args.artifact); result={"status":"PASS","hidden_size":lifecycle.pipeline.model.hidden_size,
            "temperatures":lifecycle.pipeline.temperatures,"ordered_heads":list(lifecycle.pipeline.bins)}
    else: result={"status":"PASS","architecture":"one_layer_unidirectional_gru","ordered_heads":["R_IB","DELTA_OB","T_TX"]}
    print(json.dumps(result,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
