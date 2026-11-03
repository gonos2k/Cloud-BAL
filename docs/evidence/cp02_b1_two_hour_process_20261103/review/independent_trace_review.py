import gzip, json, struct, hashlib, csv
from pathlib import Path
from collections import Counter, defaultdict
ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
RAW=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_two_hour_probe_20261103/payloads')
COORDS={(int(x['j']),int(x['i'])) for x in json.loads((ROOT/'cells.json').read_text())['coordinates']}
CORNER_MAP={}
with open(ROOT/'cohorts/corners.csv',newline='') as _f:
 for _r in csv.DictReader(_f): CORNER_MAP[(int(_r['wrf_j_1based']),int(_r['wrf_i_1based']))]=(_r['point_id'],float(_r['weight']))
LENS={'ENTRY_RAW':23,'ENTRY_CLAMPED':23,'SATURATION':16,'SATDT':13,'PREVP_FORMULA':15,'PREVP_RAW':12,'PREVP_QR_CAP':9,'PREVP_SAT_CAP':9,'PROCESS_RATES':24,'PRE_UPDATE':25,'LATENT_INPUT':14,'POST_STEP':23,'SURFACE_RETURN':9,'SNOW_RETURN':7,'GRAUPEL_RETURN':7}
def f32(s): return struct.unpack('>f',struct.pack('>I',int(s)&0xffffffff))[0]
def r32(x): return struct.unpack('>f',struct.pack('>f',float(x)))[0]
def f64(s): return struct.unpack('>d',struct.pack('>Q',int(s)&0xffffffffffffffff))[0]
def ident(v): return tuple(map(int,v[1:8])) # rank,call,step,loop,j,i,k
def scan(case):
 path=RAW/f'{case}_kdm6_trace_rank3.bits.gz'
 sha=hashlib.sha256(path.read_bytes()).hexdigest()
 phases=defaultdict(dict); pcount=Counter(); pending=None; lineno=0; counts=Counter()
 with gzip.open(path,'rt',encoding='ascii') as fh:
  for line in fh:
   lineno+=1; w=line.split()
   if not w: continue
   if w[0] in LENS:
    if pending is not None: raise RuntimeError(f'incomplete before {lineno}')
    pending=[w[0],w[1:]]
   elif pending is not None: pending[1].extend(w)
   else: raise RuntimeError(f'continuation at {lineno}')
   if pending and len(pending[1])+1==LENS[pending[0]]:
    name=pending[0]; v=[name]+pending[1]; pending=None
    if name in ('PREVP_FORMULA','PREVP_RAW','PREVP_QR_CAP','PREVP_SAT_CAP','PROCESS_RATES','PRE_UPDATE','LATENT_INPUT','POST_STEP','ENTRY_RAW'):
     if (int(v[5]),int(v[6])) in COORDS:
      k=ident(v); pcount[name]+=1
      if name=='ENTRY_RAW': counts['entry_raw_rows']+=1
      else:
       if k in phases[name]: counts['duplicate_'+name]+=1
       phases[name][k]=v
  if pending: raise RuntimeError('trailing incomplete')
 # Evaluate events from each matched PREVP_RAW.
 zero_raw=[]; qrs_zero_neg=[]; raw_minus_any=[]
 for k,raw in phases['PREVP_RAW'].items():
  rb=int(raw[8]); rawv=f32(raw[8]); qrs=f32(raw[9]); sat=f32(raw[10]); dt=f32(raw[11])
  formula=phases['PREVP_FORMULA'].get(k); qr=phases['PREVP_QR_CAP'].get(k); cap=phases['PREVP_SAT_CAP'].get(k); process=phases['PROCESS_RATES'].get(k)
  if rb&0x7fffffff==0:
   zero_raw.append((k,raw,formula,qr,cap,process))
  if qrs==0.0 and rawv<0:
   qrs_zero_neg.append((k,raw,formula,qr,cap,process))
  if rawv<0 and cap is not None and f32(cap[8])<0:
   raw_minus_any.append((k,raw,formula,qr,cap,process))
 # Local residuals among corresponding recorded updates, matched on same composite key.
 qres=[]; tres=[]; nrcheck=[]
 for k,pre in phases['PRE_UPDATE'].items():
  lat=phases['LATENT_INPUT'].get(k); post=phases['POST_STEP'].get(k); rates=phases['PROCESS_RATES'].get(k)
  if not (lat and post and rates): continue
  q0,q1=f32(pre[8]),f32(post[8]); t0,t1=f32(pre[9]),f32(post[9]); work=f32(pre[23]); dt=f32(pre[24]); xlw=f32(lat[9]); cp=f32(lat[10]); ldt=f32(lat[11])
  qres.append((abs((q1-q0)-work*dt), k, q1-q0,work*dt))
  tres.append((abs((t1-t0)-(-xlw/cp*ldt)), k,t1-t0,-xlw/cp*ldt))
 # Group zero raw events by point/hour. These are event sums over levels, not column budgets.
 grouped=defaultdict(lambda:{'zero_raw_events':0,'negative_sat_cap_events':0,'negative_final_process_events':0,'sum_final_prevp_dtcld_over_events':0.0,'weighted_sum_final_prevp_dtcld_over_events':0.0,'matched_qt_updates':0,'sum_local_delta_q_over_events':0.0,'sum_local_delta_T_over_events':0.0,'negative_satcap_first_step':None,'negative_satcap_last_step':None})
 for ev in zero_raw:
  key,raw,formula,qrcap,satcap,process=ev; step=key[2]; hour='13Z' if step<=180 else '14Z'; j,i=key[4],key[5]; point,wgt=CORNER_MAP[(j,i)]; g=grouped[(point,hour)]; g['zero_raw_events']+=1
  if satcap is not None and f32(satcap[8])<0:
   g['negative_sat_cap_events']+=1; g['negative_satcap_first_step']=step if g['negative_satcap_first_step'] is None else min(g['negative_satcap_first_step'],step); g['negative_satcap_last_step']=step if g['negative_satcap_last_step'] is None else max(g['negative_satcap_last_step'],step)
  if process is not None and f32(process[10])<0:
   g['negative_final_process_events']+=1; val=f32(process[10])*f32(raw[11]); g['sum_final_prevp_dtcld_over_events']+=val; g['weighted_sum_final_prevp_dtcld_over_events']+=wgt*val
  if key in phases['PRE_UPDATE'] and key in phases['POST_STEP']:
   pre=phases['PRE_UPDATE'][key]; post=phases['POST_STEP'][key]; g['matched_qt_updates']+=1; g['sum_local_delta_q_over_events']+=f32(post[8])-f32(pre[8]); g['sum_local_delta_T_over_events']+=f32(post[9])-f32(pre[9])
 # Summarize negative zero and events; include paired state and exact line words for spot-check samples.
 def sample(events):
  out=[]
  for k,raw,formula,qr,cap,process in events[:30]:
   out.append({'key':list(k),'raw_prev_word':raw[8],'raw_prev':f32(raw[8]),'qrs_word':raw[9],'qrs':f32(raw[9]),
     'satdt':f32(raw[10]),'dtcld':f32(raw[11]),
     'formula_prev_word':formula[8] if formula else None,'formula_prev':f32(formula[8]) if formula else None,
     'nrs_word':formula[9] if formula else None,'nrs':f32(formula[9]) if formula else None,
     'den':f32(formula[11]) if formula else None,'rh':f32(formula[12]) if formula else None,
     'n0r':f64(formula[13]) if formula else None,'fac_evap':f32(formula[14]) if formula else None,
     'qr_cap_word':qr[8] if qr else None,'qr_cap':f32(qr[8]) if qr else None,
     'sat_cap_word':cap[8] if cap else None,'sat_cap':f32(cap[8]) if cap else None,
     'process_prev_word':process[10] if process else None,'process_prev':f32(process[10]) if process else None})
  return out
 result={'case':case,'trace_path':str(path),'compressed_sha256':sha,'compressed_bytes':path.stat().st_size,'selected_coordinates':len(COORDS),
  'selected_phase_rows':dict(pcount),'selected_exact_zero_PREVP_RAW_count':len(zero_raw),
  'exact_zero_raw_cap_negative_timestep_minmax':[min((x[0][2] for x in zero_raw if x[4] is not None and f32(x[4][8])<0),default=None),max((x[0][2] for x in zero_raw if x[4] is not None and f32(x[4][8])<0),default=None)],
  'exact_zero_raw_events_by_point_and_hour':{f'{pt}_{hr}':v for (pt,hr),v in sorted(grouped.items())},
  'selected_exact_zero_PREVP_RAW_cap_negative_count':sum(x[4] is not None and f32(x[4][8])<0 for x in zero_raw),
  'selected_exact_zero_PREVP_RAW_process_negative_count':sum(x[5] is not None and f32(x[5][10])<0 for x in zero_raw),
  'selected_exact_zero_PREVP_RAW_process_zero_count':sum(x[5] is not None and f32(x[5][10])==0 for x in zero_raw),
  'selected_exact_zero_PREVP_RAW_formula_and_number_summary':{
    'formula_zero_count':sum(x[2] is not None and (int(x[2][8])&0x7fffffff)==0 for x in zero_raw),
    'formula_negative_zero_count':sum(x[2] is not None and int(x[2][8])==-2147483648 for x in zero_raw),
    'raw_negative_zero_count':sum(int(x[1][8])==-2147483648 for x in zero_raw),
    'sat_cap_equal_float32_satdt_half_count':sum(x[4] is not None and f32(x[4][8])==f32(int(x[1][10])/2) for x in zero_raw),
    'final_process_equal_inventory_limit_count':sum(x[5] is not None and f32(x[5][10])==f32(-f32(x[1][9])/f32(x[1][11])) for x in zero_raw),
    'nrs_zero_count':sum(x[2] is not None and f32(x[2][9])==0 for x in zero_raw),
    'nrs_positive_count':sum(x[2] is not None and f32(x[2][9])>0 for x in zero_raw),
    'n0r_zero_count':sum(x[2] is not None and f64(x[2][13])==0 for x in zero_raw),
    'n0r_finite_nonzero_count':sum(x[2] is not None and f64(x[2][13])!=0 and abs(f64(x[2][13]))<float('inf') for x in zero_raw),
    'mean_nrs_when_positive':(sum(f32(x[2][9]) for x in zero_raw if x[2] is not None and f32(x[2][9])>0)/max(1,sum(x[2] is not None and f32(x[2][9])>0 for x in zero_raw))),
    'nonzero_nrs_n0r_zero_raw_rows':[{'key':list(x[0]),'nrs_word':x[2][9],'nrs':f32(x[2][9]),'n0r_word':x[2][13],'n0r':f64(x[2][13]),'rh_word':x[2][12],'rh':f32(x[2][12]),'qrs':f32(x[1][9]),'formula_prev':f32(x[2][8]),'fac_evap':f32(x[2][14])} for x in zero_raw if x[2] is not None and f32(x[2][9])>0]
  },
  'selected_qrs_zero_and_PREVP_RAW_negative_count':len(qrs_zero_neg),
  'selected_qrs_zero_PREVP_RAW_negative_QRcap_satcap_PROCESS_counts':{
    'QRcap_present':sum(x[3] is not None for x in qrs_zero_neg),
    'QRcap_zero':sum(x[3] is not None and f32(x[3][8])==0 for x in qrs_zero_neg),
    'SATcap_present':sum(x[4] is not None for x in qrs_zero_neg),
    'SATcap_negative':sum(x[4] is not None and f32(x[4][8])<0 for x in qrs_zero_neg),
    'PROCESS_prev_negative':sum(x[5] is not None and f32(x[5][10])<0 for x in qrs_zero_neg)},
  'PREVP_RAW_negative_to_negative_SATcap_count':len(raw_minus_any),
  'zero_PREVP_RAW_update_correspondence':{
    'matched_pre_latent_post_process_count':sum(all(phases[ph].get(x[0]) is not None for ph in ('PRE_UPDATE','LATENT_INPUT','POST_STEP','PROCESS_RATES')) for x in zero_raw),
    'max_abs_q_update_residual':max((abs((f32(phases['POST_STEP'][x[0]][8])-f32(phases['PRE_UPDATE'][x[0]][8]))-f32(phases['PRE_UPDATE'][x[0]][23])*f32(phases['PRE_UPDATE'][x[0]][24])) for x in zero_raw if x[0] in phases['POST_STEP'] and x[0] in phases['PRE_UPDATE']),default=None),
    'max_abs_T_update_residual':max((abs((f32(phases['POST_STEP'][x[0]][9])-f32(phases['PRE_UPDATE'][x[0]][9]))-(-f32(phases['LATENT_INPUT'][x[0]][9])/f32(phases['LATENT_INPUT'][x[0]][10])*f32(phases['LATENT_INPUT'][x[0]][11]))) for x in zero_raw if x[0] in phases['POST_STEP'] and x[0] in phases['PRE_UPDATE'] and x[0] in phases['LATENT_INPUT']),default=None),
    'max_abs_q_update_residual_after_real32_rounding':max((abs(f32(phases['POST_STEP'][x[0]][8])-r32(f32(phases['PRE_UPDATE'][x[0]][8])+r32(f32(phases['PRE_UPDATE'][x[0]][23])*f32(phases['PRE_UPDATE'][x[0]][24])))) for x in zero_raw if x[0] in phases['POST_STEP'] and x[0] in phases['PRE_UPDATE']),default=None),
    'max_abs_T_update_residual_after_real32_rounding':max((abs(f32(phases['POST_STEP'][x[0]][9])-r32(f32(phases['PRE_UPDATE'][x[0]][9])-r32(r32(f32(phases['LATENT_INPUT'][x[0]][9])/f32(phases['LATENT_INPUT'][x[0]][10]))*f32(phases['LATENT_INPUT'][x[0]][11])))) for x in zero_raw if x[0] in phases['POST_STEP'] and x[0] in phases['PRE_UPDATE'] and x[0] in phases['LATENT_INPUT']),default=None),
    'process_prev_values_min_max':[min((f32(x[5][10]) for x in zero_raw if x[5]),default=None),max((f32(x[5][10]) for x in zero_raw if x[5]),default=None)]
  },
  'zero_PREVP_RAW_examples':sample(zero_raw),'qrs_zero_raw_negative_examples':sample(qrs_zero_neg),
  'local_update_pairs':len(qres),'max_abs_q_update_residual':max((x[0] for x in qres),default=None),
  'max_abs_T_update_residual':max((x[0] for x in tres),default=None),
  'q_residual_top5':[{'abs_residual':x[0],'key':list(x[1]),'delta_q':x[2],'work2_dt':x[3]} for x in sorted(qres,reverse=True)[:5]],
  'T_residual_top5':[{'abs_residual':x[0],'key':list(x[1]),'delta_T':x[2],'minus_xlwork2_over_cpm_dt':x[3]} for x in sorted(tres,reverse=True)[:5]],
  'duplicate_relevant_records':{k:v for k,v in counts.items() if k.startswith('duplicate_')}}
 return result
if __name__=='__main__':
 out=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_two_hour_probe_20261103/analysis_scratch/independent_trace_review.json')
 res={'independent_method':'custom gzip streaming/token collector written for this review; stores only selected records keyed by rank,call_id,itimestep,loop,j,i,k; no use/import of maintained analyzer','cases':[scan('OLD'),scan('FIX')]}
 out.write_text(json.dumps(res,indent=2)+'\n')
 print(out)
 for x in res['cases']:
  print(x['case'],x['selected_exact_zero_PREVP_RAW_count'],x['selected_qrs_zero_and_PREVP_RAW_negative_count'],x['selected_qrs_zero_PREVP_RAW_negative_QRcap_satcap_PROCESS_counts'],x['max_abs_q_update_residual'],x['max_abs_T_update_residual'])
