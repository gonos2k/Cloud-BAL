import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FULL=ROOT/'full'
FREEZE=FULL/'reference_history_freeze.json'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

assert sha(FREEZE)=='11a7e70b43a25ef4476f15757cb0956ddc4ef18d010e3c72b74c43e1390d8c32'
source_freeze=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_thermo_cloud_path_20261105/Cloud-BAL/docs/evidence/cp02_thermo_cloud_path_20261105/native/source/source_freeze.json')
assert sha(source_freeze)=='3548e4d01e0291c9b8811ac7fd9cbede16d54a693648bd45ff4edffc5e87f62d'
assert all(sha(Path(path))==value for path,value in json.loads(source_freeze.read_text())['sha256'].items())
freeze=json.loads(FREEZE.read_text());result={'status':'PASS','source_freeze_sha256':sha(source_freeze),'source_pins_unchanged':True,'reference_history_freeze_sha256':sha(FREEZE),'arms':{}}
inputs={}
for arm in ('B1','DM065'):
 ref=freeze[arm]; assert sha(Path(ref['receipt']))==ref['receipt_sha256']
 p=FULL/arm/'launch_receipt.json';d=json.loads(p.read_text());assert d['status']=='PASS' and d['history_byte_parity'] and d['inputs_unchanged']
 assert len(d['inputs_after'])==89
 assert {n:x['actual_sha256'] for n,x in d['history_comparisons'].items()}==ref['history_sha256']
 assert {n:x['reference_sha256'] for n,x in d['history_comparisons'].items()}==ref['history_sha256']
 assert all(sha(FULL/arm/n)==v for n,v in d['inputs_after'].items())
 inputs[arm]=d['inputs_after'];result['arms'][arm]={'launch_receipt_path':str(p),'launch_receipt_sha256':sha(p),'history_comparisons':d['history_comparisons'],'input_count':89}
assert inputs['B1'].keys()==inputs['DM065'].keys()
assert [n for n in inputs['B1'] if inputs['B1'][n]!=inputs['DM065'][n]]==['wrfinput_d01']
assert inputs['B1']['wrfinput_d01']=='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
assert inputs['DM065']['wrfinput_d01']=='e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175'
result['common_input_count']=88;result['common_input_sha256']={k:v for k,v in inputs['B1'].items() if k!='wrfinput_d01'}
(FULL/'history_parity_gate.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS',sha(FULL/'history_parity_gate.json'))
