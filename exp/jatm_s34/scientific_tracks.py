"""User-approved policy tracks; separate annual measurement and policy origins."""
from model.common.decision_contracts import HeadroomSummary
from .e2_e3_exact import _headroom

MECHANISM_VERSION='JATM_THRESHOLD_BASELINE_HEADROOM_OB_ONLY_20261012'
NOMINAL_SOURCE='RETROSPECTIVE_COMMON_POLICY_FROM_ORIGINAL_BENCHMARK_NOT_ANNUAL_TRAIN_FIT'


def nominal_headroom(year):
    if year not in range(2017,2023):raise ValueError('NOMINAL_POLICY_YEAR_INVALID')
    # HeadroomSummary requires quantile/count fields for compatibility with M3.
    # They are policy provenance labels here, never annual fitted statistics.
    return HeadroomSummary(turnaround_lower_bound_q=41.,u_max=45.,floor_to_minutes=5.,
        turnaround_quantile=.20,headroom_quantile=.90,headroom_positive_n=0,
        source_id=NOMINAL_SOURCE)


def nominal_policy_metadata():
    return dict(track='NOMINAL_COMMON',source_id=NOMINAL_SOURCE,
        fit_status='NOT_ANNUAL_TRAIN_ESTIMATE',turnaround_lower_bound_minutes=41.,
        u_max_minutes=45.,lambda_policy=.25,action_grid_minutes=list(range(0,46,5)),
        compatibility_fields=dict(turnaround_quantile='BENCHMARK_LABEL_NOT_ANNUAL_FIT',
            headroom_quantile='BENCHMARK_LABEL_NOT_ANNUAL_FIT',
            headroom_positive_n='NOT_APPLICABLE_REPRESENTED_AS_ZERO'))


def policy_tracks(year):
    return {'NOMINAL_COMMON':nominal_headroom(year),'YEAR_ADAPTIVE_SENSITIVITY':_headroom(year)}
