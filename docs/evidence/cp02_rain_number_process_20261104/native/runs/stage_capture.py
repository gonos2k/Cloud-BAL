import concurrent.futures,gzip,hashlib,json
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
manifest_path=R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/input_manifest.json'
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()=='f0c6441c9679a66ebc678e0a2d2ffd5853bfae9b10f94add6d34ce4034fd18e7'
assert json.loads((R/'runtime/runs/history_byte_comparison.json').read_text())['status']=='PASS'
input_manifest=json.loads(manifest_path.read_text()); out=R/'runtime/capture_staging';out.mkdir(exist_ok=False)
CHUNK=64*1024*1024
tasks=[]
for arm in ('B1','NR_PRIOR'):
 d=out/arm;d.mkdir();item=input_manifest['arms'][arm];root=Path(item['root']);expected=item['files']
 actual={p.name for pattern in ('cp03_rank*.bits','kdm6_trace_rank*.bits','state_selected_*.bin','state_calls_*.txt') for p in root.glob(pattern)};assert actual==set(expected)
 for name,sha in sorted(expected.items()):tasks.append((arm,root/name,d,sha))
def process(task):
 arm,path,d,expected=task;h=hashlib.sha256();parts=[];size=0
 with path.open('rb') as f:
  index=0
  while True:
   block=f.read(CHUNK)
   if not block:break
   size+=len(block);h.update(block);part=d/(path.name+f'.part{index:04}.gz')
   with part.open('xb') as fp:
    with gzip.GzipFile(filename='',mode='wb',fileobj=fp,mtime=0,compresslevel=6) as g:g.write(block)
   blob=part.read_bytes();assert len(blob)<100*1024*1024 and gzip.decompress(blob)==block
   parts.append({'name':part.name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'raw_bytes':len(block),'raw_sha256':hashlib.sha256(block).hexdigest()});index+=1
 assert h.hexdigest()==expected and size==path.stat().st_size
 print(arm,path.name,size,flush=True)
 return arm,{'name':path.name,'bytes':size,'sha256':expected,'chunks':parts}
res={'B1':[],'NR_PRIOR':[]}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for arm,item in pool.map(process,tasks):res[arm].append(item)
for arm in res:
 (out/arm/'manifest.json').write_text(json.dumps({'files':res[arm],'chunk_raw_limit':CHUNK,'gzip_max_bytes':100*1024*1024,'source':input_manifest['arms'][arm]['root']},indent=2)+'\n')
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()=='f0c6441c9679a66ebc678e0a2d2ffd5853bfae9b10f94add6d34ce4034fd18e7'
total=sum(x['bytes'] for a in res.values() for item in a for x in item['chunks']);(out/'staging_receipt.json').write_text(json.dumps({'status':'STAGED_NOT_PUBLISHED','input_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'total_compressed_bytes':total},indent=2)+'\n');print('STAGED_NOT_PUBLISHED',total,flush=True)
