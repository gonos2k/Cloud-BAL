#!/usr/bin/env python3
"""Guarded selected-path Graphify/KG update for the CP06A joint producer. External scratch utility; do not commit."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, re, shutil, stat, subprocess, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT=ROOT/'Cloud-BAL'
SOURCE=ROOT/'scratch/pr78_cp06a_20261012/Cloud-BAL'
OUT=MAINT/'scratch/cp06a_joint_20261012'
BASE='a444a788e8e7301354bec14c3708aacddb8f31d3'
PRIOR=SOURCE/'docs/evidence/pr77_kg_20261012.json'
PRIOR_SHA='60a4ff6072d17f580e88a128b75e25088e49d9ae20d67071f026fb72d2b49025'
PR77_CLOSURE=SOURCE/'docs/evidence/pr77_kg_review_20261012.json'
PR77_CLOSURE_SHA='89a14d840c823060f1adb30d770374462963b386723c86a2d6be7c46a9355a6e'
PR77_ARCHIVE=SOURCE/'docs/evidence/pr77_kg_20261012/archive_manifest.json'
PR77_ARCHIVE_SHA='f6e0034d59ae4e33534a8b0bef80235667bd75cd1df1ac5831e4f14be4a380de'
CP06A_RECEIPT=ROOT/'cloudbal-cp06a-pr-work/docs/evidence/cp06a-kg-20261012.json'
CP06A_RECEIPT_SHA='d0795121dcb01e0dbefe518995b4a46fcded0286089c92a909d49915b7883982'
CP06A_TREE=ROOT/'cloudbal-cp06a-pr-work'
CP06A_RECEIPT_COMMIT='1d44398bcbef7f0bdba2bbcb2149d6abfcfbb2c0'

OLD_AUDIT=MAINT/'scratch/pr59_team_audit_20261006'
OLD_PUBLISH=MAINT/'scratch/pr59_publish_kg_20261002'
OLD_PRODUCT=ROOT/'scratch/pr59_joint_diagnostic_20261002/Cloud-BAL/docs/evidence/pr59_current_lapsprep.json'
PR='PENDING (supply actual PR URL with --pr-url)'
HELPER=Path(__file__).resolve()
GRAPHIFY_PY=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3')
GRAPHIFY_CLI=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/graphify')

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha(p:Path)->str:return sha_bytes(p.read_bytes())
def git(*args,cwd=SOURCE):return subprocess.check_output(['git',*args],cwd=cwd,text=True).rstrip()
def fail(msg):raise RuntimeError('guard failed: '+msg)
def regular_file(path:Path):
    if not stat.S_ISREG(path.lstat().st_mode):fail(f'non-regular selected artifact: {path}')
def reject_symlink_ancestors(path:Path):
    for part in (path,*path.parents):
        if part.is_symlink():fail(f'symlinked output component: {part}')

def guard_destination(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'destination escapes expected root {root}: {path}')
    if path.exists():regular_file(path)

def guard_directory(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'directory escapes expected root {root}: {path}')
    if not path.is_dir():fail(f'expected directory: {path}')

def copy_checked(source:Path,target:Path):
    guard_destination(source)
    guard_destination(target)
    source_hash=sha(source)
    shutil.copy2(source,target)
    regular_file(target)
    if sha(source)!=source_hash or sha(target)!=source_hash:
        fail(f'copy verification failed: {source} -> {target}')

def restore_automatic_snapshots(snapshots):
    for directory,members in snapshots.items():
        previous=Path(directory)
        guard_directory(previous)
        for created in previous.iterdir():
            guard_destination(created)
            if created.name not in members:created.unlink()
        for name,record in members.items():
            backup=Path(record['backup'])
            if sha(backup)!=record['sha256']:fail('prior automatic snapshot backup drift')
            copy_checked(backup,previous/name)
        if {p.name for p in previous.iterdir()}!=set(members):fail('prior snapshot membership changed')
        for name,record in members.items():
            if sha(previous/name)!=record['sha256']:fail('prior snapshot content changed')

def show(commit,path):return subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=SOURCE)
def tracked_snapshot(dirpath:Path)->dict:
    result={}
    for f in sorted(p for p in dirpath.rglob('*') if p.is_file()):
        result[f.relative_to(dirpath).as_posix()]=sha(f)
    return result

def make_plan(commit:str):
    os.environ['TZ']='Asia/Seoul'
    time.tzset()
    if date.today().isoformat()!='2026-10-12':fail('Graphify local snapshot day differs from declared session day')
    if importlib.metadata.version('graphifyy')!='0.9.53':fail('Graphify package must be exactly 0.9.53')
    if Path(sys.executable).resolve()!=GRAPHIFY_PY.resolve():fail('run through pinned Graphify Python')
    if Path(shutil.which('graphify') or '').resolve()!=GRAPHIFY_CLI.resolve():fail('pinned Graphify CLI must be first on PATH')
    if git('rev-parse','HEAD')!=commit:fail('candidate HEAD differs from requested frozen SHA')
    if git('status','--porcelain'):fail('candidate source worktree is not clean')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,commit],cwd=SOURCE,check=True)
    changed=git('diff','--name-status','--find-renames',BASE,commit).splitlines()
    items=[]
    for row in changed:
        fields=row.split('\t')
        status=fields[0]
        if status not in ('A','M') or len(fields)!=2:fail(f'unsupported selected path change: {row}')
        rel=fields[1]
        if rel=='config/cp01_private_host_profile.json':fail('private profile cannot enter selected extraction')
        old=subprocess.run(['git','show',f'{BASE}:{rel}'],cwd=SOURCE,capture_output=True,check=False)
        oldbytes=old.stdout if old.returncode==0 else None
        candidate=SOURCE/rel
        reject_symlink_ancestors(candidate)
        if not candidate.resolve().is_relative_to(SOURCE.resolve()):
            fail(f'selected candidate escapes source root: {candidate}')
        regular_file(candidate)
        maintained=MAINT/rel
        guard_destination(maintained,MAINT)
        items.append({'path':rel,'change':status,'base_sha256':sha_bytes(oldbytes) if oldbytes is not None else None,
          'candidate_sha256':sha(candidate),'maintained_before_sha256':sha(maintained) if maintained.is_file() else None})
    if not items:fail('no source paths changed since declared base')
    immutable_chain=((PRIOR,PRIOR_SHA),(PR77_CLOSURE,PR77_CLOSURE_SHA),
                     (PR77_ARCHIVE,PR77_ARCHIVE_SHA),(CP06A_RECEIPT,CP06A_RECEIPT_SHA))
    for path,expected in immutable_chain:
        guard_destination(path)
        if sha(path)!=expected:fail(f'PR77 immutable receipt-chain artifact changed: {path}')
    prior=json.loads(PRIOR.read_text())
    closure=json.loads(PR77_CLOSURE.read_text())
    cp06a=json.loads(CP06A_RECEIPT.read_text())
    if prior.get('pr')!='https://github.com/gonos2k/Cloud-BAL/pull/77' or prior.get('frozen_source_commit')!='feb0710f90ce33249b9fd29cb3a90f92cba6b7a7':
        fail('PR77 original receipt identity mismatch')
    if closure.get('original_kg_receipt_sha256')!=PRIOR_SHA or closure.get('review_status')!='PASS':
        fail('PR77 append-only review closure does not bind the preserved receipt')
    if cp06a.get('source_commit')!='35831e13a863a09b201fbe428e7faa4a8b9b214f' or cp06a.get('base_commit')!=BASE:
        fail('CP06A maintained baseline receipt identity mismatch')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=CP06A_TREE,text=True).strip()!=CP06A_RECEIPT_COMMIT:
        fail('CP06A baseline worktree moved from its receipted commit')
    cp06a_committed=subprocess.check_output(['git','show',f'{CP06A_RECEIPT_COMMIT}:docs/evidence/cp06a-kg-20261012.json'],cwd=CP06A_TREE)
    if sha_bytes(cp06a_committed)!=CP06A_RECEIPT_SHA:
        fail('CP06A receipt bytes differ from the pinned baseline commit')
    baseline_graphs={
      'KLAPS50':{'snapshot':'2026-10-12-cp06a-native','sha256':'c9633468c49dedc172a59f3d3e5e6192c5e2117ed8420a384f7039fab84cf64d','nodes':34612,'edges':74505,'communities':2744},
      'Cloud-BAL':{'snapshot':'2026-10-12-cp06a-native','sha256':'5de5427f6540ff59f89769c3a1de5a913bf00b95d22126f7bc952dcdac15e9af','nodes':8785,'edges':16081,'communities':722},
    }
    baseline_files={
      'KLAPS50':{'graph.json':'c9633468c49dedc172a59f3d3e5e6192c5e2117ed8420a384f7039fab84cf64d','GRAPH_REPORT.md':'dd289cd2c4c627cdc0ffbf91aa2dd087963f9c01c5d9710c2e9c75db098ea232','manifest.json':'ff7d71f81606a59a100ba1e094ac6ddb287f97486747b5869c98cf8340f56bdc'},
      'Cloud-BAL':{'graph.json':'5de5427f6540ff59f89769c3a1de5a913bf00b95d22126f7bc952dcdac15e9af','GRAPH_REPORT.md':'40ed291210addef51ed57c11255606d95e5cdcedb54e5491ddc20e06fa4365cc','manifest.json':'fbdfa6ac2b58f03fb582a38a1b6f151726f66ac5dbed56ed0f2f97ff94f35e9f'},
    }
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for name,expected in baseline_files[label].items():
            p=directory/'graphify-out/2026-10-12-cp06a-native'/name
            guard_destination(p,directory)
            if sha(p)!=expected:fail(f'{label} immutable CP06A dated baseline differs: {name}')
        live=directory/'graphify-out/graph.json'
        guard_destination(live,directory)
        if sha(live)!=baseline_graphs[label]['sha256']:
            fail(f'{label} live graph differs from the receipted CP06A baseline')
        if cp06a.get('corpora',{}).get(label,{}).get('graph_sha256')!=baseline_graphs[label]['sha256']:
            fail(f'{label} CP06A receipt does not bind the live baseline graph')
        if cp06a.get('corpora',{}).get(label,{}).get('pre_update_graph_sha256')!=prior['corpora'][label]['sha256']:
            fail(f'{label} CP06A receipt does not link back to the preserved PR77 graph')
    current_wiki={
      'wiki/graph-report-cloud-bal.md':'40ed291210addef51ed57c11255606d95e5cdcedb54e5491ddc20e06fa4365cc',
      'wiki/graph-report-klaps50.md':'dd289cd2c4c627cdc0ffbf91aa2dd087963f9c01c5d9710c2e9c75db098ea232',
      'wiki/graph-report.md':'c6c0304796fb0eb542ba27efd7f03f35dd8875e89764d06a9ef5ea9d4c026a53',
      'wiki/index.md':'b65b26aff78cf06d9ce8753c5ae926eee1cf919e0274b1003d988cebea662fd9',
      'wiki/log.md':'614f6fc916b300a51102383ffbf522362c6b16e00cf87c6520b4328b8af48a08',
    }
    for rel,expected in current_wiki.items():
        p=ROOT/rel;guard_destination(p)
        if sha(p)!=expected:fail(f'wiki differs from pinned CP06A baseline: {rel}')
    prior['corpora']=baseline_graphs
    prior['physical_approval']=prior.get('physical_approval','FAIL_OPEN')
    prior['remaining_scientific_gates']=prior.get('remaining_scientific_gates',[])
    prior['remaining_acceptance_gates']=[]
    prior['prior_immutable_receipts']=prior.get('prior_immutable_receipts',{})
    immutable={
      PRIOR:PRIOR_SHA,
      Path('/var/tmp/pr72_refresh_kg.py'):'8d68ddff856a44995ac376c1fff1efc12e4bb7f5c94ab45823af917dadb0eb79',
      OLD_PUBLISH/'update.py':'7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0',
      OLD_AUDIT/'update_kg.py':'bfe6242618e8ca1b60ab1304221d1fd215476d7f23281b69e48963611c0b76e1',
      OLD_AUDIT/'kg_receipt.json':'b07681e59678761ded5e1bd986ff0fe7f57cfb35a345f92ffc96b58424bab7ef',
      OLD_PUBLISH/'kg_receipt.json':'0e6ba4056e1edbcf542a35fe54c81fe88501245b63447324dd4c01c29655020a',
      OLD_PRODUCT:'f6150857b78e5af1c5e77ff9e2a64608c46d44fc490a775d11fe5992f9fec1f9',
    }
    for p,h in immutable.items():
        guard_destination(p,Path('/var/tmp') if p.parent==Path('/var/tmp') else ROOT)
        if sha(p)!=h:fail(f'earlier immutable receipt changed: {p}')
    for label, files in prior.get('dated_snapshots',{}).items():
        for name, record in files.items():
            artifact=Path(record['path'])
            guard_destination(artifact)
            immutable[artifact]=record['after_sha256']
            if sha(artifact) != record['after_sha256']:
                fail(f'{label} dated artifact differs from PR77 native-state receipt-chain baseline: {name}')
    for path, expected in prior['prior_immutable_receipts'].items():
        previous_path=Path(path)
        guard_destination(previous_path,Path('/var/tmp') if previous_path.parent==Path('/var/tmp') else ROOT)
        if sha(previous_path)!=expected:fail(f'previous immutable evidence drift: {path}')
        immutable[previous_path]=expected
    immutable[PRIOR]=PRIOR_SHA
    immutable[PR77_CLOSURE]=PR77_CLOSURE_SHA
    immutable[PR77_ARCHIVE]=PR77_ARCHIVE_SHA
    immutable[CP06A_RECEIPT]=CP06A_RECEIPT_SHA
    immutable[HELPER]=sha(HELPER)
    return items,prior,immutable

def find_validation_evidence(document:dict)->dict:
    found={'cp06a_real_scopes':[],'native_pair_errors':[]}
    def walk(value,path=()):
        if isinstance(value,dict):
            for key,item in value.items():
                next_path=path+(str(key),)
                normalized=' '.join(next_path).lower().replace('-','_')
                if 'scope' in normalized and ('real' in normalized or 'cp06a' in normalized):
                    found['cp06a_real_scopes'].append({'path':'.'.join(next_path),'value':item})
                elif 'native' in normalized and 'pair' in normalized and 'error' in normalized:
                    found['native_pair_errors'].append({'path':'.'.join(next_path),'value':item})
                elif isinstance(item,(dict,list)):walk(item,next_path)
        elif isinstance(value,list):
            for index,item in enumerate(value):
                if isinstance(item,(dict,list)):walk(item,path+(str(index),))
    walk(document)
    if not found['cp06a_real_scopes']:fail('validation receipt lacks CP06A real-scope evidence')
    if not found['native_pair_errors']:fail('validation receipt lacks native-pair error evidence')
    return found

def validation_summary(document:dict)->str:
    checks=document.get('checks')
    scoped=checks.get('scoped_unit') if isinstance(checks,dict) else None
    status=scoped.get('status') if isinstance(scoped,dict) else None
    if not isinstance(status,str) or not status.strip():
        fail('validation receipt must contain checks.scoped_unit.status')
    evidence=find_validation_evidence(document)
    rendered=json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True)
    return f"CP06A scoped-unit status `{status.strip()}`; recorded real-scope and native-pair error fields {rendered}. Full details are in the bound validation receipt."


INHERITED_ACCEPTANCE_GATES=[
    "Whole host/thread FP policy",
    "Completed Q/N/B state",
    "PBL DEL versus dry carrier",
    "Freezing and transient QG/BG",
    "First native call",
    "Water and energy closure",
]
OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS=[
    "Real spatial joint candidate generated from independent observation/background contracts",
    "Valid first native call",
    "Same-carrier dry-mass, water, and energy closure",
    "Spatial mass-wind compatibility at cells and shared faces",
    "Meaning-preserving WPS/metgrid/real handoff",
    "Fixed-setting short-time response and independent observation signal preservation",
]

def load_validation_receipt(argument:str|None,items:list[dict],commit:str):
    if argument is None:return None
    relative=Path(argument)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        fail("validation receipt path must stay relative to the candidate source root")
    relative_text=relative.as_posix()
    source=SOURCE/relative
    reject_symlink_ancestors(source)
    if not source.resolve().is_relative_to(SOURCE.resolve()):
        fail("validation receipt escapes candidate source root")
    regular_file(source)
    selected=next((item for item in items if item["path"]==relative_text),None)
    if selected is None:
        fail("validation receipt must be a changed, selected path in the frozen source commit")
    digest=sha(source)
    if digest!=selected["candidate_sha256"]:
        fail("validation receipt hash differs from the selected frozen-source hash")
    committed=subprocess.check_output(["git","show",f"{commit}:{relative_text}"],cwd=SOURCE)
    if sha_bytes(committed)!=digest:
        fail("validation receipt bytes differ from the frozen commit")
    try:document=json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        fail(f"validation receipt is not valid UTF-8 JSON: {exc}")
    if not isinstance(document,dict):
        fail("validation receipt root must be a JSON object")
    checks=document.get("checks")
    summary=validation_summary(document)
    scoped=checks.get("scoped_unit") if isinstance(checks,dict) else None
    return {"path":relative_text,"sha256":digest,"source_commit":commit,
      "checks":{"scoped_unit":{"status":scoped['status']}},
      "cp06a_evidence":find_validation_evidence(document),'summary':summary}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit',required=True,help='exact clean frozen source commit SHA')
    ap.add_argument('--pr-url',default=None,help='PR URL once assigned; optional while the PR is pending')
    ap.add_argument('--validation-receipt',default='docs/evidence/pr78_validation_20261012.json',help='changed JSON receipt path relative to the candidate source root')
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true',help='read-only guard/preflight; never updates graphs/wiki')
    mode.add_argument('--apply',action='store_true',help='perform Graphify update and derived wiki sync')
    args=ap.parse_args()
    global PR
    PR=args.pr_url or PR
    if args.pr_url and not re.fullmatch(r'https://github\.com/gonos2k/Cloud-BAL/pull/[1-9][0-9]*',args.pr_url):
        fail('--pr-url must be the actual Cloud-BAL pull-request URL')
    if args.apply and not args.pr_url:fail('apply requires the actual PR URL via --pr-url')
    items,prior,immutable=make_plan(args.commit)
    validation=load_validation_receipt(args.validation_receipt,items,args.commit)
    if args.check_only:
        print(json.dumps({'ready':True,'mode':'CHECK_ONLY_NO_WRITES','source':str(SOURCE),'commit':args.commit,'base':BASE,
          'selected_paths':items,'previous_receipt_sha256':PRIOR_SHA,
          'baseline_graphs':{k:{x:prior['corpora'][k][x] for x in ('snapshot','nodes','edges','communities','sha256')} for k in ('KLAPS50','Cloud-BAL')},
          'validation_receipt':validation,'new_output_path':str(OUT),'output_exists':OUT.exists()},indent=2));return
    # This output directory may contain only this external helper before the run.
    reject_symlink_ancestors(OUT)
    if OUT.exists() and set(p.name for p in OUT.iterdir())!={HELPER.name}:
        fail('new CP06A joint output directory is not fresh; refuses overwrite')
    protected={}
    for rel in ('wiki/hot.md','wiki/overview.md'):
        p=ROOT/rel
        guard_destination(p)
        protected[rel]=sha(p)
    protected_dirs=('wiki/.schema','wiki/.schema-proposals','wiki/.research-queue','wiki/entities','wiki/concepts','wiki/sources','wiki/decisions',
      'wiki/heuristics','wiki/experiences','wiki/procedures','wiki/queries')
    for rel in protected_dirs:
        p=ROOT/rel
        if p.exists():
            guard_directory(p)
            files=sorted(x for x in p.rglob('*') if x.is_file())
            for f in files:guard_destination(f)
            entries=[(f.relative_to(ROOT).as_posix(),sha(f)) for f in files]
            protected[rel]=sha_bytes(json.dumps(entries,separators=(',',':')).encode())
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(OLD_PUBLISH))
    import update as graph_update
    graph_update.SOURCE=SOURCE;graph_update.OUT=OUT;graph_update.BASE_COMMIT=BASE;graph_update.PR=PR
    graph_update.PATHS=tuple(x['path'] for x in items)
    spec=importlib.util.spec_from_file_location('pr59_audit_util',OLD_AUDIT/'update_kg.py')
    audit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=audit;spec.loader.exec_module(audit)
    audit.ROOT=ROOT;audit.MAINTAINED=MAINT;audit.OUT=OUT;audit.PATHS=tuple(x['path'] for x in items)
    # Guard every destination the delegated Graphify/writer batch may create.
    for directory in (ROOT,MAINT):
        for rel in graph_update.GRAPH_FILES:
            guard_destination(directory/'graphify-out'/rel,directory)
        for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
            guard_destination(directory/'graphify-out/2026-10-12-cp06a-joint'/name,directory)
    for rel in graph_update.WIKI_FILES:guard_destination(ROOT/'wiki'/rel)
    before={label:json.loads((directory/'graphify-out/graph.json').read_text()) for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT))}
    # Back up every graph/report/manifest and allowed wiki artifact before mutation.
    baseline_presence={}
    rollback_backup_sha256={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for rel in graph_update.GRAPH_FILES:
            p=directory/'graphify-out'/rel
            baseline_presence[str(p)]=p.exists()
            if p.exists():
                regular_file(p)
                target=OUT/'backups'/label/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
    for rel in graph_update.WIKI_FILES:
        p=ROOT/'wiki'/rel
        baseline_presence[str(p)]=p.exists()
        if p.exists():
            regular_file(p)
            target=OUT/'backups/wiki'/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
            rollback_backup_sha256[str(target)]=sha(target)
    dated_names=('graph.json','GRAPH_REPORT.md','manifest.json')
    dated_before={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        dated_before[label]={}
        for name in dated_names:
            p=directory/'graphify-out/2026-10-12-cp06a-joint'/name
            target=OUT/'backups'/label/'dated_2026-10-12-cp06a-joint'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            existed=p.exists()
            if existed:
                copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
            dated_before[label][name]={'path':str(p),'before_sha256':sha(p) if existed else None,'backup_path':str(target),'existed_before':existed}
    automatic_snapshot_backups={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        previous=directory/'graphify-out/2026-10-12'
        if not previous.exists():
            continue
        guard_directory(previous,directory)
        members={}
        for original in sorted(previous.iterdir()):
            guard_destination(original,directory)
            backup=OUT/'backups'/label/'prior_auto_2026-10-12'/original.name
            backup.parent.mkdir(parents=True,exist_ok=True)
            copy_checked(original,backup)
            members[original.name]={'backup':str(backup),'sha256':sha(backup)}
        automatic_snapshot_backups[str(previous)]=members
    sync={'base_commit':BASE,'frozen_commit':args.commit,'paths':items}
    source_sync_path=OUT/'source_sync.json'
    guard_destination(source_sync_path)
    source_sync_path.write_text(json.dumps(sync,indent=2)+'\n')
    try:
        records={'KLAPS50':graph_update.update_graph('KLAPS50',ROOT,'Cloud-BAL',items),
                 'Cloud-BAL':graph_update.update_graph('Cloud-BAL',MAINT,'',items)}
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            ext=json.loads((OUT/f'{label.lower().replace("-","_")}_extraction.json').read_text())
            audit.record_snapshot(label,directory,before[label],ext)
        # Preserve every old date-directory member, including hidden labels/analysis.
        restore_automatic_snapshots(automatic_snapshot_backups)
        private=audit.verify_private_profile(before)
        if private['Cloud-BAL']['nodes']!=134 or private['Cloud-BAL']['incident_links']!=133 or not private['Cloud-BAL']['unchanged'] or private['KLAPS50']['nodes']!=0:
            fail('private profile preservation guard failed')
        if git('rev-parse','HEAD')!=args.commit or git('status','--porcelain'):fail('source checkout changed during graph build')
        for x in items:
            if sha(SOURCE/x['path'])!=x['candidate_sha256']:fail(f'candidate source changed during build: {x["path"]}')
            p=MAINT/x['path'];guard_destination(p,MAINT);after=sha(p) if p.is_file() else None
            if after!=x['maintained_before_sha256']:fail(f'maintained source path changed: {x["path"]}')
        for label,r in records.items():
            r['previous_graph_sha256']=prior['corpora'][label]['sha256']
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            report_path=directory/'graphify-out/GRAPH_REPORT.md'
            guard_destination(report_path,directory)
            old_report=report_path.read_text()
            new_section=(f"## Graph Freshness\n\n"
                f"- Selected candidate overlay: `{args.commit}` against `{BASE}`; "
                f"{len(items)} committed changed paths only.\n"
                f"- Snapshot: {records[label]['snapshot']}. Maintained checkout HEAD is a separate base, "
                f"not the source identity of this selected extraction.\n"
                f"- The persistent graph combines earlier corpus snapshots and selected overlays. "
                f"This is not a full extraction of the candidate tree.\n"
                f"- AST/Markdown headings only; cross-file Fortran CALL extraction is partial. "
                f"Freshness is navigation evidence, not runtime/scientific validation.\n"
                f"- External source trees and runtime artifacts outside the selected repository paths are not represented.\n")
            new_report,count=re.subn(r"## Graph Freshness\n.*?(?=\n## |\Z)",new_section,old_report,flags=re.S)
            if count!=1:fail(f'{label} derived freshness section missing or duplicated')
            report_path.write_text(new_report)
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for name in dated_names:
                source=directory/'graphify-out'/name
                target=directory/'graphify-out/2026-10-12-cp06a-joint'/name
                guard_destination(target,directory)
                target.parent.mkdir(parents=True,exist_ok=True)
                copy_checked(source,target)
                dated_before[label][name]['after_sha256']=sha(target)
                if sha(source)!=sha(target):fail(f'{label} final dated copy differs: {name}')
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            records[label]['snapshot']=datetime.fromtimestamp((directory/'graphify-out/GRAPH_REPORT.md').stat().st_mtime,timezone.utc).isoformat()
        copy_checked(ROOT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-klaps50.md')
        copy_checked(MAINT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-cloud-bal.md')
        idx=ROOT/'wiki/graph-report.md';lines=idx.read_text().splitlines()
        for i,line in enumerate(lines):
            for label,r in records.items():
                if line.startswith(f'| {label} |'):
                    folder='.' if label=='KLAPS50' else 'Cloud-BAL/';mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[i]=f"| {label} | `{folder}` | {r['snapshot']} (CP06A joint-producer candidate overlay) | {r['nodes']} | {r['edges']} | {r['communities']} | [[{mirror}]] |"
        guard_destination(idx)
        idx.write_text('\n'.join(lines)+'\n')
        page=ROOT/'wiki/index.md';before_text=page.read_text();start=before_text.index('## Graph snapshot');end=before_text.find('\n## ',start+3);has_tail=end>=0
        if not has_tail:end=len(before_text)
        section='## Graph snapshot\n\n'
        for label,r in records.items():
            section+=(f"- {label}: {r['snapshot']}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"CP06A joint-producer delta [{r['delta_nodes']}, {r['delta_edges']}].\n")
        section+='- [[graph-report|Separate corpus reports]] retain extraction limits. Graph freshness is navigation evidence only, not runtime or scientific validation.\n'
        after_text=before_text[:start]+section+before_text[end:]
        if before_text[:start]!=after_text[:start]:fail('index prefix changed outside Graph snapshot section')
        if has_tail:
            new_end=after_text.find('\n## ',after_text.index('## Graph snapshot')+3)
            if new_end<0 or before_text[end:]!=after_text[new_end:]:fail('index suffix changed outside Graph snapshot section')
        guard_destination(page)
        after_text=re.sub(r'(?m)^date_modified: .*$', 'date_modified: 2026-10-12', after_text, count=1)
        page.write_text(after_text)
        stamp=datetime.now(timezone.utc)
        log=ROOT/'wiki/log.md'
        entry=f"\n## [{stamp.strftime('%Y-%m-%d')}] kg-update | CP06A joint-producer selected-path overlay ({stamp.strftime('%H:%M UTC')})\n"
        entry+=f"- PR {PR}; frozen source commit `{args.commit}` against `{BASE}`. {len(items)} committed changed paths were hash-captured and structurally extracted as candidate overlays; maintained source files were not copied or replaced.\n"
        for label,r in records.items():
            entry+=(f"- {label} snapshot {r['snapshot']}: {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"CP06A joint delta [{r['delta_nodes']}, {r['delta_edges']}], added/removed IDs {r['added_ids']}/{r['removed_ids']}; "
              f"previous graph SHA-256 `{r['previous_graph_sha256']}`.\n")
        entry+='- Cloud-BAL private profile remains 134 nodes / 133 incident links; KLAPS50 carries zero nodes from this private source. Graph integrity diagnostics passed.\n'
        entry+='- Graphify 0.9.53 selected-source AST/Markdown-heading extraction and separate `cluster-only --no-viz --no-label`; no semantic refresh. Fortran cross-file CALL extraction is partial; corpora overlap and counts are separate.\n'
        entry+=f"- Graph freshness is navigation-only; selected-source AST/Markdown headings have no semantic refresh, and cross-file Fortran CALL extraction is partial. The bound validation receipt is scoped evidence; physical approval carries forward `{prior['physical_approval']}`.\n"
        entry+=f"- Durable preceding PR77 KG receipt: `{PRIOR.relative_to(ROOT)}` (SHA-256 `{PRIOR_SHA}`); append-only review closure SHA-256 `{PR77_CLOSURE_SHA}`.\n"
        if validation:
            entry+=f"- Validation evidence: {validation['summary']} Receipt `{validation['path']}` SHA-256 `{validation['sha256']}` at `{args.commit}`.\n"
        else:
            entry+='- CP06A validation receipt not supplied; no new runtime-validation claims recorded.\n'
        entry+=f"- Overall physical approval remains `{prior['physical_approval']}`; inherited acceptance gates remain open.\n"
        entry+='- All six same-candidate integration conditions remain OPEN; this selected-path structural update does not establish end-to-end candidate integration or native acceptance.\n'
        guard_destination(log)
        with log.open('a') as f:f.write(entry)
        for rel,expected in protected.items():
            p=ROOT/rel
            if p.is_file():
                guard_destination(p)
                if sha(p)!=expected:fail(f'protected wiki file changed: {rel}')
            else:
                guard_directory(p)
                files=sorted(x for x in p.rglob('*') if x.is_file())
                for q in files:guard_destination(q)
                rows=[(q.relative_to(ROOT).as_posix(),sha(q)) for q in files]
                if sha_bytes(json.dumps(rows,separators=(',',':')).encode())!=expected:fail(f'protected wiki directory changed: {rel}')
        for p,h in immutable.items():
            if p!=HELPER:guard_destination(p,Path('/var/tmp') if p.parent==Path('/var/tmp') else ROOT)
            if sha(p)!=h:fail(f'prior immutable receipt changed: {p}')
        receipt={
          'schema':'cp06a_joint_selected_path_graphify_kg_receipt_v1','dated_snapshot_day':'2026-10-12','dated_snapshot_timezone':'Asia/Seoul (session day)','recorded_utc':datetime.now(timezone.utc).isoformat(),
          'pr':PR,'base_commit':BASE,'frozen_source_commit':args.commit,'source_path':str(SOURCE),'selected_path_count':len(items),
          'selected_paths':items,'source_sync_sha256':sha(OUT/'source_sync.json'),
          'previous_pr77_kg_receipt_sha256':PRIOR_SHA,'previous_pr77_closure_sha256':PR77_CLOSURE_SHA,
          'previous_cp06a_overlay_receipt_sha256':CP06A_RECEIPT_SHA,
          'previous_cp06a_overlay_source_commit':'35831e13a863a09b201fbe428e7faa4a8b9b214f',
          'previous_physical_approval':prior['physical_approval'],
          'physical_approval':prior['physical_approval'],
          'remaining_scientific_gates':prior.get('remaining_scientific_gates',[]),
          'remaining_acceptance_gates':INHERITED_ACCEPTANCE_GATES,
          'same_candidate_integration_conditions_open':OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS,
          'validation_receipt_binding':validation,
          'graphify_version':subprocess.check_output(['graphify','--version'],text=True).strip(),'python_executable':sys.executable,
          'mode':'guarded selected-path overlay extraction/build_merge, cluster-only, derived wiki sync',
          'extraction':'Graphify AST and Markdown headings only; no semantic/LLM refresh',
          'corpora':records,'private_profile_preservation':private,
          'dated_snapshots':dated_before,'dated_snapshot_directory':'2026-10-12-cp06a-joint',
          'automatic_snapshot_preservation':automatic_snapshot_backups,'baseline_artifact_presence':baseline_presence,
          'rollback_backup_sha256':rollback_backup_sha256,'protected_content_before_sha256':protected,
          'wiki':{'updated':['graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md#Graph-snapshot','log.md (append-only)'],
            'protected_unchanged':list(protected),'schema_and_content_pages_touched':False},
          'prior_immutable_receipts':{str(p):h for p,h in immutable.items()},
          'limitations':['Graph counts are separate for overlapping KLAPS50 and Cloud-BAL corpora.','Markdown semantic extraction was not performed; Markdown contributes heading structure only.',
            'Fortran cross-file CALL extraction is partial.','External source trees and runtime artifacts outside selected repository paths are not represented.',
            'Candidate overlay graphs and freshness are structural navigation evidence, not runtime or scientific validation.',
            'The prior PR77 receipt chain remains immutable; this structural update does not establish end-to-end runtime or scientific acceptance.']}
        receipt['wiki_sha256']={rel:sha(ROOT/rel) for rel in ('wiki/graph-report.md','wiki/graph-report-klaps50.md','wiki/graph-report-cloud-bal.md','wiki/index.md','wiki/log.md')}
        rp=OUT/'kg_receipt.json';guard_destination(rp);rp.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'receipt':str(rp),'receipt_sha256':sha(rp),'corpora':records,'private_profile':private},indent=2))
    except BaseException:
        restore_automatic_snapshots(automatic_snapshot_backups)
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for rel in graph_update.GRAPH_FILES:
                b=OUT/'backups'/label/rel;t=directory/'graphify-out'/rel
                if b.exists():
                    if sha(b)!=rollback_backup_sha256[str(b)]:fail(f'rollback backup changed: {b}')
                    copy_checked(b,t)
                elif not baseline_presence.get(str(t),True) and t.exists():
                    guard_destination(t,directory);t.unlink()
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for name in dated_names:
                b=OUT/'backups'/label/'dated_2026-10-12-cp06a-joint'/name
                if b.exists():
                    if sha(b)!=rollback_backup_sha256[str(b)]:fail(f'rollback backup changed: {b}')
                    copy_checked(b,directory/'graphify-out/2026-10-12-cp06a-joint'/name)
                elif not dated_before[label][name]['existed_before']:
                    target=directory/'graphify-out/2026-10-12-cp06a-joint'/name
                    if target.exists():guard_destination(target,directory);target.unlink()
        for rel in graph_update.WIKI_FILES:
            b=OUT/'backups/wiki'/rel;t=ROOT/'wiki'/rel
            if b.exists():
                if sha(b)!=rollback_backup_sha256[str(b)]:fail(f'rollback backup changed: {b}')
                copy_checked(b,t)
            elif not baseline_presence.get(str(t),True) and t.exists():
                guard_destination(t);t.unlink()
        raise

if __name__=='__main__':main()
