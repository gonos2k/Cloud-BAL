#!/usr/bin/env python3
"""Validate saved debugger words against nine extracted history words, without NetCDF."""
import argparse,csv,hashlib,json,struct
from pathlib import Path

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--replayed',type=Path,required=True);p.add_argument('--inputsreceipt',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 records=[json.loads(line) for line in a.capture.read_text().splitlines()]; expected=['kdm_entry','kdm_return','zero_b_entry','zero_b_return','zero_a_entry','zero_a_return']; events=[r['event'] for r in records]; selected={tuple(row['cell']):row for row in json.loads(a.baseline.read_text())['cells']};replay={tuple(row['cell']):row for row in json.loads(a.replayed.read_text())['cells']}
 checks={'exact_six_event_sequence':events==expected,'nine_cells_baseline_and_replay':len(selected)==len(replay)==9 and selected.keys()==replay.keys(),'nine_matching_rows_per_event':all(len(r.get('rows',[]))==9 and {tuple(x['cell']) for x in r['rows']}==selected.keys() for r in records) and len(records)==6,'word_encodings_valid':all(struct.pack('<f',v[k]).hex()==v[k+'_le'] for r in records for v in r.get('rows',[]) for k in ('qi','ni'))}
 byevent={r['event']:{tuple(x['cell']):x for x in r.get('rows',[])} for r in records};continuity={}
 for x,y in [('kdm_return','zero_b_entry'),('zero_b_return','zero_a_entry')]:
  continuity[x+'_to_'+y]=all(c in byevent.get(x,{}) and c in byevent.get(y,{}) and all(byevent[x][c][f+'_le']==byevent[y][c][f+'_le'] for f in ('qi','ni')) for c in selected)
 checks.update(continuity)
 for field in ('qi','ni'):
  checks['zero_a_return_'+field+'_equals_replayed_history']=all(c in byevent.get('zero_a_return',{}) and byevent['zero_a_return'][c][field+'_le']==replay[c][field+'_le'] for c in selected)
  checks['baseline_equals_replayed_history_'+field]=all(selected[c][field+'_le']==replay[c][field+'_le'] for c in selected)
 with (a.out/'boundary_values.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['i','j','k','event','qi','ni','qi_hex_le','ni_hex_le'])
  for r in records:
   for x in r.get('rows',[]):w.writerow([*x['cell'],r['event'],x['qi'],x['ni'],x['qi_le'],x['ni_le']])
  for label,table in [('baseline_history',selected),('replayed_history',replay)]:
   for cell,x in table.items():w.writerow([*cell,label,x['qi'],x['ni'],x['qi_le'],x['ni_le']])
 result={'status':'PASS' if all(checks.values()) else 'INCOMPLETE_OR_MISMATCH','checks':checks,'events':events,'file_sha256':{x:sha(getattr(a,x)) for x in ('capture','baseline','replayed','inputsreceipt')},'scope':'Offline validation of 54 recorded event-cell words plus 18 saved history-cell pairs; it does not independently read or hash NetCDF inputs or outputs.'}
 (a.out/'offline_word_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
