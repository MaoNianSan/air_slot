from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

ROOT=Path(r'D:\Local_Projects\airslot')
DATA=ROOT/'backfill_20261014'/'extracted'/'e3_six_year.json'
OUT=ROOT/'reports'/'section5_candidate_20261017_v2'/'figures'
OUT.mkdir(parents=True,exist_ok=True)
d=json.loads(DATA.read_text(encoding='utf-8'))
years=('2017','2018','2019','2020','2021','2022')
objectives=('BALANCED','FLIGHT','PASSENGER','RESOURCE')
labels=('Balanced','Flight','Passenger','Resource')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'axes.labelsize':8.2,
 'axes.titlesize':9.0,'xtick.labelsize':7.6,'ytick.labelsize':7.6,
 'pdf.fonttype':42,'ps.fonttype':42,'figure.dpi':300,'savefig.dpi':300,
 'savefig.bbox':'tight','axes.spines.top':False,'axes.spines.right':False})
agreement=np.array([[d[y]['profile_summary'][o]['exact_target_agreement_share'] for y in years] for o in objectives])
delta=np.empty((len(objectives),len(years)))
for i,o in enumerate(objectives):
 for j,y in enumerate(years):
  umax=d[y]['mechanism_summary']['headroom_u_max_values'][0]
  hj=d[y]['u_star_distribution'][f'{o}|HISTORY_JOINT']['mean']
  hm=d[y]['u_star_distribution'][f'{o}|HISTORY_MARGINAL_EXACT']['mean']
  delta[i,j]=100*(hj-hm)/umax
fig,axs=plt.subplots(1,2,figsize=(8.0,3.45),gridspec_kw={'wspace':.48})
left=axs[0].imshow(agreement,cmap='viridis',aspect='auto',vmin=.50,vmax=.80)
axs[0].grid(False); axs[0].set_title('(a) Exact target agreement')
axs[0].set_xticks(range(6),["'17","'18","'19","'20","'21","'22"])
axs[0].set_yticks(range(4),labels); axs[0].set_xlabel('Evaluation year')
for i in range(4):
 for j in range(6):
  value=agreement[i,j]; color='white' if (value-.50)/.30<.56 else '#111111'
  axs[0].text(j,i,f'{value:.2f}',ha='center',va='center',color=color,fontsize=8.2)
cb=fig.colorbar(left,ax=axs[0],fraction=.045,pad=.035); cb.set_label('Agreement share')
limit=6.5
right=axs[1].imshow(delta,cmap='RdBu_r',aspect='auto',norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit))
axs[1].grid(False); axs[1].set_title('(b) Mean target difference, HJ − HM')
axs[1].set_xticks(range(6),["'17","'18","'19","'20","'21","'22"])
axs[1].set_yticks(range(4),labels); axs[1].set_xlabel('Evaluation year')
for i in range(4):
 for j in range(6):
  value=delta[i,j]
  axs[1].text(j,i,f'{value:+.1f}',ha='center',va='center',
      color='white' if abs(value)>3.8 else '#111111',fontsize=8.2)
cb=fig.colorbar(right,ax=axs[1],fraction=.045,pad=.035); cb.set_label('Difference in mean u*/Umax (percentage points)')
cb.set_ticks([-6,-3,0,3,6])
fig.subplots_adjust(left=.12,right=.97,bottom=.17,top=.87)
fig.savefig(OUT/'figure_5_3_objectives_v2.pdf')
fig.savefig(OUT/'figure_5_3_objectives_v2.png',dpi=300)
plt.close(fig)
print(OUT/'figure_5_3_objectives_v2.pdf')
print(OUT/'figure_5_3_objectives_v2.png')
