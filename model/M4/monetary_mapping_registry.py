"""Materialize the M4 constructed-EUR monetary mapping registry (D1 frozen).

Decision 2026-08-24 D1: dual-layer, EUR-native monetary mapping.

- Ops-layer label is ``constructed_EUR`` (literature-native: the EUROCONTROL
  2004/2015 anchors are EUR-per-minute), not a currency conversion.
- The fixed paper claim statement is: "constructed scale anchored on
  EUROCONTROL EUR-basis values, not a currency conversion".
- D1b: EU261 ``tau_comp`` selected = 180 minutes (regulation 3h trigger);
  150/210 remain sensitivity values.

Numeric freeze is per-component: components with a verified anchor in the
retrieved literature carry values (F_continuity / F_execution / R_operating /
F_propagation = 72 EUR per CU-minute; P_time = 0.30 EUR per passenger-minute);
components without a per-CU anchor (P_itinerary / P_service) stay
HUMAN_DECISION_REQUIRED with an explicit reason (no zero-fill).
"""

from __future__ import annotations


from model.M4.monetary_mapping_plan import (
    ConversionOption,
    EU261Staircase,
    EU261Tier,
    MonetaryConversionPlan,
    MonetaryMappingPlanRegistry,
    NumericAnchorStatus,
    NumericFreezeStatus,
    OpsComponentRule,
    OpsCostBand,
    OPS_LAYER,
    PASSENGER_LAYER,
)


REFERENCES = (
    "EUROCONTROL (Cook, Tanner, Anderson) 2004: Evaluating the true cost to airlines of one minute of airborne or ground delay - final report, Transport Studies Group, University of Westminster (report; no DOI; local copies artifacts/diagnostics/cost_of_delay_2004_eurocontrol.pdf and artifacts/diagnostics/cost_of_delay_2004_text.txt)",
    "Cook, Tanner 2015: The cost of passenger delay to airlines in Europe - consultation document, EUROCONTROL (report; no DOI)",
    "Regulation (EC) No 261/2004, Articles 6-7 (regulatory fact; 250/400/600 EUR and 1500/3500 km thresholds verified against the regulation text before publication)",
    "CJEU C-402/07 Sturgeon v Condor (2011), Air & Space Law, DOI 10.54648/aila2011027 (3h trigger extension)",
)

EUROCONTROL_2004_MINUTE_ANCHOR = (
    "EUROCONTROL_2004_NETWORK_AVERAGE_72_EUR_PER_MINUTE",
    "72 Euros per minute network average for 'long' ATFM delays (over 15 minutes), "
    "weighted by aircraft types and the ATFM delay-minute distribution; includes "
    "reactionary delay costs; excludes strategic buffer minutes (EUROCONTROL 2004, "
    "results F.2, page 15)",
)

EUROCONTROL_2004_PASSENGER_MINUTE_ANCHOR = (
    "EUROCONTROL_2004_PASSENGER_DELAY_0_30_EUR_PER_PASSENGER_MINUTE",
    "EUR 0.30 per average passenger, per average delay minute, per average delayed "
    "flight, covering 'hard' compensation/rebooking costs and 'soft' future-revenue "
    "costs (EUROCONTROL 2004, summary item 6; carrier range 0.27-0.32 EUR per "
    "passenger per minute: Austrian vs Airline Z)",
)

OPS_MINUTE_BASE_EUR = 72.0
PASSENGER_MINUTE_BASE_EUR = 0.30

CLAIM_STATEMENT = (
    "constructed scale anchored on EUROCONTROL EUR-basis values, not a currency "
    "conversion; assumption-grounded, not empirical cost; no authoritative, "
    "optimal, or regret claim"
)


def _frozen_rule(
    component_id: str,
    base_per_cu_money: float,
    base_reference: tuple[str, ...],
    anchor_reason: str,
    *,
    layer: str = OPS_LAYER,
) -> OpsComponentRule:
    return OpsComponentRule(
        component_id=component_id,
        layer=layer,
        base_per_cu_money=base_per_cu_money,
        base_reference=base_reference,
        anchor_status=NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED,
        anchor_reason=anchor_reason,
        bands=(
            OpsCostBand(
                band_id="LOW", scale_factor=0.5,
                per_cu_money=round(base_per_cu_money * 0.5, 6),
            ),
            OpsCostBand(
                band_id="BASE", scale_factor=1.0,
                per_cu_money=base_per_cu_money,
            ),
            OpsCostBand(
                band_id="HIGH", scale_factor=2.0,
                per_cu_money=round(base_per_cu_money * 2.0, 6),
            ),
        ),
    )


def _pending_rule(component_id: str, layer: str, anchor_reason: str) -> OpsComponentRule:
    return OpsComponentRule(
        component_id=component_id,
        layer=layer,
        base_per_cu_money=None,
        base_reference=REFERENCES[:1],
        anchor_status=NumericAnchorStatus.HUMAN_DECISION_REQUIRED,
        anchor_reason=anchor_reason,
        bands=(
            OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=None),
            OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=None),
            OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=None),
        ),
    )


def build_plan() -> MonetaryMappingPlanRegistry:
    raise RuntimeError("M4_LEGACY_EUR_MAPPING_SUPERSEDED_USE_ACTIVE_RMB_REGISTRY")


def _build_superseded_plan_provenance_only() -> MonetaryMappingPlanRegistry:
    """Historical builder body retained for provenance inspection only."""
    eu261 = EU261Staircase(
        trigger_minutes=180,
        tau_comp_options_minutes=(150, 180, 210),
        tau_comp_selected_minutes=180,
        tau_comp_sensitivity_minutes=(150, 210),
        tiers=(
            EU261Tier(max_distance_km=1500, compensation_eur=250),
            EU261Tier(max_distance_km=3500, compensation_eur=400),
            EU261Tier(max_distance_km=None, compensation_eur=600),
        ),
        regulatory_reference=REFERENCES[2:4],
    )
    conversion = MonetaryConversionPlan(
        status="FROZEN",
        issue=(
            "Dual EUR-native layers: ops layer is constructed_EUR anchored on the "
            "EUROCONTROL EUR-per-minute literature; compensation layer is the EU261 "
            "EUR regulatory staircase; no cross-currency conversion is required "
            "because both layers are EUR"
        ),
        options=(
            ConversionOption(
                option_id="OPTION_A_DUAL_LAYER",
                description=(
                    "Report both layers in their own EUR units (constructed_EUR ops "
                    "+ EU261 EUR compensation) and keep J_post as a two-part "
                    "expression without any cross-currency conversion"
                ),
                assumptions=(
                    "no exchange-rate assumption",
                    "no purchasing-power assumption",
                    "each layer carries its own constructed/regulatory label",
                ),
                recommended=True,
            ),
            ConversionOption(
                option_id="OPTION_B_FIXED_RATE",
                description=(
                    "Convert one layer into the other with a reference rate before "
                    "summing J_post"
                ),
                assumptions=(
                    "requires user-specified reference rate and period",
                    "introduces an extra assumption not grounded in the cited literature",
                ),
                recommended=False,
            ),
            ConversionOption(
                option_id="OPTION_C_WELFARE_WEIGHTED",
                description=(
                    "Reweight compensation amounts via welfare coefficients into the "
                    "ops-layer scale"
                ),
                assumptions=(
                    "requires welfare-transfer estimates",
                    "heavier assumption load; not recommended for the paper",
                ),
                recommended=False,
            ),
        ),
    )
    return MonetaryMappingPlanRegistry(
        numeric_freeze_status=NumericFreezeStatus.FROZEN_ASSUMPTION_GROUNDED,
        monetary_ground_truth_claim=False,
        claim_statement=CLAIM_STATEMENT,
        ops_components=(
            _frozen_rule(
                "F_continuity",
                OPS_MINUTE_BASE_EUR,
                EUROCONTROL_2004_MINUTE_ANCHOR,
                "CU unit = minutes; EUROCONTROL 2004 network average 72 EUR/min applies directly",
            ),
            _frozen_rule(
                "F_execution",
                OPS_MINUTE_BASE_EUR,
                EUROCONTROL_2004_MINUTE_ANCHOR,
                "CU unit = minutes (R_OB = max(0, DELTA_OB)); 72 EUR/min applies directly",
            ),
            _frozen_rule(
                "F_propagation",
                OPS_MINUTE_BASE_EUR,
                EUROCONTROL_2004_MINUTE_ANCHOR,
                "CU unit = exposure_minutes = delay_minutes x expected_downstream_exposure(origin); "
                "each exposure-minute is one expected downstream airline delay minute costed at the "
                "same EUROCONTROL 2004 network-average 72 EUR/min (mathematical assumption: "
                "unit-consistent linear anchor; no separate literature value)",
            ),
            _frozen_rule(
                "P_time",
                PASSENGER_MINUTE_BASE_EUR,
                EUROCONTROL_2004_PASSENGER_MINUTE_ANCHOR,
                "CU unit = passenger_minutes; EUROCONTROL 2004 estimate 0.30 EUR per passenger "
                "per delay minute applies directly",
                layer=PASSENGER_LAYER,
            ),
            _pending_rule(
                "P_itinerary",
                PASSENGER_LAYER,
                "CU unit = events (N_miss = n_pax x 1[D_TO >= tau_itinerary]); retrieved EUROCONTROL "
                "2004 text (sec. 2.3.2.3.7) documents missed-connection costs only qualitatively "
                "(compensation, rebooking, accommodation; no per-passenger numeric value); per-event "
                "anchor requires a literature value (e.g. AGIFORS missed-connection cost study) or a "
                "user-authorized assumption",
            ),
            _pending_rule(
                "P_service",
                PASSENGER_LAYER,
                "CU unit = events (N_svc = n_pax x 1[D_TO >= tau_service]); no per-event cost anchor "
                "in the retrieved literature (EUROCONTROL 2004/2015); per-event anchor requires a "
                "literature value or a user-authorized assumption",
            ),
            _frozen_rule(
                "R_operating",
                OPS_MINUTE_BASE_EUR,
                EUROCONTROL_2004_MINUTE_ANCHOR,
                "CU unit = excess taxi minutes; 72 EUR/min applies directly",
            ),
        ),
        eu261=eu261,
        conversion_plan=conversion,
        references=REFERENCES,
    )

