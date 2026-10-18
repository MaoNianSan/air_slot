import json
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

def generate_table_bundle(rows,table_id,output:Path,metadata):
    output.mkdir(parents=True,exist_ok=True);frame=pd.DataFrame(rows);frame.to_csv(output/f"{table_id}.csv",index=False);(output/f"{table_id}.tex").write_text(frame.to_latex(index=False),encoding="utf-8");meta={"table_id":table_id,**metadata,"source_data":f"{table_id}.csv","generated_at":datetime.now(timezone.utc).isoformat()};(output/f"{table_id}.json").write_text(json.dumps(meta,indent=2,sort_keys=True),encoding="utf-8");return meta
