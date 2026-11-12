import hashlib, json
from pathlib import Path
import numpy as np

root=Path(__file__).resolve().parent.parent
npz=root/'coverage/actual_12utc/diagnostic_only.npz'
policy_path=root/'fixed_application/policy.json'
report_path=root/'coverage/actual_12utc/coverage.json'
attempt=root/'production_attempt/attempt.json'
policy=json.loads(policy_path.read_text()); report=json.loads(report_path.read_text()); rec=json.loads(attempt.read_text())
sha=lambda p:hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
with np.load(npz,allow_pickle=False) as z:
 mask=z['selected_fixed_mask']; status=z['status'][mask]; idx=z['selected_flat_indices']; sh=mask.shape
 aqi=z['analysis_qi_selected'].astype(np.float64); aqs=z['analysis_qs_selected'].astype(np.float64); ani=z['analysis_ni_selected'].astype(np.float64)
 bi=z['background_qi_selected'].astype(np.float64); bs=z['background_qs_selected'].astype(np.float64); bn=z['background_ni_selected'].astype(np.float64)
 ad=z['analysis_density_selected'].astype(np.float32); bd=z['background_density_selected'].astype(np.float32)
 context={name:z[name+'_selected'].astype(np.float64) for name in ['analysis_temperature','background_temperature','analysis_pressure','background_pressure','analysis_qv','background_qv']}
assert np.array_equal(idx,np.flatnonzero(mask)) and len(status)==report['selected']
lo,hi,cap=policy['lower'][1],policy['upper'][1],policy['number_cap'][1]
target=aqi+aqs; total=bi+bs; pos=(bi>0)&(bn>0); mean=np.zeros_like(bi)
with np.errstate(divide='ignore',invalid='ignore',over='ignore',under='ignore'):
 np.divide(bi,bn,out=mean,where=pos)
 qi=np.where(total>0,(bi/total)*target,0); qs=np.where(total>0,(bs/total)*target,0)
 qi32=qi.astype(np.float32); qs32=qs.astype(np.float32)
 ni=np.where(pos,qi32.astype(np.float64)/mean,0); ni32=ni.astype(np.float32)
 targetvol=(ni32*ad).astype(np.float32); backvol=(bn.astype(np.float32)*bd).astype(np.float32)
 storedmean=np.where(ni32>0,qi32.astype(np.float64)/ni32.astype(np.float64),0)
 storedtotal=qi32.astype(np.float64)+qs32.astype(np.float64)
 tol=np.finfo(np.float32).eps*np.maximum(target,storedtotal)
tiny=np.finfo(np.float32).tiny; huge=np.finfo(np.float32).max
flags={
 'background_negative_any':(bi<0)|(bs<0)|(bn<0),
 'background_total_zero':total==0,
 'background_ice_positive_number_zero':(bi>0)&(bn==0),
 'background_ice_zero_number_positive':(bi==0)&(bn>0),
 'background_snow_only':(bi==0)&(bs>0)&(bn==0),
 'background_mean_outside_policy':pos&((mean<lo)|(mean>hi)),
 'computed_mass_nonzero_below_float32_normal':((qi>0)&(qi<tiny))|((qs>0)&(qs<tiny)),
 'computed_mass_above_float32_max':(qi>huge)|(qs>huge),
 'computed_ni_nonzero_below_float32_normal':(ni>0)&(ni<tiny),
 'computed_ni_above_float32_max':ni>huge,
 'rounded_ni_times_density_above_policy_cap':targetvol>cap}
failed=status==-10
for name,flag in flags.items():
 assert int(flag.sum())==report['categories'][name]['selected'],name
 assert int((flag&failed).sum())==report['categories'][name]['failed'],name
union=np.logical_or.reduce(list(flags.values())); uf=failed&~union
capflag=flags['rounded_ni_times_density_above_policy_cap']; outside=flags['background_mean_outside_policy']
relative=np.where(mean<lo,(lo-mean)/lo,(mean-hi)/hi)
under=outside&(mean<lo); over=outside&(mean>hi)
proposed_bad=(qi32>0)&(ni32>0)&((storedmean<lo)|(storedmean>hi)); mass_bad=np.abs(storedtotal-target)>tol
names=list(flags); overlaps={}
for i,a in enumerate(names):
 for b in names[i+1:]:
  n=int((failed&flags[a]&flags[b]).sum())
  if n: overlaps[a+' & '+b]=n
flat=np.ravel_multi_index((10,227,149),sh); loc=int(np.searchsorted(idx,flat)); assert idx[loc]==flat
sample={'location_ijk_1based':[150,228,11], 'status':int(status[loc]),'analysis_qice':float(aqi[loc]),'analysis_qsnow':float(aqs[loc]),'analysis_qnice':float(ani[loc]),'background_qice':float(bi[loc]),'background_qsnow':float(bs[loc]),'background_qnice':float(bn[loc]),'analysis_density':float(ad[loc]),'background_density':float(bd[loc]),'background_mean':float(mean[loc]),'target_qice_real32':float(qi32[loc]),'target_qsnow_real32':float(qs32[loc]),'target_qnice_real32':float(ni32[loc]),'target_number_volume_real32':float(targetvol[loc]),'background_number_volume_real32':float(backvol[loc]),'observation_flags':[name for name,v in flags.items() if v[loc]],**{key:float(v[loc]) for key,v in context.items()}}
sample['first_applicable_source_guard']=('background negative or invalid value' if (bi[loc]<0 or bs[loc]<0 or bn[loc]<0) else 'background QI/NI zero mismatch' if ((bi[loc]>0 and bn[loc]==0) or (bi[loc]==0 and bn[loc]>0)) else 'background QI/NI outside bounds' if outside[loc] else 'zero total background' if total[loc]==0 else 'candidate mass sum tolerance' if mass_bad[loc] else 'candidate number cap' if capflag[loc] else 'candidate rounded mean outside bounds' if proposed_bad[loc] else 'not resolved by scalar checks')
def rng(x):return {'count':int(x.size),'min':float(x.min()),'max':float(x.max())} if x.size else {'count':0}
outputs={'scope':'Overlapping observations; not exclusive causes or attribution. Only fixed selected cells. Native density is file proxy float32 1/(AL+ALB).','inputs':{str(p):sha(p) for p in (npz,policy_path,report_path,attempt)},'cap_flags':{'count':int(capflag.sum()),'background_volume_above_cap':int((capflag&(backvol>cap)).sum()),'background_volume_at_or_below_cap':int((capflag&(backvol<=cap)).sum()),'background_volume_multiply':'float32 background QNICE times float32 background density','target_volume_multiply':'float32 rounded proposed QNICE times float32 analysis density'},'background_mean_outside':{'lower_bound':lo,'upper_bound':hi,'below_count':int(under.sum()),'above_count':int(over.sum()),'relative_lower_deficit':rng(relative[under]),'relative_upper_excess':rng(relative[over]),'relative_violation_all':rng(relative[outside]),'float32_eps':float(np.finfo(np.float32).eps)},'selected':len(status),'failures':int(failed.sum()),'flags_union_selected':int(union.sum()),'flags_union_failures':int((union&failed).sum()),'rejected_not_covered_by_original_flags':int(uf.sum()),'pairwise_overlap_failed':overlaps,'uncovered_stored_proposal_mean_outside_bounds':int((uf&proposed_bad).sum()),'uncovered_mass_sum_tolerance_exceeded':int((uf&mass_bad).sum()),'uncovered_stored_mean_relative_violation':rng(np.where(storedmean<lo,(lo-storedmean)/lo,(storedmean-hi)/hi)[uf&proposed_bad]),'first_failed_cell':sample,'production_attempt':{'receipt':rec,'manifest_hash_matches':sha(root/'production_attempt/manifest.json')==rec['manifest_sha256'],'producer_error_log_sha256':sha(root/'production_attempt/producer_error.log'),'directory_entries':sorted(p.name for p in (root/'production_attempt').iterdir())}}
assert int(capflag.sum())==20373 and int(outside.sum())==183
print(json.dumps(outputs,indent=2,allow_nan=False))
