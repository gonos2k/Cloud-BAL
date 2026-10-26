#!/usr/bin/env python3
"""PR108 external staged KG publisher. Check-only by default; publication requires exact root GO."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, uuid
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT=ROOT/'Cloud-BAL'
SOURCE=ROOT/'scratch/pr108_input_execution_20261026/Cloud-BAL'
STAGE=Path('/var/tmp/pr108_kg_stage_20261026')
RECEIPT=STAGE/'stage_receipt.json'
PRIOR=SOURCE/'docs/evidence/pr105_observation_pairing_20261026/kg/publication/kg_receipt.json'
PRIOR_SHA='34e96032623e8a58d3717941d910efbc50eedd712851f894e9775f69537187fc'
OUT=Path('/var/tmp/pr108_kg_publication_20261026')
RAW_SUFFIX='pr108-graphify-raw'
WIKI=('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')
PR107_PUB=Path('/var/tmp/pr107_kg_publication_20261026/publish_receipt.json')
PR107_PUB_SHA='35603e219745640dc2c520198db9cb3e8446e26d48ac3ca4de18b9977f943c3e'
PR107_STAGE=Path('/var/tmp/pr107_kg_stage_20261026_v2')
PR107_STAGE_SHA='2b28ee23e0d1d190b6b940dd0e0d69d395d443c5ee55fa49280d749851cb639d'

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def canon_hash(x)->str:return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path); assert s and s.loader
 m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def load_context(plan):
 helpers=plan['pinned_helpers']; engine_path=Path(helpers['pr98_engine']['path'])
 require(sha(engine_path)==helpers['pr98_engine']['sha256'],'pinned PR98 guard engine changed')
 helper_dir=SOURCE/'docs/evidence/pr105_observation_pairing_20261026/kg'
 sys.path.insert(0,str(helper_dir))
 pre=load('pr108_publish_preflight',helper_dir/'preflight_kg.py')
 apply=load('pr108_publish_apply',helper_dir/'apply_kg.py')
 pre.SOURCE=SOURCE;pre.ROOT=ROOT;pre.MAINT=MAINT;pre.PRIOR=PRIOR;pre.PRIOR_SHA=PRIOR_SHA;pre.EXPECTED_SNAPSHOTS=132
 engine=load('pr108_publish_engine',engine_path)
 return pre,apply,engine

def expected_live_inventory(prior):
 expected=dict(prior['dated_snapshot_baseline'])
 expected.update({folder:{n:{'sha256':r['sha256']} for n,r in rows.items()}
                  for folder,rows in prior['post_apply_snapshot_additions'].items()})
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  for staged_name,published_name in (('2026-10-26','2026-10-26-pr107-graphify-raw'),
                                      ('2026-10-26-pr107-t39-capture','2026-10-26-pr107-t39-capture')):
   staged=PR107_STAGE/'staging'/label/'graphify-out'/staged_name
   require(staged.is_dir(),f'PR107 staged snapshot unavailable: {staged}')
   expected[str(root/'graphify-out'/published_name)]={p.name:{'sha256':sha(p)}
       for p in sorted(staged.iterdir()) if p.is_file()}
 return expected

def verify_live(plan,pre,apply,engine):
 require(PRIOR.is_file() and sha(PRIOR)==PRIOR_SHA,'PR105 receipt hash drift')
 prior=json.loads(PRIOR.read_text()); require(prior['status']=='PASS','PR105 receipt not PASS')
 require(prior['post_apply_dated_snapshot_count']==128,'PR105 receipt snapshot count mismatch')
 require(PR107_PUB.is_file() and sha(PR107_PUB)==PR107_PUB_SHA,'PR107 publication receipt hash drift')
 pub=json.loads(PR107_PUB.read_text())
 require(pub.get('status')=='PASS' and pub.get('stage_sha256')==PR107_STAGE_SHA and
         pub.get('dated_snapshot_count_after')==132,'PR107 published baseline receipt mismatch')
 stage_receipt=json.loads((PR107_STAGE/'stage_receipt.json').read_text())
 require(stage_receipt.get('stage_sha256')==PR107_STAGE_SHA,'PR107 stage receipt fingerprint mismatch')
 expected=expected_live_inventory(prior)
 actual=pre.current_snapshot_inventory((ROOT,MAINT),expected_count=132)
 require(actual==expected,'maintained 132-folder snapshot inventory differs from PR107 receipt lineage')
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  require(sha(root/'graphify-out/graph.json')==pub['corpora'][label]['sha256'],f'{label} maintained graph drift')
  receipted={Path(p).name:h for p,h in pub['published_graph_files'].items()
             if p.startswith(str(root/'graphify-out')+'/')}
  require(receipted==plan['baseline_graph_artifacts'][label],
          f'{label} stage graph artifacts differ from the PR107 receipt')
  expected_files={**receipted,**plan['baseline_graphify_metadata'][label]}
  current={}
  for p in (root/'graphify-out').iterdir():
   if p.is_dir():continue
   require(p.is_file() and not p.is_symlink(),f'unsupported maintained graph file {p}')
   current[p.name]=sha(p)
  require(current==expected_files,f'{label} maintained graph artifacts/metadata drift')
 for name in WIKI:
  require(sha(ROOT/'wiki'/name)==pub['wiki_sha256'][f'wiki/{name}'],f'maintained wiki baseline drift: {name}')
 staged_log=(STAGE/'staging/KLAPS50/wiki/log.md').read_bytes()
 current_log=(ROOT/'wiki/log.md').read_bytes()
 require(staged_log.startswith(current_log), 'staged wiki log does not preserve exact current log prefix')
 require(b'PR108 input execution contracts' in staged_log[len(current_log):], 'staged wiki log lacks PR108 audit append')
 require(plan['source_commit']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
         'source commit changed since staging')
 require(not subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip(),
         'source checkout is no longer clean')
 for name,h in plan['selected_source_sha256'].items():require(sha(SOURCE/name)==h,f'selected source changed: {name}')
 for name,h in plan['hash_only_sha256'].items():require(sha(SOURCE/name)==h,f'hash-only source changed: {name}')
 require(pre.active250_root_go_snapshot()==plan['active250_root_go_snapshot'],'active250 ROOTGO/pins changed')
 pins=engine.immutable_pin_snapshot(prior);require(len(pins)==197,'inherited immutable pin count mismatch')
 legacy=load('pr108_publish_legacy_preflight',SOURCE/'docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py')
 guard_engine=legacy._load_pinned_helper();require(sha(guard_engine.GUARD)==guard_engine.GUARD_SHA,'host guard pin drift')
 host=load('pr108_publish_host_guard',guard_engine.GUARD)
 require(engine.snapshot_identity(host.maintained_source_snapshot())==prior['maintained_source_snapshot_after'],'maintained-source inventory drift')
 _,protected,_=engine.load_previous_helpers()
 require(protected.protected_content(host)==prior['protected_content_sha256'],'protected wiki/profile content drift')
 stage_inventory=apply.stage_inventory(STAGE/'staging/KLAPS50',STAGE/'staging/Cloud-BAL')
 require(stage_inventory==json.loads(RECEIPT.read_text())['stage_inventory'],'staged inventory changed after review')
 return prior,stage_inventory

def verify_post(plan,prior,pre,engine,targets,stage_roots,raw_date,raw_name,snapshot):
 # The source and protected content guards remain valid after the graph and wiki write.
 require(plan['source_commit']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
         'source commit changed during publication')
 require(not subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip(),
         'source checkout changed during publication')
 for name,h in plan['selected_source_sha256'].items():require(sha(SOURCE/name)==h,f'selected source changed: {name}')
 for name,h in plan['hash_only_sha256'].items():require(sha(SOURCE/name)==h,f'hash-only evidence changed: {name}')
 require(pre.active250_root_go_snapshot()==plan['active250_root_go_snapshot'],'active250 ROOTGO/pins changed')
 pins=engine.immutable_pin_snapshot(prior);require(len(pins)==197,'inherited immutable pin count mismatch')
 legacy=load('pr108_publish_legacy_postflight',SOURCE/'docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py')
 guard_engine=legacy._load_pinned_helper();require(sha(guard_engine.GUARD)==guard_engine.GUARD_SHA,'host guard pin drift')
 host=load('pr108_publish_host_post_guard',guard_engine.GUARD)
 require(engine.snapshot_identity(host.maintained_source_snapshot())==prior['maintained_source_snapshot_after'],'maintained-source inventory drift')
 _,protected,_=engine.load_previous_helpers()
 require(protected.protected_content(host)==prior['protected_content_sha256'],'protected wiki/profile content drift')
 expected=expected_live_inventory(prior)
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  staged_graph=stage_roots[label]/'graphify-out'
  for src_name,dst_name in ((raw_date,raw_name),(snapshot,snapshot)):
   src=staged_graph/src_name
   expected[str(root/'graphify-out'/dst_name)]={p.name:{'sha256':sha(p)} for p in sorted(src.iterdir()) if p.is_file()}
 actual=pre.current_snapshot_inventory((ROOT,MAINT),expected_count=136)
 require(actual==expected,'post-apply 136-folder snapshot inventory differs from exact staged additions')
 for src,dst in targets:require(sha(src)==sha(dst),f'published file readback mismatch: {dst}')
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  for name in (f'{raw_date}-pr108-graphify-raw',snapshot):
   src=stage_roots[label]/'graphify-out'/('2026-10-26' if name.endswith('graphify-raw') else name)
   dst=root/'graphify-out'/name
   require({p.name:sha(p) for p in src.iterdir() if p.is_file()}=={p.name:sha(p) for p in dst.iterdir() if p.is_file()},
           f'snapshot readback mismatch: {dst}')
 staged_wiki=STAGE/'staging/KLAPS50/wiki'
 for name in WIKI:require(sha(staged_wiki/name)==sha(ROOT/'wiki'/name),f'published wiki readback mismatch: {name}')

def verify_stage():
 require(RECEIPT.is_file() and not RECEIPT.is_symlink(),'stage receipt missing')
 d=json.loads(RECEIPT.read_text()); stage_sha=d.pop('stage_sha256')
 require(canon_hash(d)==stage_sha,'stage receipt hash mismatch')
 plan=d['plan']; fingerprint=plan.get('plan_sha256'); pcopy=dict(plan); pcopy.pop('plan_sha256',None)
 require(canon_hash(pcopy)==fingerprint,'plan fingerprint mismatch')
 return d,stage_sha

def main():
 ap=argparse.ArgumentParser(); mode=ap.add_mutually_exclusive_group(required=True)
 mode.add_argument('--check-only',action='store_true');mode.add_argument('--apply',action='store_true')
 ap.add_argument('--root-go',type=Path);ap.add_argument('--stage-sha256');args=ap.parse_args()
 receipt,stage_sha=verify_stage();plan=receipt['plan'];pre,apply,engine=load_context(plan)
 require(args.stage_sha256==stage_sha,'caller stage hash does not match reviewed receipt')
 prior,inventory=verify_live(plan,pre,apply,engine)
 if args.check_only:
  print(json.dumps({'status':'CHECK_ONLY_PASS_NO_WRITES','stage_sha256':stage_sha,'plan_sha256':plan['plan_sha256'],
   'source_commit':plan['source_commit'],'approval_base':plan['approval_base'],'graph_selection_base':plan['graph_selection_base'],
   'dated_snapshot_count_before':132,'dated_snapshot_count_after':136,'selected_paths':plan['selected_graph_paths'],
   'hash_only_paths':plan['hash_only_paths'],'corpora':receipt['build']['corpora'],'runtime':{
    'PR106_HAN_3600':'INCOMPLETE at 760 s / 38 steps','PR107_T39':'pending; no closed result in pinned launch record'},
   'active250_pin_count':plan['active250_root_go_snapshot']['source_pin_count'],'writes_performed':False},indent=2));return
 require(args.root_go and args.root_go.is_file() and not args.root_go.is_symlink(),'apply requires a regular root GO JSON')
 go=json.loads(args.root_go.read_text())
 require(go.get('decision')=='GO' and go.get('stage_sha256')==stage_sha and go.get('plan_sha256')==plan['plan_sha256'] and
         go.get('source_commit')==plan['source_commit'] and isinstance(go.get('reviewed_by'),str) and go['reviewed_by'].strip(),
         'root GO does not bind this exact plan, stage, and source commit')
 require(not OUT.exists(),'refuse existing publication backup/output directory')
 graph_files=tuple(plan['pinned_helpers']['graph_artifact_names'])
 raw_date=plan['automatic_snapshot_date']; snapshot=plan['snapshot_name'] if 'snapshot_name' in plan else '2026-10-26-pr108-input-execution'
 require(snapshot=='2026-10-26-pr108-input-execution','unexpected named snapshot')
 raw_name=f'{raw_date}-{RAW_SUFFIX}'
 stage_roots={'KLAPS50':STAGE/'staging/KLAPS50','Cloud-BAL':STAGE/'staging/Cloud-BAL'}
 targets=[]; new_dirs=[]
 for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
  src=stage_roots[label]/'graphify-out'; dst=root/'graphify-out'
  for name in graph_files:
   candidate=src/name
   if candidate.exists(): targets.append((candidate,dst/name))
  raw_src=src/raw_date; named_src=src/snapshot
  require(raw_src.is_dir() and named_src.is_dir(),f'missing staged snapshots for {label}')
  raw_dst=dst/raw_name; named_dst=dst/snapshot
  require(not raw_dst.exists() and not named_dst.exists(),f'PR108 snapshot target already exists for {label}')
  new_dirs.extend(((raw_src,raw_dst),(named_src,named_dst)))
 for name in WIKI:
  targets.append((STAGE/'staging/KLAPS50/wiki'/name,ROOT/'wiki'/name))
 require(all(src.is_file() and not src.is_symlink() for src,dst in targets),'missing/symlinked staged publication file')
 OUT.mkdir(parents=True,exist_ok=False); backup=OUT/'backups'; backup.mkdir()
 file_backups={}; original_exists={}
 for index,(src,dst) in enumerate(targets):
  require(not dst.is_symlink(),'symlinked publication destination')
  original_exists[dst]=dst.exists()
  if dst.exists():
   require(dst.is_file(),'publication destination is not a regular file')
   saved=backup/f'{index:03d}_{dst.name}';shutil.copy2(dst,saved)
   require(sha(saved)==sha(dst),'backup verification failed')
   file_backups[dst]=saved
 published_dirs=[]
 def copy_file_atomic(src,dst):
  temp=dst.with_name(dst.name+'.pr108-'+uuid.uuid4().hex+'.tmp')
  shutil.copy2(src,temp)
  require(sha(temp)==sha(src),'temporary file hash mismatch')
  os.replace(temp,dst)
 def copy_dir_atomic(src,dst):
  temp=dst.with_name(dst.name+'.pr108-'+uuid.uuid4().hex+'.tmp')
  shutil.copytree(src,temp)
  os.replace(temp,dst)
 try:
  for src,dst in targets:copy_file_atomic(src,dst)
  for src,dst in new_dirs:
   copy_dir_atomic(src,dst);published_dirs.append(dst)
  # Verify exact staged files, all 136 dated folders, and protected source state.
  verify_post(plan,prior,pre,engine,targets,stage_roots,raw_date,raw_name,snapshot)
  result={'schema':'pr108_guarded_kg_publication_v1','status':'PASS','stage_sha256':stage_sha,
          'plan_sha256':plan['plan_sha256'],'root_go_sha256':sha(args.root_go),'source_commit':plan['source_commit'],
          'raw_snapshot_name':raw_name,'named_snapshot':snapshot,'dated_snapshot_count_after':136,
          'corpora':receipt['build']['corpora'],'wiki_sha256':{f'wiki/{n}':sha(ROOT/'wiki'/n) for n in WIKI},
          'published_graph_files':{str(dst):sha(dst) for src,dst in targets if 'graphify-out' in str(dst)},
          'published_snapshot_paths':[str(dst) for src,dst in new_dirs],
          'rollback_backups':{str(dst):str(src) for dst,src in file_backups.items()},'writes_performed':True}
  with (OUT/'publish_receipt.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
  print(json.dumps(result,indent=2))
 except BaseException:
  for dst in published_dirs:
   if dst.exists():shutil.rmtree(dst)
  for dst in reversed([dst for _,dst in targets]):
   if dst in file_backups:copy_file_atomic(file_backups[dst],dst)
   elif not original_exists.get(dst,False):dst.unlink(missing_ok=True)
  shutil.rmtree(OUT,ignore_errors=True)
  raise
if __name__=='__main__':main()
