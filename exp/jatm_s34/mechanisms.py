"""Approved threshold-by-headroom operators, shared scenario-wise integration."""
from model.M3.stage2 import action_grid
from model.M3.transition import apply_recovery
from model.M2.comparison_support import phi_c
from .e2_e3_exact import PROFILES
from .scientific_tracks import MECHANISM_VERSION


def curves(state,context,service,headroom,*,ledger=None):
    grid=action_grid(headroom.u_max,floor_to_minutes=headroom.floor_to_minutes)
    result={(threshold,coupling,profile):[[u,0.] for u in grid]
            for threshold in (False,True) for coupling in (False,True) for profile in PROFILES}
    responses={}
    for scenario in state.scenarios:
        base=service.consequence_scenario(scenario,node_id=state.node_id,support=scenario.support)
        for coupling in (False,True):
            for index,u in enumerate(grid):
                after=apply_recovery(scenario,context,u) if coupling else scenario.model_copy(update={
                    'd_ob_minutes':max(scenario.d_ob_minutes-u,0.),
                    'd_to_minutes':max(scenario.d_ob_minutes-u,0.)+scenario.d_tx_minutes})
                c=service.consequence_scenario(after,node_id=state.node_id,support=after.support)
                for threshold in (False,True):
                    native=dict(c.native_components)
                    if not threshold:
                        for k in ('P_itinerary','P_service'):native[k]=base.native_components[k]
                    cu=service.to_cu(native)
                    if ledger is not None:
                        key=(threshold,coupling,u)
                        if key not in responses:
                            responses[key]=dict(native={k:0. for k in native},native_change={k:0. for k in native},
                                                weight=0.,scenario_count=0)
                        response=responses[key]
                        response['weight']+=scenario.scenario_weight;response['scenario_count']+=1
                        for k,v in native.items():
                            response['native'][k]+=scenario.scenario_weight*v
                            response['native_change'][k]+=scenario.scenario_weight*(v-base.native_components[k])
                    for profile,view in PROFILES.items():
                        result[threshold,coupling,profile][index][1]+=scenario.scenario_weight*phi_c(cu,view=view)
    for table in result.values():
        for row in table:row[1]+=.25*row[0]/headroom.u_max if headroom.u_max else 0.
    if ledger is not None:
        for (threshold,coupling,u),response in responses.items():
            ledger(dict(representation=state.representation.representation_id,u=u,
                threshold_on=threshold,headroom_on=coupling,aggregation='EXACT_WEIGHTED_SCENARIO_SUM',**response))
    return result


def compare(node,context,service,headroom,*,ledger=None):
    joint=curves(node.state('HISTORY_JOINT'),context,service,headroom,ledger=ledger)
    marginal=curves(node.state('HISTORY_MARGINAL_EXACT'),context,service,headroom,ledger=ledger)
    rows=[]
    for key,table in joint.items():
        threshold,coupling,profile=key
        j=dict(table);m=dict(marginal[key]);uj=min(j,key=lambda u:(j[u],u));um=min(m,key=lambda u:(m[u],u))
        diff={u:m[u]-j[u] for u in j};relative=max((abs(diff[u]-diff[uj]) for u in j if u!=uj),default=0.)
        denom=j[0.]-j[uj]
        rows.append(dict(node_id=node.node_id,episode_id=node.episode_id,stage=node.stage.value,
            mechanism_version=MECHANISM_VERSION,threshold_on=threshold,headroom_on=coupling,profile=profile,
            joint_curve=table,marginal_curve=marginal[key],fixed_target_difference=diff,
            max_fixed_target_difference=max(map(abs,diff.values())),action_relative_difference=relative,
            u_joint=uj,u_marginal=um,choice_agreement=uj==um,reference_regret=j[um]-j[uj],
            normalized_reference_regret=None if denom<=0 else (j[um]-j[uj])/denom,
            null_interpretation='OBSERVED_ONLY_NO_FORCED_ZERO'))
    return rows
