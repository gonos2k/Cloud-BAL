import hashlib,json,os
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
e=R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104';stage=R/'runtime/capture_staging';destination=e/'native/capture';coverage=json.loads((e/'analysis/coverage_receipt.json').read_text());receipt=json.loads((stage/'staging_receipt.json').read_text());source=e/'input_manifest.json'
assert coverage['status']=='PASS_FULL_CAPTURE' and coverage['steps']==540 and coverage['levels']==39 and coverage['native_cells']==36
assert coverage['schema_sha256']=='3427340bf76f9d4fb662f9891ae5029546c4bdc78d5a5c3e71ed49f03610d87f'
assert coverage['corners_sha256']=='aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b'
assert Path(coverage['input_manifest_path'])==source and hashlib.sha256(source.read_bytes()).hexdigest()==coverage['input_manifest_sha256']==receipt['input_manifest_sha256']
assert receipt['status']=='STAGED_NOT_PUBLISHED'
assert receipt['total_compressed_bytes']<1500000000, 'report size to root before publishing above threshold'
assert not destination.exists()
for arm in ('B1','NR_PRIOR'):
 files=json.loads((stage/arm/'manifest.json').read_text())['files'];covered={Path(x['path']).name:(x['sha256'],x['bytes']) for x in coverage['source_files'][arm]}
 assert {x['name']:(x['sha256'],x['bytes']) for x in files}==covered
 for x in files:
  for c in x['chunks']:
   data=(stage/arm/c['name']).read_bytes();assert len(data)==c['bytes'] and len(data)<100*1024*1024 and hashlib.sha256(data).hexdigest()==c['sha256']
os.rename(stage,destination)
print('PUBLISHED',receipt['total_compressed_bytes'])
