import sys,json,csv,math,struct,collections
from pathlib import Path
sys.path.insert(0,'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/runtime/tooling')
from scan_state_streams import scan,STAGES
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
schema=json.loads((R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/native/schema/cp03_schema.json').read_text())
corners={(int(x['wrf_i_1based']),int(x['wrf_j_1based'])) for x in csv.DictReader((R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/newcohorts/unique_global_corners.csv').open())};assert len(corners)==36
for arm in ['B1','NR_PRIOR']:
 d=R/'runtime/quick'/arm
 streams=[scan(d/f'state_{stage}_rank{rank}.bin',rank,stage_id) for rank in range(8) for stage_id,stage in STAGES.items()]
 rows=collections.Counter(); sets={k:set() for k in range(1,7)}; steps=set(); ranks=set(); loops=set()
 for path in d.glob('cp03_rank*.bits'):
  rank=int(path.stem.split('rank')[1]);ranks.add(rank)
  def records():
   record=[]
   for line in path.open():
    parts=line.split()
    if parts and parts[0]=='CP03':
     if record: yield record
     record=parts
    else:
     assert record
     record.extend(parts)
   if record: yield record
  for a in records():
   assert a[0]=='CP03';p,r,c,t,loop,nloops,i,j,k,n,m,nf=map(int,a[1:13]);v=list(map(int,a[13:]));assert r==rank and 1<=p<=6 and len(v)==nf==len(schema['phases'][str(p)]['fields']);assert 1<=loop<=nloops and 1<=k<=39 and (i,j) in corners and t>=1
   for b in v: assert math.isfinite(struct.unpack('>f',struct.pack('>i',b))[0])
   if p in (1,2):assert 1<=n<=m
   else:assert n==0 and m==0
   key=(r,c,t,loop,nloops,i,j,k,n,m); assert key not in sets[p];sets[p].add(key);rows[p]+=1;steps.add(t);loops.add(nloops)
 assert sets[1]==sets[2] and sets[3]==sets[4] and sets[5]==sets[6]
 substeps={}
 for r,c,t,loop,nloops,i,j,k,n,m in sets[1]:
  key=(r,c,t,loop,nloops,i,j,k,m);substeps.setdefault(key,set()).add(n)
 assert all(ns==set(range(1,key[-1]+1)) for key,ns in substeps.items())
 assert loops=={1}
 assert {(x[5],x[6],x[7]) for x in sets[1]}=={(i,j,k) for i,j in corners for k in range(1,40)}
 assert {(x[5],x[6],x[7]) for x in sets[5]}=={(i,j,k) for i,j in corners for k in range(1,40)}
 assert rows[3]>0
 out={'status':'PASS','state_streams':len(streams),'state_finite':True,'state_headers_and_payload_complete':True,'cp03_finite':True,'phase_counts':rows,'ranks_with_selected_cells':sorted(ranks),'timesteps':sorted(steps),'loops':sorted(loops),'matched_pre_post':True,'all_36_cells_all_39_layers_present':True}
 (d/'schema_gate.json').write_text(json.dumps(out,indent=2)+'\n');print(arm,json.dumps(out),flush=True)
