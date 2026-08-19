"""V2 principal M1 state-estimator pipeline.

Round-2 M1 V2 real estimator:

    T_IB_A00 (discrete hazard) -> D_OB (hurdle + conditional quantile)
        -> D_TX (hurdle + conditional quantile, conditioned on formal D_OB)
    R_IB = max(0, T_IB_A00 - t), D_TO = D_OB + D_TX (derived).

The V1 signed estimator (R_IB -> DELTA_OB -> T_TX categorical) is
LEGACY_V1/HISTORICAL_ONLY: ``M1Pipeline.load`` can still deserialize frozen V1
artifacts for provenance, but no V1 semantics are presented as principal and
``sample_from_pre`` refuses V1 models.
"""

from pathlib import Path

import torch

from .contracts import HazardBinContract, HurdleQuantileContract, TargetBinContract
from .data import M1NormalizationArtifact
from .network import M1V2GRU, OrderedEventGRU
from .scenarios import ancestral_sample_v2
from .loss import hazard_pmf, monotone_positive_quantiles

V1_TO_V2_SUPPORT = {"R_IB": "T_IB_A00", "DELTA_OB": "D_OB", "T_TX": "D_TX"}


class M1Pipeline:
    """V2 principal pipeline (hazard + hurdle-quantile heads)."""

    def __init__(self, model, contracts, temperatures=None, normalization=None):
        self.model = model
        self.contracts = contracts
        self.temperatures = temperatures or {name: 1.0 for name in contracts}
        self.normalization = normalization

    @property
    def bins(self):
        """Legacy alias for consumers that only read the contract table."""
        return self.contracts

    @classmethod
    def smoke(cls, input_size=4):
        """Synthetic fixture helper; never resolves formal scientific bins."""
        contracts = {
            "T_IB_A00": HazardBinContract(target_name="T_IB_A00", bin_width_minutes=5,
                                          max_finite_minutes=60),
            "D_OB": HurdleQuantileContract(target_name="D_OB", bin_width_minutes=5,
                                           max_finite_minutes=60,
                                           quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9)),
            "D_TX": HurdleQuantileContract(target_name="D_TX", bin_width_minutes=5,
                                           max_finite_minutes=30,
                                           quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9)),
        }
        torch.manual_seed(0)
        return cls(M1V2GRU(input_size, 16, contracts["T_IB_A00"],
                           contracts["D_OB"], contracts["D_TX"]), contracts)

    @classmethod
    def from_scientific_config(cls, scientific, *, input_size, normalization,
                               hidden_size=None):
        if not isinstance(normalization, M1NormalizationArtifact) \
                or normalization.fitted_split != "train":
            raise ValueError("M1_FORMAL_TRAIN_NORMALIZATION_REQUIRED")
        width = scientific.parameters["m1_bin_width_minutes"].value
        ib_max = scientific.parameters["m1_r_ib_max_finite_minutes"].value
        d_ob_max = scientific.parameters["m1_delta_ob_max_finite_minutes"].value
        d_tx_max = scientific.parameters["m1_t_tx_max_finite_minutes"].value
        quantile_levels = scientific.parameters["m1_v2_quantile_levels"].value
        if None in (ib_max, d_ob_max, d_tx_max) or not quantile_levels:
            raise ValueError("M1_V2_FINITE_SUPPORT_UNFROZEN")
        selected = scientific.parameters["m1_hidden_size"].value
        hidden = selected if hidden_size is None else hidden_size
        if hidden is None:
            raise ValueError("M1_HIDDEN_SIZE_SELECTION_REQUIRED")
        candidates = scientific.parameters.get("m1_hidden_size_candidates")
        if candidates is not None and hidden not in candidates.value:
            raise ValueError("M1_HIDDEN_SIZE_NOT_IN_DEVELOPMENT_CANDIDATES")
        contracts = {
            "T_IB_A00": HazardBinContract(target_name="T_IB_A00",
                                          bin_width_minutes=width,
                                          max_finite_minutes=ib_max),
            "D_OB": HurdleQuantileContract(target_name="D_OB", bin_width_minutes=width,
                                           max_finite_minutes=d_ob_max,
                                           quantile_levels=tuple(quantile_levels)),
            "D_TX": HurdleQuantileContract(target_name="D_TX", bin_width_minutes=width,
                                           max_finite_minutes=d_tx_max,
                                           quantile_levels=tuple(quantile_levels)),
        }
        return cls(M1V2GRU(input_size, hidden, contracts["T_IB_A00"],
                           contracts["D_OB"], contracts["D_TX"]),
                   contracts, normalization=normalization)

    def predict_distributions(self, values, lengths):
        """Current-state marginal distribution summary (V2 schema).

        Returns ``{T_IB_A00: hazard PMF, D_OB: {zero_probability,
        positive_quantiles_minutes}, D_TX: {...}}``.  Successor heads are
        summarized conditional on the marginal T_IB_A00 mixture (D_OB) and on
        that mixture plus the expected D_OB (D_TX).  Ancestral scenario draws
        always use the true conditional heads via ``sample_from_pre``.
        """
        self.model.eval()
        with torch.no_grad():
            history = self.model.encode_history(values, lengths)
            hazard_logits = self.model.hazard_logits(history)
            pmf = hazard_pmf(hazard_logits, self.contracts["T_IB_A00"])
            zero_probs = []
            quantiles = []
            for bin_index in range(self.contracts["T_IB_A00"].class_count):
                zero_logit, quantile_logits = self.model.d_ob_heads(
                    history, torch.full((history.shape[0],), bin_index, dtype=torch.long)
                )
                zero_probs.append(torch.sigmoid(zero_logit))
                quantiles.append(monotone_positive_quantiles(quantile_logits))
            d_ob_zero = sum(weight * value for weight, value in zip(
                pmf.t(), zero_probs)) / pmf.sum(dim=-1, keepdim=True).clamp_min(1e-12)
            d_ob_quantiles = sum(weight * value for weight, value in zip(
                pmf.t(), quantiles)) / pmf.sum(dim=-1, keepdim=True).clamp_min(1e-12)
            zero_probability = d_ob_zero.squeeze(-1)
            expected_d_ob = (1.0 - zero_probability) * d_ob_quantiles.mean(dim=-1)
            expected_bin = torch.clamp(
                (expected_d_ob / self.contracts["D_OB"].bin_width_minutes).long(),
                0, self.contracts["D_OB"].overflow_index,
            )
            # D_TX summary conditions on the marginal T_IB_A00 mixture by
            # re-running the D_OB parent expectation over each IB bin.
            zero_probe, quantile_probe = self.model.d_tx_heads(
                history, torch.full((history.shape[0],), 0, dtype=torch.long),
                expected_bin,
            )
            d_tx_zero_acc = torch.zeros_like(zero_probe)
            d_tx_quant_acc = torch.zeros_like(quantile_probe)
            for bin_index in range(self.contracts["T_IB_A00"].class_count):
                zero_logit, quantile_logits = self.model.d_tx_heads(
                    history, torch.full((history.shape[0],), bin_index, dtype=torch.long),
                    expected_bin,
                )
                d_tx_zero_acc = d_tx_zero_acc + pmf[:, bin_index:bin_index + 1] * zero_logit
                d_tx_quant_acc = d_tx_quant_acc + pmf[:, bin_index:bin_index + 1] * quantile_logits
            d_tx_zero = d_tx_zero_acc / pmf.sum(dim=-1, keepdim=True).clamp_min(1e-12)
            d_tx_quantiles = d_tx_quant_acc / pmf.sum(dim=-1, keepdim=True).clamp_min(1e-12)
            return {
                "T_IB_A00": pmf,
                "D_OB": {
                    "zero_probability": torch.sigmoid(zero_probability),
                    "positive_quantiles_minutes": d_ob_quantiles,
                },
                "D_TX": {
                    "zero_probability": torch.sigmoid(d_tx_zero.squeeze(-1)),
                    "positive_quantiles_minutes": d_tx_quantiles,
                },
            }

    def sample_from_pre(self, pre_state, values, lengths, *, observed, count, seed,
                        taxi_reference=None):
        if not isinstance(self.model, M1V2GRU):
            raise ValueError("M1_V1_PRINCIPAL_DISABLED")
        if values.shape[0] != 1:
            raise ValueError("formal scenario generation accepts one decision node at a time")
        support = {}
        for item in pre_state.target_support:
            name = V1_TO_V2_SUPPORT.get(item.target_name, item.target_name)
            support[name] = (item.support_state.value
                             if hasattr(item.support_state, "value")
                             else str(item.support_state))
        stage = pre_state.decision_node.operational_stage
        stage = stage.value if hasattr(stage, "value") else str(stage)
        decision_time_utc = pre_state.decision_node.decision_time.isoformat()
        self.model.eval()
        with torch.no_grad():
            history = self.model.encode_history(values, lengths)
        schedule = pre_state.successor_state.get("schedule_reference")
        schedule_value = None if schedule is None else schedule.value
        scheduled_ob_utc = None
        origin_airport_id = None
        if isinstance(schedule_value, dict):
            scheduled = schedule_value.get("scheduled_departure_utc")
            scheduled_ob_utc = None if scheduled is None else scheduled.isoformat()
            origin_airport_id = schedule_value.get("origin_airport_id")
        reference_context = {
            "taxi_reference_id": None,
            "taxi_reference_hash": None,
            "taxi_reference_fallback_level": None,
            "taxi_reference_support_state": None,
        }
        if taxi_reference is not None:
            if getattr(taxi_reference, "dataset_instance_id", None) != "data2_2019" \
                    or getattr(taxi_reference, "rule_id", None) != "DATA2_TAXI_REFERENCE":
                raise ValueError("M1_REQUIRES_TRAIN_FROZEN_DATA2_TAXI_REFERENCE")
            lookup = taxi_reference.lookup(origin_airport_id)
            state = getattr(lookup.support_state, "value", str(lookup.support_state))
            flags = set(getattr(lookup, "quality_flags", ()))
            fallback = next((flag.removeprefix("REFERENCE_LEVEL_") for flag in flags
                             if flag.startswith("REFERENCE_LEVEL_")), None)
            reference_context = {
                "taxi_reference_id": taxi_reference.reference_id,
                "taxi_reference_hash": getattr(taxi_reference, "manifest_freeze_id", None),
                "taxi_reference_fallback_level": fallback,
                "taxi_reference_support_state": state,
            }
        return ancestral_sample_v2(
            self.model, history, self.contracts,
            episode_id=pre_state.decision_node.episode_id,
            decision_node_id=pre_state.decision_node.decision_node_id,
            stage=stage, observed=observed, count=count, seed=seed,
            target_support=support, decision_time_utc=decision_time_utc,
            scheduled_ob_utc=scheduled_ob_utc,
            temperatures=self.temperatures, **reference_context,
        )

    def summarize(self, scenarios, **kwargs):
        from .summaries import horizon_summaries
        return horizon_summaries(scenarios, **kwargs)

    def warning_probability(self, scenarios, **kwargs):
        from .warning import warning_probability
        return warning_probability(scenarios, **kwargs)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state": self.model.state_dict(),
            "input_size": self.model.input_size,
            "hidden_size": self.model.hidden_size,
            "contracts": {
                name: contract.model_dump() for name, contract in self.contracts.items()
            },
            "contract_version": "M1_STATE_ESTIMATOR_V2",
            "temperatures": self.temperatures,
            "normalization": None if self.normalization is None
                else self.normalization.model_dump(mode="json"),
        }, path)

    @classmethod
    def load(cls, path: Path):
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if "bins" in payload and "contracts" not in payload:
            # LEGACY_V1 frozen artifact: keep deserializable for provenance.
            bins = {name: TargetBinContract(**value) for name, value in payload["bins"].items()}
            model = OrderedEventGRU(payload["input_size"], payload["hidden_size"], bins)
            model.load_state_dict(payload["state"])
            pipeline = cls(model, bins, payload["temperatures"])
            pipeline._legacy_v1 = True
            return pipeline
        contracts = {
            name: (HazardBinContract(**value) if name == "T_IB_A00"
                   else HurdleQuantileContract(**value))
            for name, value in payload["contracts"].items()
        }
        model = M1V2GRU(payload["input_size"], payload["hidden_size"],
                        contracts["T_IB_A00"], contracts["D_OB"], contracts["D_TX"])
        model.load_state_dict(payload["state"])
        normalization = payload.get("normalization")
        if normalization is not None:
            normalization = M1NormalizationArtifact.model_validate(normalization)
        return cls(model, contracts, payload["temperatures"], normalization)
