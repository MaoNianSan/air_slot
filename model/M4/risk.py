def weighted_mean(values,weights):return sum(v*w for v,w in zip(values,weights))/sum(weights)

def weighted_var_cvar(values,weights,alpha):
    pairs=sorted(zip(values,weights));total=sum(weights);threshold=alpha*total;cumulative=0;var=pairs[-1][0]
    for value,weight in pairs:
        cumulative+=weight
        if cumulative>=threshold:var=value;break
    tail_mass=(1-alpha)*total
    if tail_mass<=0:return var,var
    remaining=tail_mass;total_tail=0
    for value,weight in reversed(pairs):
        take=min(weight,remaining);total_tail+=value*take;remaining-=take
        if remaining<=1e-12:break
    return var,total_tail/tail_mass
