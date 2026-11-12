import hashlib,json
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent.parent
p=root/'coverage/actual_12utc/diagnostic_only.npz'; pp=root/'fixed_application/policy.json'; rp=root/'coverage/actual_12utc/coverage.json'
policy=json.loads(pp.read_text()); report=json.loads(rp.read_text())
with np.load(p,allow_pickle=False) as z:
 mask=z['selected_fixed_mask']; status=z['status'][mask]
 aq=z['analysis_qi_selected'].astype('float64'); ass=z['analysis_qs_selected'].astype('float64')
 bq=z['background_qi_selected'].astype('float64'); bs=z['background_qs_selected'].astype('float64'); bn=z['background_ni_selected'].astype('float64')
 ad=z['analysis_density_selected'].astype('float32'); bd=z['background_density_selected'].astype('float32')
target=aq+ass; total=bq+bs; positive=(bq>0)&(bn>0); mean=np.zeros_like(bq)
with np.errstate(invalid='ignore',divide='ignore',over='ignore',under='ignore'):
 np.divide(bq,bn,out=mean,where=positive)
 qi=np.where(total>0,(bq/total)*target,0).astype('float32')
 ni=np.where(positive,qi.astype('float64')/mean,0).astype('float32')
 vol=(ni*ad).astype('float32'); bgvol=(bn.astype('float32')*bd).astype('float32')
flags={'background_negative_any':(bq<0)|(bs<0)|(bn<0),'background_total_zero':total==0,'background_ice_positive_number_zero':(bq>0)&(bn==0),'background_ice_zero_number_positive':(bq==0)&(bn>0),'background_mean_outside_policy':positive&((mean<policy['lower'][1])|(mean>policy['upper'][1])),'rounded_ni_times_density_above_policy_cap':vol>policy['number_cap'][1]}
for k,x in flags.items():
 assert int(x.sum())==report['categories'][k]['selected'] and int((x&(status==-10)).sum())==report['categories'][k]['failed']
assert np.all(target>0) and len(status)==report['selected']
def quant(x):
 if not len(x): return {'count':0}
 return {'count':int(len(x)), **dict(zip(['min','p01','p10','p25','median','p75','p90','p99','max'],[float(i) for i in np.quantile(x,[0,.01,.10,.25,.5,.75,.90,.99,1])]))}
bins=[]
for name,m in [('(0,1e-12)',(target>0)&(target<1e-12)),('[1e-12,1e-9)',(target>=1e-12)&(target<1e-9)),('[1e-9,1e-6)',(target>=1e-9)&(target<1e-6)),('[1e-6,inf)',target>=1e-6)]:
 bins.append({'interval_kg_kg':name,'selected':int(m.sum()),'accepted':int((m&(status==20)).sum()),'rejected':int((m&(status==-10)).sum())})
assert sum(i['selected'] for i in bins)==report['selected'] and sum(i['rejected'] for i in bins)==report['rejected']
out={'interpretation':'Descriptive numeric bins, not physical activation thresholds. Counts are cells, not mass fractions or forecast impacts. Flag groups overlap; no selection or acceptance change. Density is float32 file proxy 1/(AL+ALB).','input_sha256':{str(x):hashlib.file_digest(open(x,'rb'),'sha256').hexdigest() for x in (p,pp,rp)},'mass_bins':bins,'target_mass_quantiles_kg_kg_by_flag':{k:quant(target[v]) for k,v in flags.items()},'ice_zero_number_positive_background_ni_kg_minus1':quant(bn[flags['background_ice_zero_number_positive']]),'ice_zero_number_positive_background_volume_number_m_minus3':quant(bgvol[flags['background_ice_zero_number_positive']].astype('float64')),'mean_outside':{'count':int(flags['background_mean_outside_policy'].sum()),'target_total_at_least_1e_9':int((flags['background_mean_outside_policy']&(target>=1e-9)).sum()),'background_ice_at_least_1e_12':int((flags['background_mean_outside_policy']&(bq>=1e-12)).sum()),'both_thresholds':int((flags['background_mean_outside_policy']&(target>=1e-9)&(bq>=1e-12)).sum())}}
print(json.dumps(out,indent=2,allow_nan=False))
