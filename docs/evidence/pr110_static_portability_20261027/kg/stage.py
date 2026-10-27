#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT = ROOT / 'Cloud-BAL'
SOURCE = Path('/var/tmp/cloudbal-pr110')
BASE = '6b4ee5d71c9a88acd861b41d607d31087c165267'
COMMIT = 'bb2358de77d0496d13004b0fba0d6d96036d2934'
DATE = '2026-10-27'
SNAPSHOT = f'{DATE}-pr110-static-input-portability'
OUT = Path('/var/tmp/pr110_kg_stage_20261027_v4')
BASELINE = Path('/var/tmp/pr110_kg_baseline_20261027.json')
PR109_SOURCE = SOURCE / 'docs/evidence/pr109_memory_portability_20261027/kg'
PR105_HELPERS = SOURCE / 'docs/evidence/pr105_observation_pairing_20261026/kg'

SELECTED = [
 'src/lapsprep/module_laps_static.f90',
 'tests/fixtures/pr110_static_reader/create_fixtures.py',
 'tests/fixtures/pr110_static_reader/reader_driver.f90',
 'tests/run_pr110_static_reader.sh',
 'tests/run_unit_tests.sh',
 'tests/test_pr71_guarded_composer.py',
 'tests/test_pr83_same13_native_provenance.py',
 'tests/test_pr83_same13_native_transaction.py',
]
WIKI = ('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod
def git(*args: str) -> str: return subprocess.check_output(['git',*args],cwd=SOURCE,text=True).strip()
def require(ok, msg):
    if not ok: raise RuntimeError(msg)
def snapshot_inventory(roots):
    result={}
    for root in roots:
        gd=root/'graphify-out'
        for folder in sorted(gd.iterdir()):
            if folder.is_dir() and folder.name[:4].isdigit():
                result[str(folder)]={p.name:{'sha256':sha(p)} for p in sorted(folder.iterdir()) if p.is_file()}
    return result

def main():
    require(not OUT.exists(), f'refuse existing stage: {OUT}')
    require(git('rev-parse','HEAD')==COMMIT and not git('status','--porcelain'), 'source worktree is not clean at pinned commit')
    require(git('merge-base',BASE,COMMIT)==BASE, 'source commit does not descend from graph-selection base')
    changed=set(git('diff','--name-only','--diff-filter=ACMRT',BASE,COMMIT).splitlines())
    require(set(SELECTED)<=changed, f'selected paths not changed: {sorted(set(SELECTED)-changed)}')
    require(all((SOURCE/n).is_file() and not (SOURCE/n).is_symlink() for n in changed), 'changed source path missing or symlinked')
    manifest=json.loads(BASELINE.read_text())
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        base=manifest['corpora'][label]
        g=json.loads((root/'graphify-out/graph.json').read_text())
        require(sha(root/'graphify-out/graph.json')==base['graph_sha256'],f'{label} graph baseline drift')
        require((len(g['nodes']),len(g['links']))==(base['nodes'],base['edges']),f'{label} graph count drift')
        current={p.name:sha(p) for p in sorted((root/'graphify-out').iterdir()) if p.is_file()}
        require(current==base['top_level_files'],f'{label} graphify top-level files drift')
        for name,h in base['top_level_files'].items(): require(sha(root/'graphify-out'/name)==h,f'{label} graph file changed: {name}')
    for name,h in manifest['wiki'].items(): require(sha(ROOT/'wiki'/name)==h,f'maintained wiki drift: {name}')
    expected={}
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for folder,members in manifest['corpora'][label]['dated_snapshots'].items():
            expected[str(root/'graphify-out'/folder)]={n:{'sha256':h} for n,h in members.items()}
    actual=snapshot_inventory((ROOT,MAINT))
    require(actual==expected and len(actual)==140, 'maintained dated snapshot inventory differs from captured 140-folder baseline')
    prior_stage=json.loads((PR109_SOURCE/'stage_receipt.json').read_text())
    prior_pub=json.loads((PR109_SOURCE/'publication_receipt.json').read_text())
    require(prior_pub.get('status')=='PASS' and prior_pub.get('source_commit')=='367f3a18175e7eba005ac6f14955802b8d81b109' and prior_pub.get('dated_snapshot_count_after')==140, 'PR109 publication baseline receipt mismatch')
    require(prior_stage.get('stage_sha256')==prior_pub.get('stage_sha256'), 'PR109 stage/publication lineage mismatch')
    prior_plan=prior_stage['plan']; helpers=prior_plan['pinned_helpers']
    sys.path.insert(0,str(PR105_HELPERS))
    preflight=load('preflight_kg',PR105_HELPERS/'preflight_kg.py')
    apply=load('pr110_kg_apply',PR105_HELPERS/'apply_kg.py')
    preflight.SOURCE=SOURCE; preflight.ROOT=ROOT; preflight.MAINT=MAINT; preflight.EXPECTED_SNAPSHOTS=140
    preflight.PRIOR=PR105_HELPERS/'publication/kg_receipt.json'
    preflight.PRIOR_SHA=prior_stage['prior_receipt_sha256']
    preflight.PR105_SNAPSHOT=SNAPSHOT; preflight.BASE=BASE; preflight.GRAPH_BASE=BASE; preflight.WIKI_FILES=WIKI
    # PR110 selection was separately reviewed; retain the pinned extractor/auditor versions.
    active_pins=preflight.active250_root_go_snapshot()
    require({k:v for k,v in active_pins.items() if k != 'path'}=={k:v for k,v in prior_plan['active250_root_go_snapshot'].items() if k != 'path'},'active250 ROOTGO pins drift')
    require(preflight.current_snapshot_inventory((ROOT,MAINT),expected_count=140)==expected,'pinned snapshot inventory check failed')
    # Pin current maintained outputs and metadata, including all user-dirty state in their hashes.
    graphfiles=tuple(helpers['graph_artifact_names']); artifacts={}; metadata={}; backups={}
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        gd=root/'graphify-out'; artifacts[label]={}; metadata[label]={}
        for name in graphfiles:
            p=gd/name
            if p.is_file(): artifacts[label][name]=sha(p)
        for p in sorted(gd.iterdir()):
            if p.is_dir() or p.name in graphfiles: continue
            require(p.is_file() and not p.is_symlink(),f'unexpected graph metadata path {p}')
            metadata[label][p.name]=sha(p)
        backups[label]=preflight.automatic_backup_condition(gd)
        require(backups[label]['automatic_backup_enabled'],f'automatic backup disabled for {label}')
    source_hashes={n:sha(SOURCE/n) for n in SELECTED}
    hash_only=sorted(changed-set(SELECTED))
    plan={'source':str(SOURCE),'source_commit':COMMIT,'approval_base':BASE,'graph_selection_base':BASE,'pr_url':'https://github.com/gonos2k/Cloud-BAL/pull/110',
      'automatic_snapshot_date':DATE,'selected_graph_paths':SELECTED,'selected_source_sha256':source_hashes,
      'hash_only_paths':hash_only,'hash_only_sha256':{n:sha(SOURCE/n) for n in hash_only},
      'baseline_graph_artifacts':artifacts,'baseline_graphify_metadata':metadata,'graphify_automatic_backup_conditions':backups,
      'pinned_helpers':helpers,'maintained_source_snapshot':prior_plan['maintained_source_snapshot'],
      'active250_root_go_snapshot':active_pins,'inherited_immutable_pin_count':197,
      'protected_content_sha256':prior_plan['protected_content_sha256']}
    plan['plan_sha256']=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    OUT.mkdir(); (OUT/'staging').mkdir()
    apply.SNAPSHOT_FILES=('graph.json','GRAPH_REPORT.md','manifest.json'); apply.preflight=preflight
    preflight.WIKI_FILES=WIKI
    # Permit only this exact reviewed PR110 selection in the pinned auditor.
    def finalize(plan_arg,stage_root,stage_maint,build):
        records=build['corpora']
        limits=('Selected PR110 static-reader and test-runner source paths only; documentation, policy, and evidence are hash-bound only. '
                'Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime or scientific validation.')
        for label,directory in (('KLAPS50',stage_root),('Cloud-BAL',stage_maint)):
            report=directory/'graphify-out/GRAPH_REPORT.md'; content=report.read_text()
            section=(f"## Graph Freshness\n\n- PR110 source `{COMMIT}`; approval base and graph-selection base `{BASE}`; {len(SELECTED)} selected paths.\n- {limits}\n")
            report.write_text(apply.update_graph_freshness(content,section,report))
            mirror='graph-report-klaps50.md' if label=='KLAPS50' else 'graph-report-cloud-bal.md'
            shutil.copy2(report,stage_root/'wiki'/mirror)
            snap=directory/'graphify-out'/SNAPSHOT; snap.mkdir()
            for name in apply.SNAPSHOT_FILES: shutil.copy2(directory/'graphify-out'/name,snap/name)
            records[label]['snapshot']=SNAPSHOT
        idx=stage_root/'wiki/graph-report.md'; lines=idx.read_text().splitlines()
        for i,line in enumerate(lines):
            for label in ('KLAPS50','Cloud-BAL'):
                if line.startswith(f'| {label} |'):
                    row=records[label]; folder='.' if label=='KLAPS50' else 'Cloud-BAL/'; mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[i]=f"| {label} | `{folder}` | {SNAPSHOT} (PR110 static input portability) | {row['nodes']} | {row['edges']} | {row['communities']} | [[{mirror}]] |"
        idx.write_text('\n'.join(lines)+'\n')
        page=stage_root/'wiki/index.md'; raw=page.read_bytes(); start=raw.find(b'## Graph snapshot'); end=raw.find(b'\n## ',start+3); end=len(raw) if end<0 else end
        section='## Graph snapshot\n\n'+'\n'.join(f"- {label}: {SNAPSHOT}; {records[label]['nodes']} nodes / {records[label]['edges']} edges / {records[label]['communities']} communities." for label in ('KLAPS50','Cloud-BAL'))+'\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n'
        raw=raw[:start]+section.encode()+raw[end:]; raw,count=re.subn(rb'(?m)^(date_modified:\s*)[^\r\n]+',lambda m:m.group(1)+DATE.encode(),raw,count=1); require(count==1,'wiki date_modified field not unique'); page.write_bytes(raw)
        log=stage_root/'wiki/log.md'; entry=f"\n## [{DATE}] kg-update | PR110 static input portability\n- Source `{COMMIT}`; approval base and graph-selection base `{BASE}`.\n"
        for label in ('KLAPS50','Cloud-BAL'):
            r=records[label]; entry+=f"- {label}: {SNAPSHOT}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; delta nodes={r['delta_nodes']}, edges={r['delta_edges']}.\n"
        entry+=f"- Selected {len(SELECTED)} code/test paths; remaining {len(hash_only)} changed paths hash-only.\n- PR109 maintained snapshots (140 folders), user docs, cache state, and inherited pins preserved.\n- Extraction limits: {limits}\n"
        with log.open('a') as f: f.write(entry)
        return {'corpora':records,'limitations':limits}
    apply.finalize_stage=finalize
    auditor=load('pr110_auditor_probe',Path(helpers['pr99_auditor']['path']))
    # The auditor checks snapshot invariants, not an allowlist; set paths to the exact reviewed selection.
    auditor.PATHS=tuple(SELECTED)
    stage_root,stage_maint,build=apply.prepare_stage(plan,OUT)
    final=finalize(plan,stage_root,stage_maint,build)
    inventory=apply.stage_inventory(stage_root,stage_maint)
    require(snapshot_inventory((ROOT,MAINT))==expected,'maintained snapshots changed while staging')
    for name,h in source_hashes.items(): require(sha(SOURCE/name)==h,f'selected source changed: {name}')
    for name,h in plan['hash_only_sha256'].items(): require(sha(SOURCE/name)==h,f'hash-only source changed: {name}')
    receipt={'plan':plan,'build':final,'stage_inventory':inventory,'baseline_dated_snapshot_count':140,'expected_dated_snapshot_count_after_apply':144,
             'preserved_baseline_manifest_sha256':sha(BASELINE),'pr109_publication_receipt_sha256':sha(PR109_SOURCE/'publication_receipt.json')}
    receipt['stage_sha256']=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (OUT/'stage_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'STAGE_ONLY_NO_MAINTAINED_WRITES','stage_sha256':receipt['stage_sha256'],'plan_sha256':plan['plan_sha256'],'selected_paths':SELECTED,'hash_only_paths':hash_only,'corpora':final['corpora'],'output':str(OUT)},indent=2))
if __name__=='__main__': main()
