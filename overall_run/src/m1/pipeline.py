from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

import torch

from .adapter import PublishedPreBundle, build_input_bundle
from .config import M1Settings
from .contracts import M1PredictionBundle, M1RunManifest, TriggerType, M1_CONTRACT_ID
from .distribution import (
    DiscreteBins,
    derive_joint_samples,
    learned_upper_bins,
    predecessor_bins,
)
from .model import SingleLightweightGRU
from .runtime import M1UpdateService


class M1ScientificNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class M1PipelineResult:
    prediction: M1PredictionBundle
    joint_samples: tuple


def require_training_support(bundle: PublishedPreBundle) -> dict[str, str]:
    from .adapter.target_builder import build_target_contracts

    statuses: dict[str, str] = {}
    for _, episode in bundle.episodes.iterrows():
        for target, contract in build_target_contracts(episode, bundle.events).items():
            previous = statuses.get(target)
            if previous is None or previous == "UNSUPPORTED":
                statuses[target] = contract.m1_support_level
    if any(statuses.get(target) in {None, "UNSUPPORTED"} for target in ("R_IB", "R_OB", "T_TX")):
        raise M1ScientificNotReady("M1_SCIENTIFIC_NOT_READY")
    return statuses


class M1Pipeline:
    def __init__(
        self,
        service: M1UpdateService,
        settings: M1Settings,
        bundle: PublishedPreBundle,
    ) -> None:
        self.service = service
        self.settings = settings
        self.bundle = bundle

    @classmethod
    def engineering(
        cls,
        bundle: PublishedPreBundle,
        settings: M1Settings,
        feature_order: tuple[str, ...],
        train_targets: Mapping[str, list[float]],
        *,
        model_version: str = "M1_GRU_ENGINEERING_V1",
        temperature_version: str = "M1_TEMPERATURE_IDENTITY_V1",
    ) -> "M1Pipeline":
        missing_targets = sorted({"R_OB", "T_TX"} - set(train_targets))
        if missing_targets:
            raise ValueError("M1_TRAIN_BIN_SUPPORT_MISSING:" + ",".join(missing_targets))
        if not feature_order:
            raise ValueError("M1_FEATURE_ORDER_EMPTY")
        bins: dict[str, DiscreteBins] = {
            "R_IB": predecessor_bins(settings.bin_minutes),
            "R_OB": learned_upper_bins(
                train_targets["R_OB"],
                quantile=settings.learned_upper_quantile,
                bin_minutes=settings.bin_minutes,
            ),
            "T_TX": learned_upper_bins(
                train_targets["T_TX"],
                quantile=settings.learned_upper_quantile,
                bin_minutes=settings.bin_minutes,
            ),
        }
        torch.manual_seed(settings.base_seed)
        model = SingleLightweightGRU(
            len(feature_order),
            {name: target_bins.count for name, target_bins in bins.items()},
            hidden_size=settings.hidden_size,
        )
        service = M1UpdateService(
            model,
            feature_order,
            bins,
            {name: 1.0 for name in bins},
            model_version=model_version,
            temperature_version=temperature_version,
        )
        return cls(service, settings, bundle)

    def update_and_predict(
        self,
        episode_id: str,
        query_time: object,
        trigger_type: TriggerType | str,
        commit_state: bool,
        *,
        snapshot_id: str | None = None,
        snapshot_version: int = 1,
        previous_query_time: object | None = None,
        successor_sobt: datetime | None = None,
        turnaround_floor_minutes: float | None = None,
        taxi_reference_minutes: float | None = None,
        observed_event_times: Mapping[str, datetime] | None = None,
    ) -> M1PipelineResult:
        input_bundle = build_input_bundle(
            self.bundle,
            episode_id,
            query_time,
            snapshot_id=snapshot_id,
            snapshot_version=snapshot_version,
            previous_query_time=previous_query_time,
        )
        prediction = self.service.update_and_predict(
            input_bundle, trigger_type, commit_state
        )
        samples = derive_joint_samples(
            input_bundle,
            prediction.distributions,
            sample_count=self.settings.sample_count,
            base_seed=self.settings.base_seed,
            successor_sobt=successor_sobt,
            turnaround_floor_minutes=turnaround_floor_minutes,
            taxi_reference_minutes=taxi_reference_minutes,
            observed_event_times=observed_event_times,
        )
        return M1PipelineResult(prediction, samples)

    def manifest(self, target_support: Mapping[str, str]) -> M1RunManifest:
        required = {"R_IB", "R_OB", "T_TX"}
        scientific = (
            "PASS"
            if required.issubset(target_support)
            and all(target_support[name] != "UNSUPPORTED" for name in required)
            else "NOT_READY"
        )
        return M1RunManifest(
            pre_bundle_identity=self.bundle.identity,
            m1_contract_id=M1_CONTRACT_ID,
            model_version=self.service.model_version,
            temperature_version=self.service.temperature_version,
            split_definition={
                "calibration_source": "validation",
                "calibration_tail_fraction": self.settings.calibration_tail_fraction,
            },
            engineering_status="PASS",
            scientific_status=scientific,
            target_support_status=dict(target_support),
            training_status="PASS" if scientific == "PASS" else "BLOCKED",
            calibration_status="PASS" if scientific == "PASS" else "BLOCKED",
            evaluation_status="ENGINEERING_READY",
            m2_interface_status="M2_CONTRACT_MISMATCH",
        )
