#!/usr/bin/env python3
"""Validate two WRF histories, input identities, five ownership and pointer chains."""
import collections,hashlib,json,math,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); dest=Path(sys.argv[2]); c=root/'control_terminal';p=root/'probe_terminal'
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for d in (c,p):
 names=json.loads((d/'staged.json').read_text())
 assert len(names)==89 and all(sha(d/n)==v for n,v in names.items())
 assert sum('SUCCESS COMPLETE WRF' in x.read_text(errors='replace') for x in d.glob('rsl.out.*'))==8
assert (c/'staged.json').read_bytes()==(p/'staged.json').read_bytes()
histories={}
for t in ('12:00:00','12:01:20'):
 n='wrfout_d01_2026-08-16_'+t
 h=sha(c/n); assert h==sha(p/n);histories[t]=h
for f in (p/'capture').glob('gdb_rank*.log'):
 t=f.read_text(errors='replace');assert not any(x in t for x in ('Traceback','Error','Exception','SIGSEGV')) and 'exited normally' in t
rows=[json.loads(s) for f in sorted((p/'capture').glob('rank*.jsonl')) for s in f.read_text().splitlines()]
assert len(rows)==290
counts=collections.Counter((x['kind'],x['event']) for x in rows)
assert counts=={('tend','entry'):45,('tend','return'):45,('update','entry'):90,('update','return'):90,('prep','entry'):5,('prep','return'):5,('kdm','entry'):5,('kdm','return'):5}
file_values=json.loads((dest/'file_values.json').read_text()); checks=[]
for inputrow in file_values['values']:
 cell=inputrow['cell'];r=[x for x in rows if x['cell']==cell];assert len({x['rank'] for x in r})==1
 k=next(x for x in r if x['kind']=='kdm' and x['event']=='entry');pr=next(x for x in r if x['kind']=='prep' and x['event']=='return')
 assert all(pr['bases'][a]==k['bases'][b] for a,b in [('rho','den'),('th','th'),('pii','pii'),('p_full','p')])
 for species in ('qi','qs','ni'):
  for kind in ('tend','update'):
   hits=[x for x in r if x['kind']==kind and x['event']=='entry' and x['current_base']==k['bases'][species]]
   assert len(hits)==3 and sorted(x['rk_step'] for x in hits)==[1,2,3]
   assert all(x['species_index']==x['runtime_species'][species.upper()] for x in hits)
   if kind=='update':
    returns=[x for x in r if x['kind']=='update' and x['event']=='return' and x['current_base']==k['bases'][species] and x['rk_step']==3]
    assert len(returns)==1 and returns[0]['fields']['current']['hex_le']==k['fields'][species]['hex_le']
   if kind=='tend':assert all(x['moist_flag']==(species!='ni') for x in hits)
  # Each recorded REAL32 has matching value and bytes.
 for x in r:
  for v in x['fields'].values():
   assert math.isfinite(v['value']) and struct.pack('<f',v['value']).hex()==v['hex_le']
 entry=k['fields']; f=inputrow['fields'];tk=struct.unpack('<f',struct.pack('<f',entry['th']['value']*entry['pii']['value']))[0]
 checks.append({'cell':cell,'owner_rank':k['rank'],'file':{n:f[n] for n in ('QICE','QSNOW','QNICE','AL','ALB','T','P','PB','QVAPOR')},'kdm_entry':{n:entry[n] for n in ('qi','qs','ni','den','th','pii','p','qv')},'tk_float32_th_times_pii':tk,'rk_pointer_chain_all_stages':True,'rk3_return_equals_kdm_entry_raw_words':True,'prep_pointer_chain':True})
source=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/host')
receipt={'status':'PASS_SCOPED_HISTORICAL_NATIVE_TRACE','scope':'Five cells, unchanged historical B1; no newly initialized input, policy acceptance or forecast validation. Pointer identity proves binding, not sole cause of boundary differences. TK is offline float32 TH*PII, not directly observed TK.','input_sha256':sha(p/'wrfinput_d01'),'exe_sha256':sha(p/'wrf.exe'),'history_hashes_equal_between_arms':histories,'runtime_mapping':{'QI':5,'QS':6,'NI':4},'record_counts':{f'{k[0]}_{k[1]}':v for k,v in counts.items()},'cells':checks,'source_sha256':{str(source/n):sha(source/n) for n in ('dyn_em/solve_em.f90','dyn_em/module_em.f90','phys/module_microphysics_driver.f90')},'elapsed_seconds':{d.name:float((d/'elapsed.txt').read_text()) for d in (c,p)},'limits':['Saved preprocessed sources have prior object/library identity association, not a reproduced original compilation transcript.','Small selected-cell evidence; no domain conservation, physical treatment of 1362 empty intervals, or scientific acceptance.','History at t=0 and t=80 identical; this is not exhaustive proof of every transient intermediate model value.']}
(dest/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(receipt['status'],histories)
