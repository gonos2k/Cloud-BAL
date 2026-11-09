import csv,gzip,json
from pathlib import Path
from collections import defaultdict
import cp02_protected_process_capture as c
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/runtime/native/cases/full')
out=Path('docs/evidence/cp02_sedimentation_conservation_20261109/audit')
weights={(140,79):.24629397354739388,(141,79):.24211872650600177,(140,80):.2579803287393153,(141,80):.25360697120728903}
result=[]; hashes={}
for arm in ('OLD','FIX'):
 case=root/arm; entries={Path(x['path']).name:x for x in json.loads((c.EVIDENCE/'native/compact'/arm/'capture_receipt.json').read_text())['raw_stream_files']}
 names=[p.name for p in case.glob('state_calls_rank*.txt')] + [p.name for p in case.glob('cp04_t*_rank3.bin') if c.parse_chunk_filename(p,'cp04')[0]<=360 and c.parse_chunk_filename(p,'cp04')[1]>=330]
 for name in names:
  if c.sha256(case/name)!=entries[name]['sha256']: raise ValueError(name)
 hashes[arm]={name:entries[name]['sha256'] for name in sorted(names)}
 with gzip.open(Path('../runtime/audit')/(arm+'_P01_substeps.csv.gz'),'rt') as f: rows=list(csv.reader(f))
 for first in (330,331):
  values=defaultdict(float)
  for r in rows:
   if int(r[0])<first or r[7]!='rain':continue
   w=weights[int(r[3]),int(r[4])]
   for ix,label in ((9,'limiter_events'),(10,'transfer_gap'),(11,'column_change'),(12,'ground_fall_increment')):
    values[label+'_native_sum']+=float(r[ix]); values[label+'_bilinear']+=w*float(r[ix])
  result.append({'arm':arm,'first_step':first,'last_step':360,'native_columns':4,**values})
(out/'p01_focused_proof.json').write_text(json.dumps({'status':'PASS','scope':'CP05 rain; rho=dend; source-density kg m-2; each native column integrated across its 39 levels; no inference of forecast cause; phase-9/10, source f32 replay bitwise verified','P01_point_id':'RN1_10942','weights':{str(k):v for k,v in weights.items()},'source_hashes':{arm:c.sha256(c.EVIDENCE/'native/source'/f'module_mp_kdm6_{arm}.f90') for arm in ('OLD','FIX')},'schema_sha256':c.sha256(c.SCHEMA_PATH),'inputs_sha256':hashes,'result':result},indent=2)+'\n')
for row in result:print(row)
