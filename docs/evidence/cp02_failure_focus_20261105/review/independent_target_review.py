import csv, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_failure_focus_20261105/Cloud-BAL')
target=root/'docs/evidence/cp02_failure_focus_20261105/targets'
source=root/'docs/evidence/cp02_grouped_forecast_20261105/analysis'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def read(name):
 with (target/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def require(ok,msg):
 if not ok: raise AssertionError(msg)
receipt=json.loads((target/'bundle_receipt.json').read_text())
require(receipt['status']=='COMPLETE' and receipt['analysis_plan_sha256']==sha(root/'docs/evidence/cp02_failure_focus_20261105/analysis_plan.json'),'plan binding')
require(receipt['source_receipt_sha256']==sha(source/'receipt.json'),'source receipt binding')
for name,rec in receipt['outputs'].items():
 p=root/rec['path']; require(p.is_file() and not p.is_symlink() and p.stat().st_size==rec['size_bytes'] and sha(p)==rec['sha256'],f'output pin {name}')
arr={}
for h in range(13,19):
 p=source/f'hour_{h}_arrays.npz'
 source_files=json.loads((target/'source_receipt.json').read_text())['files']; source_by_name={Path(x['path']).name:x for x in source_files}; require(sha(p)==source_by_name[p.name]['sha256'],f'source npz {h}')
 with np.load(p,allow_pickle=False) as z: arr[h-12]={k:np.array(z[k],copy=True) for k in ('reference','A','C','ORIGINAL','flat_index_yx','latitude','longitude')}
 require(arr[h-12]['reference'].shape==(3688,),f'array count {h}')
ids_by_hour={lead:{int(k):i for i,k in enumerate(a['flat_index_yx'])} for lead,a in arr.items()}
labels={
'h02_original_A_weak_hit_loss':(2,.1,'ORIGINAL','A','lost_hit','[0.1,1)'),
'h02_original_A_weak_hit_gain':(2,.1,'ORIGINAL','A','gained_hit','[0.1,1)'),
'h02_original_A_new_FA':(2,.1,'ORIGINAL','A','new_false_alarm','[0,0.1)'),
'h02_original_A_resolved_FA':(2,.1,'ORIGINAL','A','removed_false_alarm','[0,0.1)'),
'h05_A_C_5mm_new_FA':(5,5.,'A','C','new_false_alarm',None),
'h05_A_C_5mm_new_FA_dry':(5,5.,'A','C','new_false_alarm','[0,0.1)'),
'h05_A_C_5mm_new_FA_weak':(5,5.,'A','C','new_false_alarm','[0.1,1)'),
'h05_A_C_5mm_new_FA_1to5':(5,5.,'A','C','new_false_alarm','[1,5)'),
'h05_A_C_5mm_resolved_FA':(5,5.,'A','C','removed_false_alarm','[0,0.1)'),
'h05_A_C_5mm_hit_loss':(5,5.,'A','C','lost_hit','[5,infinity)'),
'h05_A_C_weak_hit_loss':(5,.1,'A','C','lost_hit','[0.1,1)'),
'h05_A_C_weak_hit_gain':(5,.1,'A','C','gained_hit','[0.1,1)'),
'h06_A_C_weak_hit_loss':(6,.1,'A','C','lost_hit','[0.1,1)'),
'h06_A_C_weak_hit_gain':(6,.1,'A','C','gained_hit','[0.1,1)'),}
def band(v):return '[0,0.1)' if v<.1 else '[0.1,1)' if v<1 else '[1,5)' if v<5 else '[5,infinity)'
def mask_event(a,lead,t,oldcase,newcase,event,bandname):
 ref=a['reference']; old=a[oldcase]>=t; new=a[newcase]>=t; obs=ref>=t
 m={'lost_hit':obs&old&~new,'gained_hit':obs&~old&new,'new_false_alarm':~obs&~old&new,'removed_false_alarm':~obs&old&~new}[event]
 if bandname is not None:m &= np.array([band(v)==bandname for v in ref])
 return set(map(int,a['flat_index_yx'][m]))
events=read('event_membership.csv')
by_group=defaultdict(list)
for row in events:by_group[row['cohort_label']].append(row)
expected_counts={}
for g,spec in labels.items():
 lead,t,old,new,event,b=spec
 expected=mask_event(arr[lead],lead,t,old,new,event,b)
 observed={int(r['flat_index_yx']) for r in by_group[g]}
 require(expected==observed,f'{g}: independent membership set mismatch; expected {len(expected)}, output {len(observed)}')
 expected_counts[g]=len(expected)
# Baseline candidate recovers the three ORIGINAL-to-A weak misses.
a=arr[2]; weak=(a['reference']>=.1)&(a['reference']<1); lost=weak&(a['ORIGINAL']>=.1)&(a['A']<.1)
rec=set(map(int,a['flat_index_yx'][lost&(a['C']>=.1)])); unrec=set(map(int,a['flat_index_yx'][lost&(a['C']<.1)]))
require(rec=={10942,11093,11242} and len(unrec)==7,'h02 C recovery IDs')
require({int(r['flat_index_yx']) for r in by_group['h02_loss_recovered_by_C']}==rec,'recovered labels')
require({int(r['flat_index_yx']) for r in by_group['h02_loss_unrecovered_by_C']}==unrec,'unrecovered labels')
# Control identities and matching states.
controls=read('matched_controls.csv'); focus=read('focus_membership.csv'); ctl_by_group=defaultdict(list)
for r in controls:ctl_by_group[r['cohort_label']].append(r)
for group,target_ids in ((g,{int(x['flat_index_yx']) for x in by_group[g]}) for g in by_group):
 rows=ctl_by_group[group]; require({int(r['target_flat_index_yx']) for r in rows}==target_ids,f'{group}: control target coverage')
 require(all(r['valid_match']=='True' for r in rows),f'{group}: missing control')
 ctlids=[int(r['control_flat_index_yx']) for r in rows]
 require(len(set(ctlids))==len(ctlids),f'{group}: control reused within group')
# Independent check each control classification and observed band.
def haversine(lat1,lon1,lat2,lon2):
 lat1,lon1,lat2,lon2=(np.radians(x) for x in (lat1,lon1,lat2,lon2)); da=lat2-lat1; db=lon2-lon1
 q=np.sin(da/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin(db/2)**2
 return 2*6371*np.arcsin(np.sqrt(np.clip(q,0,1)))
for r in controls:
 lead=int(r['lead_hour']); t=float(r['threshold_mm']); oldcase,newcase=r['baseline_case'],r['candidate_case']; a=arr[lead]; ti=ids_by_hour[lead][int(r['target_flat_index_yx'])]; ci=ids_by_hour[lead][int(r['control_flat_index_yx'])]
 require(band(a['reference'][ci])==r['observed_band'],'matched control observed band')
 require(math.isclose(float(r['distance_km']),float(haversine(a['latitude'][ti],a['longitude'][ti],a['latitude'][ci],a['longitude'][ci])),rel_tol=0,abs_tol=1e-9),'control distance')
 event='retained_hit' if r['control_state']=='retained_hit' else 'retained_correct_negative'
 obs=a['reference'][ci]>=t; old=a[oldcase][ci]>=t; new=a[newcase][ci]>=t
 valid=(obs and old and new) if event=='retained_hit' else ((not obs) and (not old) and (not new))
 require(valid,f"{r['cohort_label']}: control not {event}")
# Nearest available unused stable control check, per target-group; same band, tie flat index.
for group,rows in ctl_by_group.items():
 used=set();
 for r in sorted(rows,key=lambda x:int(x['target_flat_index_yx'])):
  lead=int(r['lead_hour']);t=float(r['threshold_mm']);a=arr[lead]; oldcase,newcase=r['baseline_case'],r['candidate_case']; ti=ids_by_hour[lead][int(r['target_flat_index_yx'])]
  obs=a['reference']>=t; old=a[oldcase]>=t;new=a[newcase]>=t
  stable=(obs&old&new) if r['control_state']=='retained_hit' else (~obs&~old&~new)
  same=np.array([band(v)==r['observed_band'] for v in a['reference']]); candidate=stable&same
  candidate &= ~np.isin(a['flat_index_yx'],list(used)); candidate[ti]=False
  inds=np.flatnonzero(candidate)
  ds=haversine(a['latitude'][ti],a['longitude'][ti],a['latitude'][inds],a['longitude'][inds])
  order=np.lexsort((a['flat_index_yx'][inds],ds)); nearest=int(a['flat_index_yx'][inds[order[0]]])
  require(nearest==int(r['control_flat_index_yx']),f'{group}: not nearest unused control')
  used.add(nearest)
# Reuse audit exact.
reuse=read('control_reuse_audit.csv'); reuse_calc=defaultdict(list)
for r in controls:reuse_calc[int(r['control_flat_index_yx'])].append(r['cohort_label'])
expected_reuse={i:sorted(set(gs)) for i,gs in reuse_calc.items() if len(set(gs))>1}
actual_reuse={int(r['control_flat_index_yx']):r for r in reuse}
require(set(actual_reuse)==set(expected_reuse),'reuse audit id set')
for i,groups in expected_reuse.items():
 require(int(actual_reuse[i]['reuse_count'])==len(reuse_calc[i]),'reuse count')
 require(actual_reuse[i]['cohort_labels']==';'.join(groups),'reuse labels')
# Focus membership binds all target and control points exactly once.
focus_rows=read('focus_membership.csv'); focus_by_id={int(r['flat_index_yx']):r for r in focus_rows}
require(len(focus_by_id)==len(focus_rows)==receipt['unique_focus_points'],'unique focus membership')
for r in events:
 key=int(r['flat_index_yx']); require(key in focus_by_id and r['cohort_label'] in focus_by_id[key]['cohort_labels'].split(';'),'target included in focus membership')
for r in controls:
 key=int(r['control_flat_index_yx']); require(key in focus_by_id and ('control_for:'+r['cohort_label']) in focus_by_id[key]['cohort_labels'].split(';'),'control included in focus membership')
# Reuse flags and row-level execution metadata must agree with the long-form reuse audit.
for r in controls:
 key=int(r['control_flat_index_yx']); groups=expected_reuse.get(key,[])
 require(int(r['control_reuse_count'])==len(reuse_calc[key]),'per-row control reuse count')
 require((r['control_reused_across_cohorts']=='True')==(len(groups)>1),'per-row cross-cohort reuse flag')
# Recompute the four requested transition census grids directly from the six source arrays.
transition_rows=read('transition_counts.csv'); require(len(transition_rows)==128,'transition count row inventory')
for r in transition_rows:
 lead=int(r['lead_hour']);t=float(r['threshold_mm']);oldcase=r['baseline_case'];newcase=r['candidate_case'];a=arr[lead]
 ref=a['reference']; bands=np.array([band(v) for v in ref]); obs=ref>=t;old=a[oldcase]>=t;new=a[newcase]>=t
 masks={'retained_hit':obs&old&new,'lost_hit':obs&old&~new,'gained_hit':obs&~old&new,'both_miss':obs&~old&~new,'retained_false_alarm':~obs&old&new,'removed_false_alarm':~obs&old&~new,'new_false_alarm':~obs&~old&new,'retained_correct_negative':~obs&~old&~new}
 expected=int(np.count_nonzero(masks[r['transition']]&(bands==r['observed_band'])))
 require(expected==int(r['count']),'transition count independent recount')
# Exact temporal target interpretation: 17 h5 weak losses, pointwise C-A rain amount sum over leads4-6.
ids=sorted(mask_event(arr[5],5,.1,'A','C','lost_hit','[0.1,1)')); signs=[]
for key in ids:
 delta=0.
 for lead in (4,5,6):
  i=ids_by_hour[lead][key]; delta+=float(arr[lead]['C'][i]-arr[lead]['A'][i])
 signs.append(delta)
require(sum(x>0 for x in signs)==5 and sum(x<0 for x in signs)==12 and sum(x==0 for x in signs)==0,'h5 17-point interval sign counts')
summary=read('temporal_cohort_summary.csv'); row=next(r for r in summary if r['cohort_label']=='h05_A_C_weak_hit_loss')
require((int(row['positive_point_count']),int(row['negative_point_count']),int(row['zero_point_count']))==(5,12,0),'temporal cohort summary')
# Algebra exact result and hit-only repair for all cells.
alg=read('csi_algebra.csv'); algebra_rows=0
for r in alg:
 cand=r['contrast'][0]; o,hA,fA,hc,fc=(int(r[k]) for k in ('observed_O_H_plus_M','A_H','A_F',f'{cand}_H',f'{cand}_F'))
 if int(r['threshold_mm'].split('.')[0]) if False else False:pass
 denA=o+fA;denC=o+fc
 if denA and denC:
  num=(hc-hA)*denA-hA*(fc-fA); den=denA*denC
  from fractions import Fraction
  exact=Fraction(num,den)
  require(r['delta_CSI_reconstructed']==str(exact)==r['delta_CSI_recount'],'CSI exact decomposition')
  require(r['restored_baseline_hit_with_candidate_F_exact_CSI']==str(Fraction(hA,denC)),'restored baseline hit exact CSI')
 else:
  require(not r['valid_csi'],'undefined CSI should be invalid')
 algebra_rows+=1
# Report artifact hashes and independent assertions.
receipt['independent_review_checks']={'source_arrays':6,'focus_points':len(focus_rows),'target_rows':len(events),'control_pairs':len(controls),'unique_reused_controls':len(expected_reuse),'transition_count_rows':len(transition_rows),'csi_algebra_rows':algebra_rows}
print(json.dumps(receipt['independent_review_checks'],indent=2))
