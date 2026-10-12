"""User-approved policy tracks; separate annual measurement and policy origins."""
from .e2_e3_exact import _headroom

MECHANISM_VERSION='JATM_THRESHOLD_BASELINE_HEADROOM_OB_ONLY_20261012'


def nominal_headroom(year):
    empirical=_headroom(year)
    return empirical.model_copy(update=dict(turnaround_lower_bound_q=41.,u_max=45.,floor_to_minutes=5.,
        source_id='RETROSPECTIVE_COMMON_POLICY_FROM_ORIGINAL_BENCHMARK_NOT_ANNUAL_TRAIN_FIT'))


def policy_tracks(year):
    return {'NOMINAL_COMMON':nominal_headroom(year),'YEAR_ADAPTIVE_SENSITIVITY':_headroom(year)}
