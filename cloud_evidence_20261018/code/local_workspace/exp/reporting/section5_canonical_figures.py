from __future__ import annotations
import csv, hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from section5_figure_style import boundary, recoverability, information

ROOT=Path(__file__).resolve().parents[2]
SRC=Path(r'D:\research\air_slot\code\explore')
EPOCH=SRC/'artifacts/experiment/final_test_v2_stage_matched_canonical_v2'
CP=EPOCH/'checkpoints'; QDIR=SRC/'artifacts/paper_results_v2_final_test_rmb/stage_q_sensitivity'
OUT=ROOT/'artifacts/paper_figures'; FIG=ROOT/'figures'; SCRIPT=Path(__file__).resolve()
for d in [FIG,OUT/'figure3_stage1',OUT/'figure4_stage2',OUT/'figure5_representation']: d.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Serif','font.size':8.5,'axes.labelsize':8.5,'xtick.labelsize':7.5,'ytick.labelsize':7.5,'legend.fontsize':7.5,'pdf.fonttype':42,'ps.fonttype':42})
BLUE='#0072B2'; ORANGE='#D55E00'; GREY='#777777'; LIGHT='#D9D9D9'; PURPLE='#7B2CBF'; GREEN='#009E73'

def payload(fn): return json.loads((CP/fn).read_text(encoding='utf-8'))['payload']
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def head():
 try:return subprocess.check_output(['git','-C',str(SRC),'rev-parse','HEAD'],text=True).strip()
 except Exception:return 'UNKNOWN'
def write_rows(path,rows):
 fields=sorted({k for r in rows for k in r})
 with path.open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
def manifest(folder,fig_id,inputs,panels,cohort,validation):
 d={'figure_id':fig_id,'creation_timestamp':datetime.now(timezone.utc).isoformat(),'design_skill':'figure-designer','style_module_path':str(SCRIPT.with_name('section5_figure_style.py')),'style_module_sha256':sha(SCRIPT.with_name('section5_figure_style.py')),'plotting_script_sha256':sha(SCRIPT),'git_head':head(),'plotting_script_path':str(SCRIPT),'authority_lineage':'artifacts/experiment/final_test_v2_stage_matched_canonical_v2','reference_representation':'HISTORY_JOINT','cohort_identity':cohort,'input_artifacts':[{'path':str(p),'sha256':sha(p)} for p in inputs],'panels':panels,'model_retrained':False,'recalibration_performed':False,'parameter_reselected':False,'raw_final_test_data_read':False,'new_final_test_access_opened':False,'scientific_definition_changed':False,'legacy_1656_node_input_used':False,'validation':validation,'output_artifacts':[{'path':str(p),'sha256':sha(p)} for p in [folder/f'{fig_id}_DATA.csv',folder/f'{fig_id}.pdf']], 'node_counts':{'PRE':29,'TURN':127} if fig_id=='FIGURE3' else {'reference_recovery_cohort':16}, 'cohort_id':cohort.get('cohort_id','canonical_v2_stage2_reference') if isinstance(cohort,dict) else str(cohort)}
 (folder/f'{fig_id}_MANIFEST.json').write_text(json.dumps(d,indent=2),encoding='utf-8')

att=payload('ATTENTION_DECISIONS.json'); rec=payload('RECOVERY_DECISIONS.json'); cohort=payload('REFERENCE_RECOVERY_COHORT.json')
att_rows=[r for r in att['rows'] if r['variant']=='HISTORY_JOINT' and abs(float(r['q'])-.10)<1e-12]
by_stage={r['stage']:r for r in att_rows}; stage_label={'PRE_IB':'PRE','POST_IB_PRE_OB':'TURN'}
# Figure 3: rank boundary maps
qfig=pd.read_csv(QDIR/'STAGE_Q_SCREENING_FIGURE_DATA.csv'); latt={str(x.stage_class):float(x.attention_loss) for _,x in qfig[qfig.q==.1].iterrows()}
f3rows=[]; stage_info={}
for st,r in by_stage.items():
 C={x['node_id']:x for x in r['consequence_decision']['entries']}; D={x['node_id']:x for x in r['delay_decision']['entries']}
 K=int(r['k']); N=int(r['eligible_candidate_count']); cs=set(r['consequence_decision']['selected_node_ids']); ds=set(r['delay_decision']['selected_node_ids'])
 stage_info[st]={'N':N,'K':K,'C':cs,'D':ds,'Centries':C,'Dentries':D}
 mis=sorted(cs-ds,key=lambda n:C[n]['rank']); add=sorted(ds-cs,key=lambda n:D[n]['rank'])
 rank_max=max(2*K,max([C[n]['rank'] for n in mis+add]+[D[n]['rank'] for n in mis+add]+[0])+2)
 stage_info[st]['rank_max']=rank_max
 labels={n:f'M{i+1}' for i,n in enumerate(mis)}; labels.update({n:f'A{i+1}' for i,n in enumerate(add)})
 for n,x in C.items():
  cat='both' if n in cs&ds else ('missed' if n in cs else ('added' if n in ds else 'neither'))
  f3rows.append({'stage':stage_label[st],'stage_code':st,'node_id':n,'episode_id':x['episode_id'],'consequence_rank':x['rank'],'delay_rank':D[n]['rank'],'category':cat,'case_label':labels.get(n,''),'N':N,'K':K,'L_att':latt.get(stage_label[st],0.0)})
for st,meta in stage_info.items():
 reference=sum(meta['Centries'][n]['score'] for n in meta['C'])
 retained=sum(meta['Centries'][n]['score'] for n in meta['D'])
 expected=1-retained/reference
 assert abs(expected-latt[stage_label[st]])<1e-10, 'BLOCKED_STAGE1_LOSS_MISMATCH'
 assert meta['K']==int(np.ceil(.10*meta['N']))
f3path=OUT/'figure3_stage1/FIGURE3_DATA.csv'; write_rows(f3path,f3rows)
boundary(f3rows,stage_info,FIG,OUT/'figure3_stage1')
manifest(OUT/'figure3_stage1','FIGURE3',[CP/'ATTENTION_DECISIONS.json',QDIR/'STAGE_Q_SCREENING_FIGURE_DATA.csv'],{'3a':'PRE','3b':'TURN'}, {'stage1':'canonical_v2 eligible candidates; q=0.10'}, {'boundary_window':{stage_label[k]:v['rank_max'] for k,v in stage_info.items()},'nominal_q_reconciled':True,'changed_selection_labels':'M=missed by delay; A=added by delay'})

# Figure 4: recoverability landscape + exactly three deterministic profiles
cohort_ids=set(cohort['stage2_actionable_node_ids_flattened']); ref_rank={}
for r in att_rows:
 for x in r['consequence_decision']['entries']: ref_rank[x['node_id']]={'stage':r['stage'],'rank':x['rank'],'N':r['eligible_candidate_count'],'pc':x['score']}
recs=[r['decision'] for r in rec['rows'] if r['variant']=='HISTORY_JOINT' and r['node_id'] in cohort_ids]
if set(x['node_id'] for x in recs)!=cohort_ids: raise RuntimeError('BLOCKED_STAGE2_COHORT_DRIFT')
case=[]
for x in recs:
 rr=ref_rank[x['node_id']]; case.append({'node_id':x['node_id'],'episode_id':x['episode_id'],'stage':stage_label[rr['stage']],'stage_code':rr['stage'],'V':float(x['recoverable_value']),'u_star':float(x['u_star']),'j_zero':float(x['j_zero']),'j_star':float(x['j_star']),'pc_rank':int(rr['rank'])})
case.sort(key=lambda z:(-z['V'],z['stage'],z['node_id']))
for i,x in enumerate(case,1): x['case_label']=f'Case {i}'
positive=[x for x in case if x['V']>0]; zero=[x for x in case if x['u_star']==0]
high=case[0]; typical=min(positive,key=lambda x:(abs(x['V']-np.median([z['V'] for z in positive])),x['case_label'])) if positive else None
zero_case=max(zero,key=lambda x:(-x['pc_rank'],x['V'])) if zero else None
selected=[]
for x in [high,typical,zero_case]:
 if x and x['node_id'] not in [z['node_id'] for z in selected]: selected.append(x)
# fill deterministic distinct if collision
for x in case:
 if len(selected)>=3: break
 if x['node_id'] not in [z['node_id'] for z in selected]: selected.append(x)
objmap=rec['reference_objectives']; f4rows=[]
for x in case:
 f4rows.append({'panel':'4a',**{k:x[k] for k in ['case_label','node_id','episode_id','stage','V','u_star','j_zero','j_star','pc_rank']}})
 for u,j in objmap[x['node_id']]['objective_by_action']: f4rows.append({'panel':'4b','case_label':x['case_label'],'node_id':x['node_id'],'episode_id':x['episode_id'],'stage':x['stage'],'u':float(u),'J':float(j),'J_minus_Jstar':float(j-x['j_star']),'u_star':x['u_star']})
f4path=OUT/'figure4_stage2/FIGURE4_DATA.csv'; write_rows(f4path,f4rows)
recoverability(case,selected,objmap,FIG,OUT/'figure4_stage2')
manifest(OUT/'figure4_stage2','FIGURE4',[CP/'ATTENTION_DECISIONS.json',CP/'RECOVERY_DECISIONS.json',CP/'REFERENCE_RECOVERY_COHORT.json'],{'4a':'16-case recoverability landscape','4b':[x['case_label'] for x in selected]}, {'stage2':'fixed HISTORY_JOINT Stage-II cohort'}, {'stage2_cohort_size':len(case),'zero_action_count':len(zero),'profiles_selected':[x['case_label'] for x in selected],'recoverable_value_identity':all(abs(x['V']-(x['j_zero']-x['j_star']))<1e-10 for x in case)})

# Figure 5: shared-row information-ablation matrix
proj=json.loads((EPOCH/'PAPER_FACING_SECTION5_RESULTS.json').read_text(encoding='utf-8'))['section_5_3_information_value']['comparators']; order=['CURRENT_JOINT','HISTORY_POINT','HISTORY_MARGINAL']; labels={'CURRENT_JOINT':'History removed','HISTORY_POINT':'Point estimate only','HISTORY_MARGINAL':'Joint dependence removed'}; s5=[]
for x in proj:
 if x['comparator_id'] not in order: continue
 a=x['stage1_attention']; r=x['stage2_recovery']; s5.append({'comparator':x['comparator_id'],'row_label':labels[x['comparator_id']],'L_att':a['L_att'],'L_att_lo':a['ci_95'][0],'L_att_hi':a['ci_95'][1],'L_rec':r['L_rec'],'L_rec_lo':r['ci_95'][0],'L_rec_hi':r['ci_95'][1],'A0':r['exact_agreement_share'],'A5':r['within_5min_agreement_share'],'A0_count':r['exact_agreement_count'],'A5_count':r['within_5min_agreement_count'],'R_star':16})
s5.sort(key=lambda z:order.index(z['comparator'])); rowlabs=[z['row_label'] for z in s5]; f5path=OUT/'figure5_representation/FIGURE5_DATA.csv'; write_rows(f5path,s5)
information(s5,FIG,OUT/'figure5_representation')
manifest(OUT/'figure5_representation','FIGURE5',[EPOCH/'PAPER_FACING_SECTION5_RESULTS.json',CP/'BOOTSTRAP.json',CP/'M4_COMPARISONS.json'],{'rows':rowlabs,'columns':['Stage-I screening loss','Stage-II recovery loss','Recovery-target agreement']},{'reference':'HISTORY_JOINT','comparators':order,'cohort':'fixed 16-case recovery cohort'},{'comparator_order':order,'no_L_total':True,'values_match_projection':True,'ci_source':'paired 95% bootstrap'})
print(json.dumps({'git_head':head(),'figures':[str(FIG/f'figure{i}.pdf') for i in (3,4,5)],'data':[str(f3path),str(f4path),str(f5path)],'counts':{'PRE':stage_info['PRE_IB']['N'],'TURN':stage_info['POST_IB_PRE_OB']['N'],'stage2':len(case)}}))


