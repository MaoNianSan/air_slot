import json
from datetime import datetime,timezone
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

def generate_figure_bundle(rows,figure_id,output:Path,metadata):
    output.mkdir(parents=True,exist_ok=True);frame=pd.DataFrame(rows);frame.to_csv(output/f"{figure_id}.csv",index=False)
    fig,ax=plt.subplots(figsize=(5,3));x=frame.iloc[:,0];y=frame.iloc[:,1];ax.plot(x,y,marker="o");ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=.2);fig.tight_layout();fig.savefig(output/f"{figure_id}.pdf");fig.savefig(output/f"{figure_id}.png",dpi=180);plt.close(fig)
    meta={"figure_id":figure_id,**metadata,"source_data":f"{figure_id}.csv","generated_at":datetime.now(timezone.utc).isoformat()};(output/f"{figure_id}.json").write_text(json.dumps(meta,indent=2,sort_keys=True),encoding="utf-8");return meta
