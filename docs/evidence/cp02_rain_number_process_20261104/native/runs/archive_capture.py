import gzip,hashlib,json,sys
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
out=R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/native/capture'
CHUNK=64*1024*1024
assert json.loads((R/'runtime/runs/history_byte_comparison.json').read_text())['status']=='PASS'

analysis=R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/analysis'
receipt=json.loads((analysis/'coverage_receipt.json').read_text())
assert receipt['status']=='PASS_FULL_CAPTURE' and receipt['steps']==540 and receipt['levels']==39 and receipt['native_cells']==36
assert receipt['schema_sha256']=='3427340bf76f9d4fb662f9891ae5029546c4bdc78d5a5c3e71ed49f03610d87f'
assert receipt['corners_sha256']=='aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b'
def file_sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
assert Path(receipt['input_manifest_path']) == analysis.parent/'input_manifest.json'
assert file_sha(Path(receipt['input_manifest_path']))==receipt['input_manifest_sha256']
for arm in ('B1','NR_PRIOR'):
 d=R/'runtime/runs'/arm
 actual={p.resolve() for pattern in ('cp03_rank*.bits','kdm6_trace_rank*.bits','state_selected_*.bin','state_calls_*.txt') for p in d.glob(pattern)}
 listed={Path(x['path']) for x in receipt['source_files'][arm]}
 assert actual==listed and actual
 for x in receipt['source_files'][arm]:
  path=Path(x['path']);assert path.stat().st_size==x['bytes'] and file_sha(path)==x['sha256']
out.mkdir(parents=True,exist_ok=True)

for arm in ('B1','NR_PRIOR'):
 d=R/'runtime/runs'/arm;dest=out/arm;dest.mkdir(exist_ok=False)
 files=sorted({p for pattern in ('cp03_rank*.bits','kdm6_trace_rank*.bits','state_selected_*.bin','state_calls_*.txt') for p in d.glob(pattern)})
 assert files
 manifest=[]
 for path in files:
  h=hashlib.sha256();parts=[]
  with path.open('rb') as inp:
   index=0
   while True:
    block=inp.read(CHUNK)
    if not block:break
    h.update(block);part=dest/(path.name+f'.part{index:04}.gz')
    with part.open('xb') as f:
     with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0,compresslevel=6) as g:g.write(block)
    blob=part.read_bytes();assert len(blob)<100*1024*1024
    assert gzip.decompress(blob)==block
    parts.append({'name':part.name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'raw_bytes':len(block),'raw_sha256':hashlib.sha256(block).hexdigest()})
    index+=1
  manifest.append({'name':path.name,'bytes':path.stat().st_size,'sha256':h.hexdigest(),'chunks':parts})
  print(arm,path.name,flush=True)
 (dest/'manifest.json').write_text(json.dumps({'files':manifest,'chunk_raw_limit':CHUNK,'gzip_max_bytes':100*1024*1024,'source':str(d)},indent=2)+'\n')
