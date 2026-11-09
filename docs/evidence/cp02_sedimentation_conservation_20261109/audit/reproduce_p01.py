import csv, gzip, json
from collections import defaultdict
from pathlib import Path
import cp02_protected_process_capture as c
import cp02_sedimentation_conservation as a
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/runtime/native/cases/full')
s,co,_=c.load_contract(); counts={int(k):len(v['fields']) for k,v in s['phases'].items()}; cells={(140,79),(141,79),(140,80),(141,80)}
for arm in ('OLD','FIX'):
 case=root/arm; inv=c.read_call_inventory(sorted(case.glob('state_calls_rank*.txt')),co.cells); raw={Path(x['path']).name:x for x in json.loads((c.EVIDENCE/'native/compact'/arm/'capture_receipt.json').read_text())['raw_stream_files']}; totals=defaultdict(lambda:defaultdict(float)); seen=set()
 with gzip.open(Path('../runtime/audit')/(arm+'_P01_substeps.csv.gz'),'wt',newline='') as f, gzip.open(Path('../runtime/audit')/(arm+'_P01_events.csv.gz'),'wt',newline='') as e:
  writer,events=csv.writer(f),csv.writer(e)
  for p in sorted(case.glob('cp04_t*_rank3.bin')):
   first,last,rank=c.parse_chunk_filename(p,'cp04')
   if last<330 or first>360: continue
   if c.sha256(p)!=raw[p.name]['sha256']:raise ValueError('hash mismatch')
   for frame, records in c.iter_process_frames(p,counts,rank):
    if frame.timestep not in range(330,361) or frame.j not in (79,80): continue
    matched=cells.intersection(c._frame_selected_cells(frame,co.cells))
    if not matched: continue
    for cell in matched:
     if (frame.timestep,cell) in seen: raise ValueError('duplicate')
     seen.add((frame.timestep,cell))
    a.audit_frame(frame,records,co,inv,writer,events,totals,cells)
 if len(seen)!=124:raise ValueError(f'missing P01 columns {len(seen)}')
 print(arm, 'covered',len(seen),'summary',json.dumps(totals),flush=True)
