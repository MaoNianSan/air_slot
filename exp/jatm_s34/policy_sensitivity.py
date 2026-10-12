"""Prespecified one-factor Stage-II sensitivity on the E3 paired cohort.

Only the M3 exact objective evaluator computes new action outcomes. Nominal
curves supply the already-computed native consequence values for unchanged
actions; changing the effort coefficient then uses the published linear term.
"""
from types import SimpleNamespace
from model.M3.stage2 import action_grid, expected_objective, objective_by_grid, RecoveryPolicy
from exp.jatm_section5.recovery_value import transition_context

from .e2_e3_exact import PROFILES


NOMINAL_TURNAROUND = 41.
NOMINAL_U_MAX = 45.
NOMINAL_LAMBDA = .25
POLICY_SENSITIVITY_VERSION = 'JATM_ONE_FACTOR_POLICY_AND_FIXED_SLOPE_V1'
REPRESENTATIONS = ('HISTORY_JOINT', 'HISTORY_MARGINAL_EXACT')


def policy_settings():
    """Main, prespecified one-factor, and explicit range/slope separation."""
    settings = [dict(policy_id='NOMINAL',variation='MAIN',turnaround=41.,u_max=45.,lambda_policy=.25)]
    settings.extend(dict(policy_id=f'LAMBDA_{value:.2f}',variation='EFFORT_ONE_FACTOR',
                         turnaround=41.,u_max=45.,lambda_policy=value)
                    for value in (.10,.50,1.00))
    settings.extend(dict(policy_id=f'TURNAROUND_{int(value)}',variation='HEADROOM_ONE_FACTOR',
                         turnaround=value,u_max=45.,lambda_policy=.25)
                    for value in (34.,47.))
    for u_max in (25.,75.):
        settings.append(dict(policy_id=f'UMAX_{int(u_max)}_COUPLED',
                             variation='RANGE_AND_EFFORT_SLOPE',turnaround=41.,
                             u_max=u_max,lambda_policy=.25))
        settings.append(dict(policy_id=f'UMAX_{int(u_max)}_FIXED_SLOPE',
                             variation='RANGE_ONLY_FIXED_NOMINAL_EFFORT_SLOPE',
                             turnaround=41.,u_max=u_max,
                             lambda_policy=.25*u_max/45.))
    return tuple(settings)


def _native_curves(node, service, nominal_curves):
    """Cache exact native expected values once per (representation, view, bound)."""
    basis={}
    for profile,view in PROFILES.items():
        for rep in REPRESENTATIONS:
            nominal=dict(nominal_curves[profile][rep])
            if tuple(sorted(nominal))!=action_grid(NOMINAL_U_MAX):
                raise ValueError('POLICY_SENSITIVITY_NOMINAL_GRID_MISMATCH')
            standard={u:value-NOMINAL_LAMBDA*u/NOMINAL_U_MAX
                      for u,value in nominal.items()}
            basis[profile,rep,41.]=standard
            extended=dict(standard)
            state=node.state(rep)
            context=transition_context(node,SimpleNamespace(turnaround_lower_bound_q=41.))
            for u in action_grid(75.):
                if u<=45.:continue
                value=expected_objective(state,context=context,service=service,u=u,
                    u_max=75.,lambda_policy=NOMINAL_LAMBDA,view=view)
                extended[u]=value-NOMINAL_LAMBDA*u/75.
            basis[profile,rep,'41_EXTENDED']=extended
            for turnaround in (34.,47.):
                altered=transition_context(node,SimpleNamespace(turnaround_lower_bound_q=turnaround))
                table=objective_by_grid(state,context=altered,service=service,u_max=45.,
                    policy=RecoveryPolicy(lambda_policy=NOMINAL_LAMBDA,aggregation_view=view))
                basis[profile,rep,turnaround]={u:value-NOMINAL_LAMBDA*u/45.
                                               for u,value in table}
    return basis


def evaluate_policy_sensitivity(node, service, nominal_curves, *, cu_track):
    """Exact HJ/HM decisions under independent, non-Cartesian policy tracks."""
    if cu_track not in ('YEAR_LOCAL','FIXED_COMMON'):
        raise ValueError('POLICY_SENSITIVITY_CU_TRACK_INVALID')
    basis=_native_curves(node,service,nominal_curves)
    output=[]
    for setting in policy_settings():
        grid=action_grid(setting['u_max'])
        for profile in PROFILES:
            curves={}
            for rep in REPRESENTATIONS:
                key='41_EXTENDED' if setting['turnaround']==41. and setting['u_max']==75. else setting['turnaround']
                native=basis[profile,rep,key]
                curves[rep]=(nominal_curves[profile][rep] if setting['policy_id']=='NOMINAL' else
                    [[u,native[u]+setting['lambda_policy']*u/setting['u_max']] for u in grid])
            joint=dict(curves['HISTORY_JOINT']);marginal=dict(curves['HISTORY_MARGINAL_EXACT'])
            u_joint=min(joint,key=lambda u:(joint[u],u))
            u_marginal=min(marginal,key=lambda u:(marginal[u],u))
            reference_v=joint[0.]-joint[u_joint]
            regret=joint[u_marginal]-joint[u_joint]
            output.append(dict(node_id=node.node_id,episode_id=node.episode_id,
                stage=node.stage.value,profile=profile,cu_track=cu_track,
                policy_version=POLICY_SENSITIVITY_VERSION,**setting,
                joint_curve=curves['HISTORY_JOINT'],
                marginal_curve=curves['HISTORY_MARGINAL_EXACT'],
                e_joint_minus_marginal={u:joint[u]-marginal[u] for u in grid},
                u_joint=u_joint,u_marginal=u_marginal,
                activation_joint=u_joint>0,activation_marginal=u_marginal>0,
                target_agreement=u_joint==u_marginal,
                reference_recoverable_value=reference_v,
                joint_reference_loss_at_marginal_action=regret,
                normalized_reference_loss=None if reference_v<=0 else regret/reference_v,
                numerical_reference='MODEL_M3_EXACT_ENUMERATION_WITH_LINEAR_EFFORT_REWEIGHT'))
    return output
