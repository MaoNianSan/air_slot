from .contracts import NativeQuantity
from model.common.errors import ContractError

REQUIRED_CONTEXT=("turnaround_buffer_minutes","downstream_exposure","service_threshold_minutes","taxi_reference_minutes")

def native_quantities(scenario:dict,context:dict):
    missing_context=[name for name in REQUIRED_CONTEXT if context.get(name) is None]
    if missing_context:raise ContractError(f"M2_CONTEXT_PARAMETER_MISSING:{','.join(missing_context)}")
    rib_value=scenario.get("r_ib_minutes"); rob_value=scenario.get("r_ob_minutes"); taxi_value=scenario.get("t_tx_minutes")
    rib=None if rib_value is None else float(rib_value); rob=None if rob_value is None else float(rob_value); taxi=None if taxi_value is None else float(taxi_value)
    takeoff=None if rob is None or taxi is None else rob+taxi; buffer=float(context["turnaround_buffer_minutes"]); pax=context.get("passenger_exposure")
    def q(component,value,unit,driver,evidence="DERIVED",support="SUPPORTED",reason=None):
        return NativeQuantity(component=component,native_value=value,native_unit=unit,driver=driver,evidence_class=evidence,support=support,reason_code=reason)
    itinerary=context.get("itinerary_disruption_events")
    return (q("F_continuity",None if rib is None else max(0,rib-buffer),"minutes","turnaround_compression",
              "DERIVED" if rib is not None else "UNSUPPORTED","SUPPORTED" if rib is not None else "ABSTAIN",None if rib is not None else "R_IB_UNSUPPORTED"),
        q("F_execution",rob,"minutes","additional_off_block_wait","DERIVED" if rob is not None else "UNSUPPORTED","SUPPORTED" if rob is not None else "ABSTAIN",None if rob is not None else "R_OB_UNSUPPORTED"),
        q("F_propagation",None if takeoff is None else takeoff*float(context["downstream_exposure"]),"exposure_minutes","takeoff_delay_x_downstream_exposure","DERIVED" if takeoff is not None else "UNSUPPORTED","SUPPORTED" if takeoff is not None else "ABSTAIN",None if takeoff is not None else "TAKEOFF_DELAY_UNSUPPORTED"),
        q("P_time",None if pax is None or takeoff is None else float(pax)*takeoff,"passenger_minutes","passenger_exposure_x_delay","DOMAIN_PROXY" if pax is not None and takeoff is not None else "UNSUPPORTED","SUPPORTED" if pax is not None and takeoff is not None else "ABSTAIN",None if pax is not None and takeoff is not None else "PASSENGER_TIME_INPUT_UNSUPPORTED"),
        q("P_itinerary",None if itinerary is None else float(itinerary),"events","supported_itinerary_disruption_events","DERIVED" if itinerary is not None else "UNSUPPORTED","SUPPORTED" if itinerary is not None else "ABSTAIN",None if itinerary is not None else "NO_ITINERARY_DISRUPTION_QUANTITY"),
        q("P_service",None if takeoff is None else (1.0 if takeoff>=float(context["service_threshold_minutes"]) else 0.0),"threshold_events","delay_policy_threshold","SCENARIO_PARAMETER" if takeoff is not None else "UNSUPPORTED","SUPPORTED" if takeoff is not None else "ABSTAIN",None if takeoff is not None else "TAKEOFF_DELAY_UNSUPPORTED"),
        q("R_operating",None if taxi is None else max(0,taxi-float(context["taxi_reference_minutes"])),"excess_taxi_minutes","excess_taxi","DERIVED" if taxi is not None else "UNSUPPORTED","SUPPORTED" if taxi is not None else "ABSTAIN",None if taxi is not None else "T_TX_UNSUPPORTED"))
