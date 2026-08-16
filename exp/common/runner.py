from datetime import datetime, timezone

from model.common.identity import content_id
from model.common.errors import ContractError
from .contracts import ExperimentResult,ExperimentRunManifest
from .datasets import dataset_role

class BaseRunner:
    experiment="";variants=()
    def run(self,rows,*,dataset="data2_2019",smoke=False,paper_eligible=False,
            split="DEVELOPMENT", scientific_config_hash="UNSET", evaluation_config_hash="UNSET",
            registry_manifest_hash="UNSET", split_contract_hash="UNSET", seed=0,
            git_commit_sha="UNSET", model_artifact_hashes=None):
        role=dataset_role(dataset)
        if not rows: raise ContractError("EXPERIMENT_COHORT_EMPTY")
        output=[]
        for variant in self.variants:
            for row in rows:
                if smoke:
                    if "metric" not in row: raise ContractError("EXPERIMENT_METRIC_MISSING")
                    metric=float(row["metric"])
                else:
                    metrics=row.get("variant_metrics")
                    if not isinstance(metrics, dict) or variant not in metrics:
                        raise ContractError("EXPERIMENT_FROZEN_ARTIFACT_VARIANT_OUTPUT_REQUIRED")
                    metric=float(metrics[variant])
                output.append({"experiment":self.experiment,"variant":variant,"episode_id":row["episode_id"],
                               "decision_node_id":row.get("decision_node_id"),"metric":metric,
                               "status":"SMOKE" if smoke else "EVALUATED",
                               "model_path":row.get("model_path","FORMAL"),
                               "information_cutoff":row.get("information_cutoff")})
        variant_hashes={variant:content_id(tuple(item for item in output if item["variant"]==variant)) for variant in self.variants}
        manifest=ExperimentRunManifest(experiment=self.experiment,dataset_instance_id=dataset,dataset_role=role,
            variant_ids=tuple(self.variants),input_manifest_hash=content_id(rows),
            config_hash=content_id({"variants":self.variants,"experiment":self.experiment}),status="PASS",
            paper_result=bool(paper_eligible and not smoke),smoke=smoke,git_commit_sha=git_commit_sha,
            scientific_config_hash=scientific_config_hash,evaluation_config_hash=evaluation_config_hash,
            registry_manifest_hash=registry_manifest_hash,split_contract_hash=split_contract_hash,
            cohort_hash=content_id(tuple(sorted((r["episode_id"],r.get("decision_node_id")) for r in rows))),
            variant_hashes=variant_hashes,model_artifact_hashes=model_artifact_hashes or {},
            scenario_count=sum(int(r.get("scenario_count",0)) for r in rows),random_seed=seed,split=split,
            primary_metric="metric",paper_eligible=bool(paper_eligible),
            timestamp=datetime.now(timezone.utc).isoformat())
        manifest.final_test_guard()
        return ExperimentResult(manifest=manifest,rows=tuple(output))

    def run_from_frozen_artifacts(self, artifacts, *, cohort_builder, variant_builder,
                                  metric_fn, dataset="data2_2019", **manifest_kwargs):
        """Build paired variant metrics without mutating the formal artifact."""
        formal_hash = content_id(artifacts)
        cohort = tuple(cohort_builder(artifacts))
        rows = []
        for row in cohort:
            variant_metrics = {}
            for variant in self.variants:
                transformed = variant_builder(artifacts, row, variant)
                variant_metrics[variant] = float(metric_fn(artifacts, transformed, row, variant))
                if content_id(artifacts) != formal_hash:
                    raise ContractError("EXPERIMENT_MUTATED_FORMAL_ARTIFACT")
            rows.append({**row, "variant_metrics": variant_metrics,
                         "formal_artifact_hash": formal_hash})
        return self.run(rows, dataset=dataset, smoke=False, **manifest_kwargs)
