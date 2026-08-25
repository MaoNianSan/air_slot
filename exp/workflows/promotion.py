import json,shutil
from pathlib import Path
from model.common.errors import ContractError
from exp.common.datasets import DATASET_ROLES

def promote(source:Path,target:Path,*,eligible:bool,destination_role:str|None=None):
    if not eligible:raise ContractError("PAPER_PROMOTION_NOT_ELIGIBLE")
    manifest_path=source/"manifest.json"
    if not manifest_path.is_file():raise ContractError("PROMOTION_MANIFEST_MISSING")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("paper_result") or manifest.get("smoke") or not manifest.get("paper_eligible", True):raise ContractError("PAPER_PROMOTION_GATE_FAILED")
    dataset=manifest.get("dataset_instance_id");declared=manifest.get("dataset_role")
    if dataset not in DATASET_ROLES or declared!=DATASET_ROLES[dataset]:raise ContractError("DATASET_ROLE_MANIFEST_MISMATCH")
    if destination_role=="MAIN_TEXT" and declared!="MAIN_TEXT_PRINCIPAL":raise ContractError("MAIN_TEXT_DATASET_ROLE_MISMATCH")
    required=("git_commit_sha","scientific_config_hash","evaluation_config_hash","registry_manifest_hash",
              "dataset_instance_id","dataset_role","split_contract_hash","cohort_hash","variant_hashes",
              "model_artifact_hashes","scenario_count","random_seed","paper_result","smoke","timestamp")
    if any(key not in manifest for key in required):raise ContractError("PROMOTION_MANIFEST_INCOMPLETE")
    if manifest.get("split")=="FINAL_TEST" and manifest.get("tuning_events"):raise ContractError("FINAL_TEST_TUNING_INVALIDATES_PROMOTION")
    target.mkdir(parents=True,exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():dest=target/path.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    return {"status":"PROMOTED","source":source.as_posix(),"target":target.as_posix()}

def write_paper_numbers(numbers,output:Path):
    output.mkdir(parents=True,exist_ok=True);(output/"paper_numbers.json").write_text(json.dumps(numbers,indent=2,sort_keys=True),encoding="utf-8");(output/"manuscript_values.json").write_text(json.dumps(numbers,indent=2,sort_keys=True),encoding="utf-8");macros="\n".join(f"\\newcommand{{\\{key.replace('_','')}}}{{{value}}}" for key,value in sorted(numbers.items()))+"\n";(output/"manuscript_macros.tex").write_text(macros,encoding="utf-8")
