import gzip,hashlib,json
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
root=R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/native/capture'
result={}
for arm in ('B1','NR_PRIOR'):
 d=root/arm; manifest=json.loads((d/'manifest.json').read_text());entries=[]
 for f in manifest['files']:
  h=hashlib.sha256();total=0
  for part in f['chunks']:
   p=d/part['name'];blob=p.read_bytes();assert len(blob)==part['bytes'] and len(blob)<100*1024*1024 and hashlib.sha256(blob).hexdigest()==part['sha256']
   raw=gzip.decompress(blob);assert len(raw)==part['raw_bytes'] and hashlib.sha256(raw).hexdigest()==part['raw_sha256'];h.update(raw);total+=len(raw)
  assert total==f['bytes'] and h.hexdigest()==f['sha256'];entries.append({'name':f['name'],'bytes':total,'sha256':h.hexdigest()})
 result[arm]=entries
(root/'verification.json').write_text(json.dumps({'status':'PASS','files':result,'scope':'decompress every independent gzip chunk; validate chunk sizes and compressed/raw SHA-256 and reconstruct each complete original byte hash'},indent=2)+'\n')
print('PASS',sum(map(len,result.values())))
