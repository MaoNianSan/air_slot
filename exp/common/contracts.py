from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import json

from pydantic import Field, model_validator
import yaml
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.paths import project_path
from model.common.value_objects import FrozenModel


class RuntimeMode(str, Enum):
    """V5 experiment modes; FAST remains an M1 computational path, not a mode."""

    SMOKE = "smoke"
    DEVELOPMENT = "development"
    PAPER_FULL = "paper_full"
    NUMERICAL_STRESS = "numerical_stress"


class ExperimentCrossContract(FrozenModel):
    """Single source of truth shared by Exp1-Exp4 and reporting."""

    schema_version: str = "V5.0"
    principal_dataset: str = "data2_2019"
    portability_dataset: str = "data1_2019"
    train_start: str = "2019-01-01"
    train_end: str = "2019-06-30"
    calibration_start: str = "2019-07-01"
    calibration_end: str = "2019-07-31"
    development_start: str = "2019-08-01"
    development_end: str = "2019-09-30"
    final_test_start: str = "2019-10-01"
    final_test_end: str = "2019-12-31"
    independent_unit: str = "episode"
    repeated_unit: str = "decision_node"
    numerical_unit: str = "scenario"
    bootstrap_unit: str = "episode"
    bootstrap_replicates: int = 2000
    principal_roll_minutes: int = 5
    sensitivity_roll_minutes: tuple[int, ...] = (10,)
    lead_times_minutes: tuple[int, ...] = (480, 420, 360, 300, 240, 180, 120, 60, 30, 15)
    delay_thresholds_minutes: tuple[int, ...] = (15, 30, 60)
    principal_lambda: float = 0.25
    principal_alpha: float = 0.90
    smoke_scenarios: int = 64
    development_scenarios: tuple[int, ...] = (250, 500)
    paper_full_scenarios: int = 1000
    numerical_reference_scenarios: int = 10000
    hidden_size_candidates: tuple[int, ...] = (8, 16, 32)
    fixed_history_windows_minutes: tuple[int, ...] = (30, 60, 120, 180)
    corruption_q: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75, 1.0)
    full_shuffle_replicates: int = 20
    deep_shuffle_replicates: int = 100
    monte_carlo_grid: tuple[int, ...] = (250, 500, 1000, 2000, 10000)
    rng_streams: tuple[str, ...] = (
        "m1_scenario",
        "m3_m4_response",
        "exp2_lineage_corruption",
        "bootstrap",
        "llm_case_selection",
        "llm_repetition",
    )

    @model_validator(mode="after")
    def validate_contract(self):
        if self.principal_dataset == self.portability_dataset:
            raise ValueError("CROSS_CONTRACT_DATASET_ROLES_COLLIDE")
        if self.bootstrap_unit != self.independent_unit:
            raise ValueError("BOOTSTRAP_UNIT_MUST_BE_EPISODE")
        if self.principal_roll_minutes <= 0 or any(x <= 0 for x in self.lead_times_minutes):
            raise ValueError("CROSS_CONTRACT_TIME_GRID_INVALID")
        if self.paper_full_scenarios != 1000 or self.numerical_reference_scenarios != 10000:
            raise ValueError("V5_SCENARIO_SCALE_INVALID")
        if tuple(sorted(self.hidden_size_candidates)) != (8, 16, 32):
            raise ValueError("V5_HIDDEN_SIZE_CANDIDATES_INVALID")
        if len(set(self.rng_streams)) != len(self.rng_streams):
            raise ValueError("RNG_STREAMS_MUST_BE_UNIQUE")
        return self

    @property
    def split_contract_hash(self) -> str:
        return content_id({
            "train": [self.train_start, self.train_end],
            "calibration": [self.calibration_start, self.calibration_end],
            "development": [self.development_start, self.development_end],
            "final_test": [self.final_test_start, self.final_test_end],
        })

    @property
    def contract_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


def cross_contract_from_mapping(payload: dict) -> ExperimentCrossContract:
    split = payload["split"]
    units = payload["statistical_unit"]
    bootstrap = payload["bootstrap"]
    rolling = payload["rolling"]
    risk = payload["principal_risk"]
    scenarios = payload["scenario_count"]
    return ExperimentCrossContract(
        schema_version=str(payload["schema_version"]),
        train_start=str(split["train"][0]), train_end=str(split["train"][1]),
        calibration_start=str(split["calibration"][0]), calibration_end=str(split["calibration"][1]),
        development_start=str(split["development"][0]), development_end=str(split["development"][1]),
        final_test_start=str(split["final_test"][0]), final_test_end=str(split["final_test"][1]),
        independent_unit=units["independent"], repeated_unit=units["repeated"],
        numerical_unit=units["numerical"], bootstrap_unit=bootstrap["unit"],
        bootstrap_replicates=int(bootstrap["replicates"]),
        principal_roll_minutes=int(rolling["principal_minutes"]),
        sensitivity_roll_minutes=(int(rolling["sensitivity_minutes"]),),
        lead_times_minutes=tuple(payload["lead_times_minutes"]),
        delay_thresholds_minutes=tuple(payload["delay_thresholds_minutes"]),
        principal_lambda=float(risk["lambda"]), principal_alpha=float(risk["alpha"]),
        smoke_scenarios=int(scenarios["smoke"]),
        development_scenarios=tuple(scenarios["development"]),
        paper_full_scenarios=int(scenarios["paper_full"]),
        numerical_reference_scenarios=int(scenarios["numerical_stress"]),
    )


def default_cross_contract() -> ExperimentCrossContract:
    path = project_path("configs", "evaluation", "common.yaml")
    if not path.is_file():
        return ExperimentCrossContract()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return cross_contract_from_mapping(payload)


def write_cross_contract(path: Path, contract: ExperimentCrossContract | None = None) -> Path:
    contract = contract or default_cross_contract()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = contract.model_dump(mode="json")
    payload.update({"contract_hash": contract.contract_hash, "split_contract_hash": contract.split_contract_hash})
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path

class ExperimentRunManifest(FrozenModel):
    experiment:str;dataset_instance_id:str;dataset_role:str;variant_ids:tuple[str,...]
    input_manifest_hash:str;config_hash:str;status:str;paper_result:bool=False;smoke:bool=False
    git_commit_sha:str="UNSET"
    scientific_config_hash:str="UNSET"
    evaluation_config_hash:str="UNSET"
    registry_manifest_hash:str="UNSET"
    split_contract_hash:str="UNSET"
    cohort_hash:str="UNSET"
    variant_hashes:dict[str,str]=Field(default_factory=dict)
    model_artifact_hashes:dict[str,str]=Field(default_factory=dict)
    scenario_count:int=0
    random_seed:int=0
    timestamp:str=""
    split:str="DEVELOPMENT"
    primary_metric:str="UNSET"
    tuning_events:tuple[str,...]=()
    paper_eligible:bool=False
    runtime_mode: str = RuntimeMode.DEVELOPMENT.value
    formal_output_hash: str = "UNSET"
    rng_streams: tuple[str, ...] = ()

    def final_test_guard(self, previous: "ExperimentRunManifest | None" = None) -> None:
        if self.split != "FINAL_TEST":
            return
        if self.tuning_events:
            raise ContractError("FINAL_TEST_TUNING_INVALIDATES_PROMOTION")
        if previous is None:
            return
        frozen = ("scientific_config_hash", "evaluation_config_hash", "registry_manifest_hash",
                  "split_contract_hash", "cohort_hash", "primary_metric", "scenario_count")
        if any(getattr(self, name) != getattr(previous, name) for name in frozen):
            raise ContractError("FINAL_TEST_IMMUTABILITY_VIOLATION")

class BootstrapResult(FrozenModel):
    metric:str;estimate:float;ci_lower:float;ci_upper:float;replicates:int;unit:str="episode"

class ExperimentResult(FrozenModel):
    manifest:ExperimentRunManifest;rows:tuple[dict[str,Any],...]


def assert_final_test_immutable(before: ExperimentRunManifest, after: ExperimentRunManifest) -> None:
    after.final_test_guard(before)
