from __future__ import annotations
import gzip, hashlib, json, math, sys, struct
from decimal import Decimal, localcontext
from pathlib import Path
sys.path.insert(0, '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL/tools')
from pr65_pbl_operator_replay import solve_f32
BASE=Path('/var/tmp')
run=BASE/'pr87_joint_OFF_40s_v25diag_20261016/run'
log=run/'rsl.out.0000.gz'
receipt=BASE/'pr87_joint_OFF_40s_v25diag_20261016/receipt.json'
build=BASE/'pr87_joint_cycle_build_20261016_v25diag/pr87_native_overlay_build.json'
exe=BASE/'pr87_joint_cycle_build_20261016_v25diag/wrf_pr87_overlay.exe'
em=BASE/'pr87_joint_cycle_sources_20261016_v25diag/module_em_pr85.F'
kernel=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL/src/common/cloud_bal_joint_transport.f90')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dec64(s): return Decimal.from_float(float(s.replace('D','E').replace('d','e')))
def f32cast(x): return struct.unpack('>f',struct.pack('>f',float(x)))[0]
def solve_decimal(lo,di,up,rhs):
 with localcontext() as ctx:
  ctx.prec=80
  n=len(rhs); cp=[Decimal(0)]*n; dp=[Decimal(0)]*n
  den=di[0]
  if den==0: raise ValueError('zero pivot')
  cp[0]=up[0]/den
  dp[0]=rhs[0]/den
  for k in range(1,n):
   den=di[k]-lo[k]*cp[k-1]
   if den==0: raise ValueError('zero pivot')
   cp[k]=up[k]/den if k+1<n else Decimal(0)
   dp[k]=(rhs[k]-lo[k]*dp[k-1])/den
  out=[Decimal(0)]*n
  out[-1]=dp[-1]
  for k in range(n-2,-1,-1): out[k]=dp[k]-cp[k]*out[k+1]
  return out
headers={}; rows={}
with gzip.open(log,'rt',encoding='utf-8') as f:
 for ln,line in enumerate(f,1):
  t=line.split()
  if not t: continue
  if t[0]=='PR87_SHINHONG_PBL_HEADER':
   if len(t)!=12: raise ValueError(f'header width {ln} {len(t)}')
   ints=tuple(map(int,t[1:9])); call,j,i,pair,qchan,nchan,kts,kte=ints
   key=(call,j,i)
   if key in headers: raise ValueError('duplicate header '+repr(key))
   headers[key]={'call':call,'j':j,'i':i,'pair':pair,'qchannel':qchan,'nchannel':nchan,'kts':kts,'kte':kte,'dt':float(t[9]),'dt2':float(t[10]),'rdt':float(t[11]),'line':ln}
   rows[key]=[]
  elif t[0]=='PR87_SHINHONG_PBL_ROW':
   if len(t)!=18: raise ValueError(f'row width {ln} {len(t)}')
   ints=tuple(map(int,t[1:7])); call,j,i,k,qchan,nchan=ints
   key=(call,j,i)
   if key not in headers: raise ValueError('row before header '+repr(key))
   vals=[dec64(x) for x in t[7:]]
   if len(vals)!=11: raise ValueError('row numeric width')
   rows[key].append({'k':k,'qchannel':qchan,'nchannel':nchan,'lower':vals[0],'diagonal':vals[1],'upper':vals[2], 'qx_q':vals[3],'qx_n':vals[4],'rhs_q':vals[5],'rhs_n':vals[6],'sol64_q':vals[7],'sol64_n':vals[8],'native_f3_q':vals[9],'native_f3_n':vals[10],'line':ln})
if len(headers)!=2: raise ValueError(f'expected 2 PBL calls, got {len(headers)}')
call_results=[]
for key,h in headers.items():
 rr=rows[key]
 if len(rr)!=h['kte']-h['kts']+1 or [r['k'] for r in rr]!=list(range(h['kts'],h['kte']+1)): raise ValueError('incomplete/out-of-order rows '+repr(key))
 if any((r['qchannel'],r['nchannel'])!=(h['qchannel'],h['nchannel']) for r in rr): raise ValueError('channel mismatch')
 lo=[r['lower'] for r in rr]; di=[r['diagonal'] for r in rr]; up=[r['upper'] for r in rr]
 if lo[0]!=0 or up[-1]!=0: raise ValueError('nonclosed endpoints')
 if any(r['qx_q']!=r['rhs_q'] or r['qx_n']!=r['rhs_n'] for r in rr): raise ValueError('qx/rhs input mismatch')
 if any(x>0 for x in lo+up) or any(x==0 for x in di): raise ValueError('invalid matrix sign/pivot')
 outputs={}
 for species in ('q','n'):
  rhs=[r['rhs_'+species] for r in rr]
  dec=solve_decimal(lo,di,up,rhs)
  f32=solve_f32([float(x) for x in lo],[float(x) for x in di],[float(x) for x in up],[float(x) for x in rhs])
  observed64=[r['sol64_'+species] for r in rr]
  native=[r['native_f3_'+species] for r in rr]
  same32=[float(x)==float(y) for x,y in zip(f32,native)]
  maxabs64=max(abs(Decimal.from_float(float(x))-d) for x,d in zip(observed64,dec))
  maxrel64=max((abs(Decimal.from_float(float(x))-d)/max(abs(d),Decimal('1e-300')) for x,d in zip(observed64,dec)))
  outputs[species]={'f32_exact_native_match_count':sum(same32),'levels':len(rr),'f32_max_abs_vs_native':max(abs(float(x)-float(y)) for x,y in zip(f32,native)), 'decimal80_k11':str(dec[10]),'decimal80_max_abs_vs_logged_sol64':float(maxabs64),'decimal80_max_rel_vs_logged_sol64':float(maxrel64),'decimal80_vs_logged_sol64_tolerance_claim':'diagnostic comparison only; input decimal tokens are reconstructed as binary64 before exact-decimal solve'}
 call_results.append({'header':{k:v for k,v in h.items() if k!='line'},'row_count':len(rr),'k11':{k:(float(v) if isinstance(v,Decimal) else v) for k,v in rr[10].items() if k!='line'},'matrix_rows':[{'k':r['k'],'lower':str(r['lower']),'diagonal':str(r['diagonal']),'upper':str(r['upper']),'qx_q':str(r['qx_q']),'qx_n':str(r['qx_n']),'rhs_q':str(r['rhs_q']),'rhs_n':str(r['rhs_n']),'sol64_q':str(r['sol64_q']),'sol64_n':str(r['sol64_n']),'native_f3_q':str(r['native_f3_q']),'native_f3_n':str(r['native_f3_n'])} for r in rr],'solutions':outputs})
# requested target = call2, k11
c2=next(x for x in call_results if x['header']['call']==2); row=c2['k11']
cloud_pidn=523.59881591796875; lam_min=12000.0; lam_max=500000.0
mass_min=cloud_pidn/lam_max**3; mass_max=cloud_pidn/lam_min**3
qsrc=row['rhs_q']; nsrc=row['rhs_n']; q64=row['sol64_q']; n64=row['sol64_n']; q32=row['native_f3_q']; n32=row['native_f3_n']; qdec=Decimal(c2['solutions']['q']['decimal80_k11']); ndec=Decimal(c2['solutions']['n']['decimal80_k11'])
q_rate64=(q64-row['qx_q'])*float(c2['header']['rdt'])
n_rate64=(n64-row['qx_n'])*float(c2['header']['rdt'])
q_rate32=f32cast(f32cast(q32-row['qx_q'])*f32cast(c2['header']['rdt']))
n_rate32=f32cast(f32cast(n32-row['qx_n'])*f32cast(c2['header']['rdt']))
result={'schema':'pr87_v25diag_shinhong_matrix_audit_v1','scope':'read-only audit of two captured Shinhong PBL matrix calls; V25 diagnostic run is INCOMPLETE after 20 s; not a completed 40 s model result','run_receipt':{'path':str(receipt),'sha256':sha(receipt),'status':json.load(open(receipt))['status'],'returncode':json.load(open(receipt))['returncode'],'final_completed_step':json.load(open(receipt))['final_completed_step'],'executed_executable_sha256':json.load(open(receipt))['executed_executable_sha256'],'build_receipt_sha256':json.load(open(receipt))['candidate_build']['receipt_sha256']},'build_executable_sha256':sha(exe),'build_receipt_actual_sha256':sha(build),'module_em_sha256':sha(em),'kernel_sha256':sha(kernel),'rsl_out_gz_sha256':sha(log),'pbl_bound':{'pidn_r32':cloud_pidn,'lambda_min':lam_min,'lambda_max':lam_max,'mass_min_q_over_n':mass_min,'mass_max_q_over_n':mass_max},'calls':call_results,'target_k11_call2':{'coordinate_j_i_k':[c2['header']['j'],c2['header']['i'],11],'rhs_is_zero_pair':qsrc==0 and nsrc==0,'logged_sol64_q_over_n':q64/n64,'decimal80_solution_q_over_n':float(qdec/ndec),'decimal80_solution_strict_valid':Decimal.from_float(mass_min)<=qdec/ndec<=Decimal.from_float(mass_max),'native_r32_q_over_n':q32/n32,'native_r32_strict_valid':mass_min<=q32/n32<=mass_max,'native_q_bits':int.from_bytes(struct.pack('>f',q32),'big'),'native_n_bits':int.from_bytes(struct.pack('>f',n32),'big'),'decimal80_to_r32_ratio_delta':q32/n32-float(qdec/ndec),'rdt':float(c2['header']['rdt']),'unrounded_r64_tendency_q':q_rate64,'unrounded_r64_tendency_n':n_rate64,'unrounded_r64_tendency_q_over_n':q_rate64/n_rate64,'unrounded_r64_tendency_strict_valid':mass_min<=q_rate64/n_rate64<=mass_max,'source_r32_tendency_q':q_rate32,'source_r32_tendency_n':n_rate32,'source_r32_tendency_q_over_n':q_rate32/n_rate32,'source_r32_tendency_strict_valid':mass_min<=q_rate32/n_rate32<=mass_max,'source_r32_tendency_q_bits':int.from_bytes(struct.pack('>f',q_rate32),'big'),'source_r32_tendency_n_bits':int.from_bytes(struct.pack('>f',n_rate32),'big')}}
out=BASE/'pr87_v25diag_shinhong_matrix_audit.json';out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(out)
for c in call_results:
 print('CALL',c['header']['call'],'target',c['header']['i'],c['header']['j'],'rows',c['row_count'],'Q f32 match',c['solutions']['q']['f32_exact_native_match_count'],'N f32 match',c['solutions']['n']['f32_exact_native_match_count'],'decimal sol diff',c['solutions']['q']['decimal80_max_rel_vs_logged_sol64'],c['solutions']['n']['decimal80_max_rel_vs_logged_sol64'])
t=result['target_k11_call2']; print('k11 call2 coordinate',t['coordinate_j_i_k'],'rhs zero',t['rhs_is_zero_pair'],'R64 solution ratio/valid',t['decimal80_solution_q_over_n'],t['decimal80_solution_strict_valid'],'native f3 ratio/valid',t['native_r32_q_over_n'],t['native_r32_strict_valid'],'R64 tendency ratio/valid',t['unrounded_r64_tendency_q_over_n'],t['unrounded_r64_tendency_strict_valid'],'R32 tendency ratio/valid',t['source_r32_tendency_q_over_n'],t['source_r32_tendency_strict_valid'])
