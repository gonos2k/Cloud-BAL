#!/usr/bin/env python3
"""PR110 scoped KG publisher. Check-only is read-only; writes require exact root GO."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50'); MAINT=ROOT/'Cloud-BAL'
SOURCE=Path('/var/tmp/cloudbal-pr111'); BASE='e381c88ebcc14ecc5f100e7a74d571752dee0789'; COMMIT='3c0deb764a5b6624ba185c1da5d431867d1f95b2'
DATE='2026-10-27'; SNAPSHOT=f'{DATE}-pr111-static-value-validation'; RAW=f'{SNAPSHOT}-graphify-raw'
STAGE=Path('/var/tmp/pr111_kg_stage_20261027'); BASELINE=Path('/var/tmp/pr111_kg_baseline_20261027.json')
OUT=Path('/var/tmp/pr111_kg_publication_20261027'); WIKI=('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')
GRAPH_FILES=('graph.json','GRAPH_REPORT.md','manifest.json','.graphify_analysis.json','.graphify_labels.json','.graphify_labels.json.sig')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def require(x,m):
 if not x:raise RuntimeError(m)
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);require(s is not None and s.loader is not None,f'cannot load helper {path}');m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def status(root):return subprocess.check_output(['git','-C',str(root),'status','--short'],text=True).splitlines()
def snapshot_inventory():
 d={}
 for root in (ROOT,MAINT):
  for f in sorted((root/'graphify-out').iterdir()):
   if f.is_dir() and f.name[:4].isdigit():d[str(f)]={p.name:{'sha256':sha(p)} for p in sorted(f.iterdir()) if p.is_file()}
 return d
def stage_inventory():
 d={}
 for label in ('KLAPS50','Cloud-BAL'):
  gd=STAGE/'staging'/label/'graphify-out'; files={};dated={}
  for p in sorted(gd.iterdir()):
   if p.is_dir():dated[p.name]={q.name:{'sha256':sha(q)} for q in sorted(p.iterdir()) if q.is_file()}
   elif p.is_file():files[p.name]=sha(p)
  d[label]={'graphify_files':files,'dated_directories':dated}
 d['wiki']={n:sha(STAGE/'staging/KLAPS50/wiki'/n) for n in WIKI};return d
def verify_protected_content(plan):
 helper=SOURCE/'docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py'
 legacy=load('pr111_kg_legacy_preflight',helper); legacy.SOURCE=SOURCE; legacy.ROOT=ROOT; legacy.MAINT=MAINT; legacy.HELPER=ROOT/'scratch/pr98_native_effect_20261022/Cloud-BAL/docs/evidence/pr98_native_effect_20261022/kg/update_kg.py'; guard=legacy._load_pinned_helper()
 require(sha(Path(guard.GUARD))==guard.GUARD_SHA,'host guard helper pin drift')
 host=load('pr111_kg_host_guard',guard.GUARD)
 engine_path=Path(plan['pinned_helpers']['pr98_engine']['path'])
 require(sha(engine_path)==plan['pinned_helpers']['pr98_engine']['sha256'],'pinned PR98 engine drift')
 engine=load('pr111_kg_pr98_engine',engine_path)
 require(engine.snapshot_identity(host.maintained_source_snapshot())==plan['maintained_source_snapshot'],'maintained source inventory/pins changed')
 _,protected,_=engine.load_previous_helpers()
 require(protected.protected_content(host)==plan['protected_content_sha256'],'protected wiki/schema/profile inventory changed')
def check_state(receipt,baseline):
 plan=receipt['plan'];require(subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==COMMIT,'source commit mismatch')
 require(not status(SOURCE),'source worktree must remain clean')
 require(subprocess.check_output(['git','-C',str(SOURCE),'merge-base',BASE,COMMIT],text=True).strip()==BASE,'source graph-selection base mismatch')
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  b=baseline['corpora'][label];g=json.loads((root/'graphify-out/graph.json').read_text())
  require(sha(root/'graphify-out/graph.json')==b['graph_sha256'],'maintained graph changed: '+label)
  require((len(g['nodes']),len(g['links']))==(b['nodes'],b['edges']),'maintained graph count changed: '+label)
  files={p.name:sha(p) for p in sorted((root/'graphify-out').iterdir()) if p.is_file()}
  require(files==b['top_level_files'],'maintained graph artifacts/metadata changed: '+label)
  require(status(root)==baseline['maintained_git_status'][label],'maintained checkout dirty status changed: '+label)
 for n,h in baseline['wiki'].items():require(sha(ROOT/'wiki'/n)==h,'maintained wiki changed: '+n)
 expected={}
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  for folder,members in baseline['corpora'][label]['dated_snapshots'].items():expected[str(root/'graphify-out'/folder)]={n:{'sha256':h} for n,h in members.items()}
 require(snapshot_inventory()==expected and len(expected)==144,'maintained dated snapshot inventory changed')
 for n,h in plan['selected_source_sha256'].items():require(sha(SOURCE/n)==h,'selected source changed: '+n)
 for n,h in plan['hash_only_sha256'].items():require(sha(SOURCE/n)==h,'hash-only source changed: '+n)
 verify_protected_content(plan)
def build_targets(receipt):
 targets=[]
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  go=STAGE/'staging'/label/'graphify-out'
  for dest,srcname in ((RAW,DATE),(SNAPSHOT,SNAPSHOT)):
   src=go/srcname;dst=root/'graphify-out'/dest;require(src.is_dir() and not dst.exists(),'snapshot source missing/target exists: '+str(dst))
   targets.append({'kind':'directory','source':str(src),'destination':str(dst),'files':{p.name:sha(p) for p in sorted(src.iterdir()) if p.is_file()}})
  for name in GRAPH_FILES:
   src=go/name
   if src.is_file():targets.append({'kind':'file','source':str(src),'destination':str(root/'graphify-out'/name),'sha256':sha(src)})
 for name in WIKI:
  src=STAGE/'staging/KLAPS50/wiki'/name;targets.append({'kind':'file','source':str(src),'destination':str(ROOT/'wiki'/name),'sha256':sha(src)})
 return targets
def atomic_file(src,dst):
 tmp=dst.with_name(dst.name+'.pr111-tmp');require(not tmp.exists(),'temporary target already exists: '+str(tmp))
 try:
  shutil.copy2(src,tmp)
  with tmp.open('rb') as f:os.fsync(f.fileno())
  os.replace(tmp,dst)
 finally:
  if tmp.exists():tmp.unlink()
def apply_targets(targets):
 backup=OUT/'backups';require(not backup.exists(),'publication backup directory already exists');backup.mkdir(parents=True)
 old_files=[];new_dirs=[]
 for i,t in enumerate(targets):
  dst=Path(t['destination'])
  if t['kind']=='file':
   b=backup/f'{i:03d}_{dst.name}';shutil.copy2(dst,b);old_files.append((b,dst))
 try:
  for i,t in enumerate(targets):
   src=Path(t['source']);dst=Path(t['destination'])
   if t['kind']=='file':atomic_file(src,dst)
   else:
    tmp=dst.with_name(dst.name+'.pr111-tmp');require(not tmp.exists(),'temporary snapshot exists: '+str(tmp));shutil.copytree(src,tmp);os.replace(tmp,dst);new_dirs.append(dst)
  for t in targets:
   dst=Path(t['destination']); expected=t.get('sha256')
   if expected:require(sha(dst)==expected,'published file hash mismatch: '+str(dst))
   else:require({p.name:sha(p) for p in sorted(dst.iterdir()) if p.is_file()}==t['files'],'published snapshot mismatch: '+str(dst))
 except Exception:
  for d in reversed(new_dirs):shutil.rmtree(d)
  for b,dst in reversed(old_files):atomic_file(b,dst)
  raise

def main():
 ap=argparse.ArgumentParser();m=ap.add_mutually_exclusive_group(required=True);m.add_argument('--check-only',action='store_true');m.add_argument('--apply',action='store_true');ap.add_argument('--root-go',type=Path)
 a=ap.parse_args();require((a.root_go is not None)==a.apply,'--apply requires --root-go; check-only forbids it')
 rp=STAGE/'stage_receipt.json';require(rp.is_file(),'stage receipt missing');receipt=json.loads(rp.read_text());stage_sha=receipt['stage_sha256'];copy=dict(receipt);copy.pop('stage_sha256');require(canon(copy)==stage_sha,'stage receipt fingerprint mismatch')
 plan=receipt['plan'];fp=plan['plan_sha256'];p=dict(plan);p.pop('plan_sha256');require(canon(p)==fp,'plan fingerprint mismatch')
 baseline=json.loads(BASELINE.read_text());require(receipt['preserved_baseline_manifest_sha256']==sha(BASELINE),'captured baseline manifest hash drift')
 require(stage_inventory()==receipt['stage_inventory'],'staged output differs from stage receipt inventory')
 check_state(receipt,baseline);targets=build_targets(receipt)
 require(len(targets)==21,'publisher target count changed')
 if a.apply:
  go=json.loads(a.root_go.read_text());require(go.get('decision')=='GO' and go.get('source_commit')==COMMIT and go.get('stage_sha256')==stage_sha and go.get('plan_sha256')==fp and go.get('automatic_snapshot_date')==DATE and isinstance(go.get('reviewed_by'),str) and go['reviewed_by'].strip(),'root GO does not bind exact source/stage/plan/date')
  apply_targets(targets)
  print(json.dumps({'status':'APPLY_PASS','source_commit':COMMIT,'stage_sha256':stage_sha,'plan_sha256':fp,'published_targets':len(targets),'writes_performed':True},indent=2));return
 OUT.mkdir(exist_ok=True)
 publish={'schema':'pr111_kg_publish_plan_v1','status':'CHECK_ONLY_PASS_NO_WRITES','source_commit':COMMIT,'approval_base':BASE,'graph_selection_base':BASE,'stage_sha256':stage_sha,'plan_sha256':fp,'baseline_manifest_sha256':sha(BASELINE),'dated_snapshot_count_before':144,'dated_snapshot_count_after':148,'raw_snapshot':RAW,'named_snapshot':SNAPSHOT,'targets':targets,'root_go_required':{'decision':'GO','source_commit':COMMIT,'stage_sha256':stage_sha,'plan_sha256':fp,'automatic_snapshot_date':DATE,'reviewed_by':'root review required'},'writes_performed':False}
 (OUT/'publish_plan.json').write_text(json.dumps(publish,indent=2,sort_keys=True)+'\n')
 go={**publish['root_go_required'],'decision':'PENDING','reviewed_by':''};(OUT/'root_go.template.json').write_text(json.dumps(go,indent=2,sort_keys=True)+'\n')
 check={'status':'CHECK_ONLY_PASS_NO_WRITES','source_commit':COMMIT,'stage_sha256':stage_sha,'plan_sha256':fp,'baseline_dated_snapshot_count':144,'expected_after':148,'targets':len(targets),'source_clean':True,'maintained_state_match':True,'staged_inventory_match':True,'protected_content_and_pins_match':True,'writes_performed':False}
 (OUT/'check_only.json').write_text(json.dumps(check,indent=2,sort_keys=True)+'\n');print(json.dumps(check,indent=2))
if __name__=='__main__':main()
