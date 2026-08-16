from model.common.identity import content_id
from model.common.errors import ContractError
from .contracts import ExperimentResult,ExperimentRunManifest

class BaseRunner:
    experiment="";variants=()
    def run(self,rows,*,dataset="data2_2019",smoke=False,paper_eligible=False):
        roles={"data2_2019":"MAIN_TEXT_PRINCIPAL","data1_2019":"APPENDIX_REPLICATION"}
        if dataset not in roles:raise ContractError("EXPERIMENT_DATASET_ROLE_UNKNOWN")
        output=[]
        for variant in self.variants:
            for row in rows:
                if "metric" not in row:raise ContractError("EXPERIMENT_METRIC_MISSING")
                output.append({"experiment":self.experiment,"variant":variant,"episode_id":row["episode_id"],"metric":float(row["metric"]),"status":"SMOKE" if smoke else "EVALUATED"})
        manifest=ExperimentRunManifest(experiment=self.experiment,dataset_instance_id=dataset,dataset_role=roles[dataset],variant_ids=tuple(self.variants),input_manifest_hash=content_id(rows),config_hash=content_id({"variants":self.variants}),status="PASS",paper_result=bool(paper_eligible and not smoke),smoke=smoke)
        return ExperimentResult(manifest=manifest,rows=tuple(output))
