"""V2 principal M1 state-estimator pipeline.

Round-2 M1 V2 real estimator:

    T_IB_A00 (discrete hazard) -> D_OB (hurdle + conditional quantile)
        -> D_TX (hurdle + conditional quantile, conditioned on formal D_OB)
    R_IB = max(0, T_IB_A00 - t), D_TO = D_OB + D_TX (derived).

Round 2.1 scientific closure (kept):
- The hazard head/label are the INTERNAL remaining-time coordinate
  ``T_IB_REMAINING_HAZARD``; the public primitive ``T_IB_A00`` stays the
  absolute ISO UTC event time and remains the public output key.
- ``predict_distributions`` returns clearly CONDITIONAL head summaries only;
  genuine marginal summaries come from aligned scenarios via
  ``scenario_marginal_summary`` (see ``model.M1.summaries``).

Round 2.2/Tranche 3 representation contract:
- The state-aware representation is
  ``state = concat(GRU(history), projection(r_fast))`` where ``r_fast`` is
  the deterministic current/local-change block (last causal
  row); the Tranche 2.1 schedule-countdown static duplicate is removed.
- PRE publishes typed static/reference context. Train-frozen numeric
  turnaround/taxi references enter ``c_static``; route/carrier/aircraft and
  schedule identity/context retain typed lineage without ordinal encoding.

The V1 signed estimator (R_IB -> DELTA_OB -> T_TX categorical) is
LEGACY_V1/HISTORICAL_ONLY: ``M1Pipeline.load`` can still deserialize frozen V1
artifacts for provenance, but no V1 semantics are presented as principal and
``sample_from_pre`` refuses V1 models.
"""

from pathlib import Path

import torch

from .contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_TEMPERATURE_D_OB_ZERO,
    M1_TEMPERATURE_D_TX_ZERO,
    M1_TEMPERATURE_HAZARD,
    M1_V2_HAZARD_COORDINATE,
    TargetBinContract,
)
from .contracts import M1StaticReferenceContext, static_reference_context_from_pre
from .data import (
    M1NormalizationArtifact,
    STATIC_FEATURE_COUNT,
    fast_features_from_sequence,
)
from .static_features import (
    M1StaticNormalizationArtifact,
    static_reference_features_from_pre,
)
from .network import M1V2GRU, OrderedEventGRU
from .history import HistoryEncoderMode
from .scenarios import ancestral_sample_v2
from .loss import hazard_pmf, monotone_positive_quantiles
from .semantics import M1_V2_HAZARD_COORDINATE_TARGET
from .calibration import M1CalibrationContract, common_calibration_policy
from .tail import EmpiricalTailContinuation

V1_TO_V2_SUPPORT = {"R_IB": "T_IB_A00", "DELTA_OB": "D_OB", "T_TX": "D_TX"}


def conditional_head_summary(model, state, contracts, *, temperatures=None):
    """Conditional head summaries shared by STATE_AWARE and FAST paths.

    Returns a dict keyed by the public primitive names ``{T_IB_A00, D_OB,
    D_TX}``.  ``state`` is the fused representation consumed by the common
    heads (for STATE_AWARE: ``concat(recurrent_repr, projection(r_fast))``;
    for FAST: the deterministic current/local feature block ``r_fast``).

    Round 2.1 summary contract:
    - ``T_IB_A00``: hazard PMF over the INTERNAL remaining-time coordinate
      (public event time ``T_IB_A00 = decision_time + coordinate``).
    - ``D_OB.zero_probability``: exact marginal P(D_OB = 0 | state) over the
      hazard PMF (single logit->prob transformation per head).
    - ``D_OB.positive_quantiles_minutes``: mixture of CONDITIONAL quantile
      curves; explicitly labeled ``CONDITIONAL_MIXTURE_NOT_MARGINAL``.
    - ``D_TX.zero_probability``: exact marginal over the hazard PMF given the
      expected-D_OB-bin proxy (single transformation per head).
    - ``D_TX.positive_quantiles_minutes``: CONDITIONAL curves at the expected
      D_OB bin; explicitly labeled ``..._NOT_MARGINAL``.

    Genuine marginal summaries are computed from aligned ancestral scenarios
    via ``model.M1.summaries.scenario_marginal_summary``; no weighted mean of
    conditional quantiles is ever presented as a marginal quantile here.
    """
    hazard = contracts[M1_V2_HAZARD_COORDINATE_TARGET]
    d_ob = contracts["D_OB"]
    d_tx = contracts["D_TX"]
    temps = temperatures or {}
    batch = state.shape[0]
    device = state.device
    with torch.no_grad():
        hazard_logits = model.hazard_logits(state) / float(
            temps.get(M1_TEMPERATURE_HAZARD, 1.0)
        )
        pmf = hazard_pmf(hazard_logits, hazard)  # (B, K)
        k = hazard.class_count
        d_ob_zero = torch.zeros(batch, device=device)
        d_ob_quant = torch.zeros(batch, d_ob.quantile_count, device=device)
        d_tx_zero = torch.zeros(batch, device=device)
        d_tx_quant = torch.zeros(batch, d_tx.quantile_count, device=device)
        for b in range(k):
            weight = pmf[:, b]  # (B,)
            ib = torch.full((batch,), b, dtype=torch.long, device=device)
            zero_ob, quant_ob = model.d_ob_heads(state, ib)
            # Zero-mass calibration temperature scales ONLY the hurdle
            # Bernoulli zero logit; positive quantile values/logits are never
            # temperature-scaled by it (QUANTILE_CALIBRATION_NOT_APPLIED).
            z_ob = torch.sigmoid(
                zero_ob.squeeze(-1) / float(temps.get(M1_TEMPERATURE_D_OB_ZERO, 1.0))
            )
            q_ob = monotone_positive_quantiles(quant_ob)
            d_ob_zero = d_ob_zero + weight * z_ob
            d_ob_quant = d_ob_quant + weight[:, None] * q_ob
            expected_d_ob = (1.0 - z_ob) * q_ob.mean(dim=-1)
            finite_expected_bin = torch.clamp(
                torch.floor(expected_d_ob / d_ob.bin_width_minutes).long(),
                0,
                d_ob.overflow_index - 1,
            )
            expected_bin = torch.where(
                expected_d_ob > d_ob.max_finite_minutes,
                torch.full_like(finite_expected_bin, d_ob.overflow_index),
                finite_expected_bin,
            )
            zero_tx, quant_tx = model.d_tx_heads(state, ib, expected_bin)
            z_tx = torch.sigmoid(
                zero_tx.squeeze(-1) / float(temps.get(M1_TEMPERATURE_D_TX_ZERO, 1.0))
            )
            q_tx = monotone_positive_quantiles(quant_tx)
            d_tx_zero = d_tx_zero + weight * z_tx
            d_tx_quant = d_tx_quant + weight[:, None] * q_tx
        norm = pmf.sum(dim=-1).clamp_min(1e-12)
        return {
            "T_IB_A00": pmf,
            "D_OB": {
                "zero_probability": d_ob_zero / norm,
                "positive_quantiles_minutes": d_ob_quant / norm[:, None],
                "summary_kind": "CONDITIONAL_HEAD_SUMMARY",
                "quantile_kind": "CONDITIONAL_MIXTURE_NOT_MARGINAL",
            },
            "D_TX": {
                "zero_probability": d_tx_zero / norm,
                "positive_quantiles_minutes": d_tx_quant / norm[:, None],
                "summary_kind": "CONDITIONAL_HEAD_SUMMARY",
                "quantile_kind": "CONDITIONAL_AT_EXPECTED_D_OB_BIN_NOT_MARGINAL",
                "zero_kind": "MARGINAL_OVER_T_IB_HAZARD_GIVEN_EXPECTED_D_OB_BIN",
            },
        }


class M1Pipeline:
    """V2 principal pipeline (hazard + hurdle-quantile heads)."""

    def __init__(
        self,
        model,
        contracts,
        temperatures=None,
        normalization=None,
        static_context=None,
        calibration_contract=None,
        calibration_diagnostics=None,
        static_normalization=None,
        history_mode=None,
        tail_continuations=None,
    ):
        self.model = model
        self.contracts = contracts
        self.history_mode = HistoryEncoderMode(
            history_mode
            or getattr(
                model,
                "history_mode",
                HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
            )
        )
        self.static_context = static_context or M1StaticReferenceContext()
        # Temperature registry (Tranche 3): the hazard temperature applies to
        # hazard logits; D_OB_ZERO / D_TX_ZERO apply ONLY to the hurdle zero
        # logits.  Positive quantiles are never scaled by zero-mass
        # temperatures.  Legacy ``D_OB`` / ``D_TX`` keys are migrated to the
        # split registry below when only the old names are present.
        if temperatures is None:
            temperatures = {
                M1_TEMPERATURE_HAZARD: 1.0,
                M1_TEMPERATURE_D_OB_ZERO: 1.0,
                M1_TEMPERATURE_D_TX_ZERO: 1.0,
            }
        else:
            temperatures = dict(temperatures)
            if "D_OB" in temperatures and M1_TEMPERATURE_D_OB_ZERO not in temperatures:
                temperatures[M1_TEMPERATURE_D_OB_ZERO] = temperatures.pop("D_OB")
            if "D_TX" in temperatures and M1_TEMPERATURE_D_TX_ZERO not in temperatures:
                temperatures[M1_TEMPERATURE_D_TX_ZERO] = temperatures.pop("D_TX")
        self.temperatures = temperatures
        self.normalization = normalization
        self.static_normalization = static_normalization
        self.calibration_contract = calibration_contract or common_calibration_policy()
        self.calibration_diagnostics = dict(calibration_diagnostics or {})
        self.tail_continuations = dict(tail_continuations or {})

    @property
    def bins(self):
        """Legacy alias for consumers that only read the contract table."""
        return self.contracts

    @classmethod
    def smoke(
        cls,
        input_size=4,
        *,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    ):
        """Synthetic fixture helper; never resolves formal scientific bins.

        Smoke contracts carry the explicitly-labeled ``TEST_ONLY_LINEAR``
        upper-tail rule so synthetic sampling stays executable; this policy
        is forbidden in foundation scientific configs.
        """
        contracts = {
            M1_V2_HAZARD_COORDINATE_TARGET: HazardBinContract(
                bin_width_minutes=5, max_finite_minutes=60
            ),
            "D_OB": HurdleQuantileContract(
                target_name="D_OB",
                bin_width_minutes=5,
                max_finite_minutes=60,
                quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
                upper_tail_policy="TEST_ONLY_LINEAR",
            ),
            "D_TX": HurdleQuantileContract(
                target_name="D_TX",
                bin_width_minutes=5,
                max_finite_minutes=30,
                quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
                upper_tail_policy="TEST_ONLY_LINEAR",
            ),
        }
        torch.manual_seed(0)
        return cls(
            M1V2GRU(
                input_size,
                16,
                contracts[M1_V2_HAZARD_COORDINATE_TARGET],
                contracts["D_OB"],
                contracts["D_TX"],
                fast_input_size=input_size,
                history_mode=history_mode,
            ),
            contracts,
            history_mode=history_mode,
        )

    @classmethod
    def from_scientific_config(
        cls,
        scientific,
        *,
        input_size,
        normalization,
        hidden_size=None,
        static_input_size=0,
        static_normalization=None,
        history_mode=HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
    ):
        history_mode = HistoryEncoderMode(history_mode)
        if (
            not isinstance(normalization, M1NormalizationArtifact)
            or normalization.fitted_split != "train"
        ):
            raise ValueError("M1_FORMAL_TRAIN_NORMALIZATION_REQUIRED")
        width = scientific.parameters["m1_bin_width_minutes"].value
        ib_max = scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value
        d_ob_max = scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value
        d_tx_max = scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value
        quantile_levels = scientific.parameters["m1_v2_quantile_levels"].value
        if None in (ib_max, d_ob_max, d_tx_max) or not quantile_levels:
            raise ValueError("M1_V2_FINITE_SUPPORT_UNFROZEN")
        tail_param = scientific.parameters.get("m1_v2_positive_tail_policy")
        tail_policy = "UNRESOLVED" if tail_param is None else tail_param.value
        if tail_policy not in (
            "UNRESOLVED",
            "DECLARED_FROZEN",
            "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
        ):
            raise ValueError("M1_V2_PRINCIPAL_TAIL_POLICY_TEST_ONLY_FORBIDDEN")
        selected_parameter = scientific.parameters["m1_hidden_size"]
        if hidden_size is None and selected_parameter.freeze_state.value != "FROZEN":
            raise ValueError("M1_HIDDEN_SIZE_SELECTION_REQUIRED")
        hidden = selected_parameter.value if hidden_size is None else hidden_size
        if hidden is None:
            raise ValueError("M1_HIDDEN_SIZE_SELECTION_REQUIRED")
        allowed_hidden_sizes = {
            int(scientific.parameters["m1_hidden_size"].value),
            int(scientific.parameters["m1_sensitivity_hidden_size"].value),
        }
        if hidden not in allowed_hidden_sizes:
            raise ValueError("M1_HIDDEN_SIZE_NOT_IN_FROZEN_MODEL_SETTINGS")
        contracts = {
            M1_V2_HAZARD_COORDINATE_TARGET: HazardBinContract(
                bin_width_minutes=width, max_finite_minutes=ib_max
            ),
            "D_OB": HurdleQuantileContract(
                target_name="D_OB",
                bin_width_minutes=width,
                max_finite_minutes=d_ob_max,
                quantile_levels=tuple(quantile_levels),
                upper_tail_policy=tail_policy,
            ),
            "D_TX": HurdleQuantileContract(
                target_name="D_TX",
                bin_width_minutes=width,
                max_finite_minutes=d_tx_max,
                quantile_levels=tuple(quantile_levels),
                upper_tail_policy=tail_policy,
            ),
        }
        if static_input_size and not isinstance(
            static_normalization, M1StaticNormalizationArtifact
        ):
            raise ValueError("M1_FORMAL_STATIC_TRAIN_NORMALIZATION_REQUIRED")
        return cls(
            M1V2GRU(
                input_size,
                hidden,
                contracts[M1_V2_HAZARD_COORDINATE_TARGET],
                contracts["D_OB"],
                contracts["D_TX"],
                fast_input_size=input_size,
                static_input_size=static_input_size,
                history_mode=history_mode,
            ),
            contracts,
            normalization=normalization,
            static_normalization=static_normalization,
            history_mode=history_mode,
        )

    def _information_state(
        self, values, lengths, fast_features=None, static_features=None, pre_state=None
    ):
        """Shared ``h + r_fast (+ c_static)`` information state.

        Tranche 3 execution closure: production forecast
        (``predict_distributions`` / ``predict_from_pre``) and scenario
        generation (``sample_from_pre``) must consume the exact same
        information state.  When ``fast_features`` is not explicitly provided
        it is auto-derived from the sequence
        (``fast_features_from_sequence``) so production never silently falls
        back to a zero fast block.  Static features are derived from the PRE
        state when available (only PRE-published MODEL_FEATURE fields).
        """
        if fast_features is None:
            fast_features = fast_features_from_sequence(values, lengths)
        if (
            static_features is None
            and pre_state is not None
            and getattr(self.model, "static_input_size", 0)
        ):
            # Tranche 3 typed wiring: PRE writes plain per-field metadata
            # (``static_reference_publication``); M1 rebuilds its typed
            # ``M1StaticReferenceContext`` from it.  Only MODEL_FEATURE
            # fields with legal frozen-reference provenance enter ``c_static``.
            publication = getattr(pre_state, "static_reference_publication", None)
            context = (
                static_reference_context_from_pre(publication)
                if publication
                else self.static_context
            )
            if self.static_normalization is None:
                raise ValueError("M1_STATIC_NORMALIZATION_REQUIRED_FOR_PRE_INFERENCE")
            static_features, _ = static_reference_features_from_pre(
                pre_state, context, self.static_normalization
            )
        history = self.model.encode_history(values, lengths)
        state = self.model.state_representation(history, fast_features, static_features)
        return history, fast_features, static_features, state

    def predict_distributions(
        self, values, lengths, fast_features=None, static_features=None
    ):
        """Conditional head summary (V2 schema); alias of the module function.

        Returns clearly CONDITIONAL head summaries keyed by the public
        primitive names ``{T_IB_A00, D_OB, D_TX}``.  The ``T_IB_A00`` PMF is
        over the internal remaining-time coordinate
        (``T_IB_A00 = decision_time + coordinate``).  D_OB/D_TX zero
        probabilities are genuine marginals over the drawn hazard/bin
        structure; positive quantile rows are CONDITIONAL mixtures and are
        labeled as such (never ``marginal``).  Scenario-derived marginal
        summaries live in ``model.M1.summaries.scenario_marginal_summary``.

        Tranche 3 execution closure: when ``fast_features`` is None the
        production path auto-derives ``r_fast`` from the sequence (never a
        zero fast block unless the model has no fast encoder at all).
        """
        _, _, _, state = self._information_state(
            values, lengths, fast_features, static_features
        )
        return conditional_head_summary(
            self.model, state, self.contracts, temperatures=self.temperatures
        )

    def predict_from_pre(self, pre_state, values, lengths):
        """Production forecast over a PRE state (identical information state).

        Consumes the same ``h + r_fast + c_static`` as scenario generation:
        ``predict_now`` and ``sample_from_pre`` share the PRE-published static
        context through ``static_reference_features_from_pre``.
        """
        _, _, _, state = self._information_state(values, lengths, pre_state=pre_state)
        return conditional_head_summary(
            self.model, state, self.contracts, temperatures=self.temperatures
        )

    def sample_from_pre(
        self, pre_state, values, lengths, *, observed, count, seed, taxi_reference=None,
        tail_continuations=None,
    ):
        if not isinstance(self.model, M1V2GRU):
            raise ValueError("M1_V1_PRINCIPAL_DISABLED")
        if values.shape[0] != 1:
            raise ValueError(
                "formal scenario generation accepts one decision node at a time"
            )
        support = {}
        for item in pre_state.target_support:
            name = V1_TO_V2_SUPPORT.get(item.target_name, item.target_name)
            support[name] = (
                item.support_state.value
                if hasattr(item.support_state, "value")
                else str(item.support_state)
            )
        stage = pre_state.decision_node.operational_stage
        stage = stage.value if hasattr(stage, "value") else str(stage)
        decision_time_utc = pre_state.decision_node.decision_time.isoformat()
        self.model.eval()
        with torch.no_grad():
            history, fast_features, static_features, _ = self._information_state(
                values, lengths, fast_features=None, pre_state=pre_state
            )
        schedule = pre_state.successor_state.get("schedule_reference")
        schedule_value = None if schedule is None else schedule.value
        scheduled_ob_utc = None
        origin_airport_id = None
        if isinstance(schedule_value, dict):
            scheduled = schedule_value.get("scheduled_departure_utc")
            scheduled_ob_utc = None if scheduled is None else scheduled.isoformat()
            origin_airport_id = schedule_value.get("origin_airport_id")
        # r_fast is derived by ``_information_state`` above; production
        # forecast and scenario generation share the identical
        # ``h + r_fast`` information state (Tranche 3 closure).  Manuscript
        # static/reference context is fused only from PRE-published fields
        # (``static_reference_features_from_pre``); nothing is fabricated.
        reference_context = {
            "taxi_reference_id": None,
            "taxi_reference_hash": None,
            "taxi_reference_fallback_level": None,
            "taxi_reference_support_state": None,
        }
        published_taxi = pre_state.successor_state.get("taxi_reference")
        published_payload = (
            published_taxi.value
            if published_taxi is not None and isinstance(published_taxi.value, dict)
            else None
        )
        if published_payload is not None:
            reference_context = {
                "taxi_reference_id": published_payload.get("reference_id"),
                "taxi_reference_hash": published_payload.get("freeze_id"),
                "taxi_reference_fallback_level": published_payload.get(
                    "fallback_level"
                ),
                "taxi_reference_support_state": published_payload.get("support_state"),
            }
        if taxi_reference is not None:
            if (
                getattr(taxi_reference, "dataset_instance_id", None) != "data2_2019"
                or getattr(taxi_reference, "rule_id", None) != "DATA2_TAXI_REFERENCE"
            ):
                raise ValueError("M1_REQUIRES_TRAIN_FROZEN_DATA2_TAXI_REFERENCE")
            lookup = taxi_reference.lookup(origin_airport_id)
            state = getattr(lookup.support_state, "value", str(lookup.support_state))
            flags = set(getattr(lookup, "quality_flags", ()))
            fallback = next(
                (
                    flag.removeprefix("REFERENCE_LEVEL_")
                    for flag in flags
                    if flag.startswith("REFERENCE_LEVEL_")
                ),
                None,
            )
            supplied_context = {
                "taxi_reference_id": taxi_reference.reference_id,
                "taxi_reference_hash": getattr(
                    taxi_reference, "manifest_freeze_id", None
                ),
                "taxi_reference_fallback_level": fallback,
                "taxi_reference_support_state": state,
            }
            if published_payload is not None and (
                supplied_context["taxi_reference_id"]
                != published_payload.get("reference_id")
                or supplied_context["taxi_reference_hash"]
                != published_payload.get("freeze_id")
            ):
                raise ValueError("M1_TAXI_REFERENCE_LINEAGE_MISMATCH")
            reference_context = supplied_context
        return ancestral_sample_v2(
            self.model,
            history,
            self.contracts,
            episode_id=pre_state.decision_node.episode_id,
            decision_node_id=pre_state.decision_node.decision_node_id,
            stage=stage,
            observed=observed,
            count=count,
            seed=seed,
            target_support=support,
            decision_time_utc=decision_time_utc,
            scheduled_ob_utc=scheduled_ob_utc,
            temperatures=self.temperatures,
            fast_features=fast_features,
            static_features=static_features,
            **reference_context,
            tail_continuations=(
                self.tail_continuations
                if tail_continuations is None
                else dict(tail_continuations)
            ),
        )

    def calibration_policy(self):
        """Single scientific calibration policy shared with the FAST path."""
        return self.calibration_contract

    def summarize(self, scenarios, **kwargs):
        from .summaries import horizon_summaries

        return horizon_summaries(scenarios, **kwargs)

    def warning_probability(self, scenarios, **kwargs):
        from .warning import warning_probability

        return warning_probability(scenarios, **kwargs)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state": self.model.state_dict(),
                "input_size": self.model.input_size,
                "hidden_size": self.model.hidden_size,
                "fast_input_size": getattr(self.model, "fast_input_size", 0),
                "contracts": {
                    name: contract.model_dump()
                    for name, contract in self.contracts.items()
                },
                "contract_version": "M1_STATE_ESTIMATOR_V2_3",
                "temperatures": self.temperatures,
                "calibration_contract": self.calibration_contract.model_dump(
                    mode="json"
                ),
                "calibration_diagnostics": self.calibration_diagnostics,
                "static_input_size": getattr(self.model, "static_input_size", 0),
                "history_mode": self.history_mode.value,
                "static_context": self.static_context.model_dump(mode="json"),
                "normalization": (
                    None
                    if self.normalization is None
                    else self.normalization.model_dump(mode="json")
                ),
                "static_normalization": (
                    None
                    if self.static_normalization is None
                    else self.static_normalization.model_dump(mode="json")
                ),
            },
            path,
        )

    @classmethod
    def load(cls, path: Path):
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if "bins" in payload and "contracts" not in payload:
            # LEGACY_V1 frozen artifact: keep deserializable for provenance.
            bins = {
                name: TargetBinContract(**value)
                for name, value in payload["bins"].items()
            }
            model = OrderedEventGRU(payload["input_size"], payload["hidden_size"], bins)
            model.load_state_dict(payload["state"])
            pipeline = cls(model, bins, payload["temperatures"])
            pipeline._legacy_v1 = True
            return pipeline
        contracts = {
            name: (
                HazardBinContract(**value)
                if name == M1_V2_HAZARD_COORDINATE_TARGET
                else HurdleQuantileContract(**value)
            )
            for name, value in payload["contracts"].items()
        }
        fast_input_size = payload.get("fast_input_size", payload["input_size"])
        static_input_size = payload.get("static_input_size", 0)
        model = M1V2GRU(
            payload["input_size"],
            payload["hidden_size"],
            contracts[M1_V2_HAZARD_COORDINATE_TARGET],
            contracts["D_OB"],
            contracts["D_TX"],
            fast_input_size=fast_input_size,
            static_input_size=static_input_size,
            history_mode=payload.get(
                "history_mode",
                HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
            ),
        )
        model.load_state_dict(payload["state"])
        normalization = payload.get("normalization")
        if normalization is not None:
            normalization = M1NormalizationArtifact.model_validate(normalization)
        static_normalization = payload.get("static_normalization")
        if static_normalization is not None:
            static_normalization = M1StaticNormalizationArtifact.model_validate(
                static_normalization
            )
        static_context = payload.get("static_context")
        if static_context is not None:
            if (
                "schedule_reference_context" in static_context
                and "schedule_reference" not in static_context
            ):
                static_context = dict(static_context)
                static_context["schedule_reference"] = static_context.pop(
                    "schedule_reference_context"
                )
            static_context = M1StaticReferenceContext.model_validate(static_context)
        calibration_contract = M1CalibrationContract.model_validate(
            payload.get(
                "calibration_contract", common_calibration_policy().model_dump()
            )
        )
        return cls(
            model,
            contracts,
            payload["temperatures"],
            normalization,
            static_context=static_context,
            calibration_contract=calibration_contract,
            calibration_diagnostics=payload.get("calibration_diagnostics"),
            static_normalization=static_normalization,
            history_mode=payload.get(
                "history_mode",
                HistoryEncoderMode.FULL_ADAPTIVE_CAUSAL_PREFIX,
            ),
        )
