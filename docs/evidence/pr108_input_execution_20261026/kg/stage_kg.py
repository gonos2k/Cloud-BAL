#!/usr/bin/env python3
"""Stage PR108 selected-source Graphify update using the pinned PR105 engine."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, subprocess, sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT = ROOT / 'Cloud-BAL'
RECEIPT = ROOT / 'scratch/pr108_input_execution_20261026/Cloud-BAL/docs/evidence/pr105_observation_pairing_20261026/kg/publication/kg_receipt.json'
RECEIPT_SHA = '34e96032623e8a58d3717941d910efbc50eedd712851f894e9775f69537187fc'
SOURCE_REL = Path('scratch/pr108_input_execution_20261026/Cloud-BAL')
APPROVAL_BASE = '4c290f1fff9c78cbe9967ce312114f0f53a27a43'
GRAPH_SELECTION_BASE = 'dc1d2d2c22bdfa44290b800c9e050299bc0b8dee'
SNAPSHOT = '2026-10-26-pr108-input-execution'
EXPECTED_PATHS = {
    'README.md',
    'docs/CI_CONTRACT.md',
    'docs/CURRENT_RESEARCH_STATUS.md',
    'docs/PR108_INPUT_EXECUTION_CONTRACTS_20261026.md',
    'src/common/cloud_bal_native_w_consumer.f90',
    'src/lapsprep/lapsprep.f90',
    'src/lapsprep/module_setup.f90',
    'tests/check_test_tiers.py',
    'tests/lapsprep_vapor_fixture.py',
    'tests/output_safety.sh',
    'tests/run_lapsprep_vapor.sh',
    'tests/run_native_w_consumer.sh',
    'tests/run_python_contract_tests.sh',
    'tests/run_python_test.py',
    'tests/run_real_manufactured_balance_cases.sh',
    'tests/run_real_shadow_cases.sh',
    'tests/run_shell_transaction_recovery.sh',
    'tests/test_initialize_native_moments.py',
    'tests/test_kg_external_helper_integration.py',
    'tests/test_native_w_consumer.f90',
    'tests/test_pr103_kg_guard.py',
    'tests/test_pr103_surface_temperature_observation.py',
    'tests/test_pr104_kg_guard.py',
    'tests/test_pr104_validtime_observation.py',
    'tests/test_pr105_kg_guard.py',
    'tests/test_pr83_policy_source_integration.py',
    'tests/test_python_test_runner.py',
    'tools/pr103_surface_temperature_observation.py',
}
JSON_HASH_ONLY_PATHS = {
    'tests/fixtures/pr83_policy_contract.json',
    'tests/python_script_test_allowlist.json',
    'tests/test_tier_exceptions.json',
}

PR106_DOC = 'docs/PR106_CLOSED_FORECAST_AND_IR_SCOPE_20261026.md'
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')
GRAPH_ROOTS = (ROOT, MAINT)

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod
def git(source: Path,*args: str) -> str: return subprocess.check_output(['git',*args],cwd=source,text=True).strip()
def fail(message: str): raise RuntimeError(message)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',required=True)
    parser.add_argument('--output',type=Path,default=Path('/var/tmp/pr108_kg_stage_20261026'))
    args=parser.parse_args()
    source=(ROOT/SOURCE_REL).resolve(); out=args.output.resolve()
    if out.exists(): fail(f'refuse existing stage output: {out}')
    if not RECEIPT.is_file() or sha(RECEIPT)!=RECEIPT_SHA: fail('PR105 applied receipt hash drift')
    prior=json.loads(RECEIPT.read_text())
    if prior.get('status')!='PASS' or prior.get('source_commit')!='7317dff60942cd27fff4e3a4ba8345f2ccc509fd' or prior.get('post_apply_dated_snapshot_count')!=128: fail('PR105 graph baseline receipt mismatch')
    if prior.get('physical_approval')!='FAIL_OPEN' or prior.get('observation_skill')!='NOT_EVALUATED': fail('PR105 approval boundary drift')
    if git(source,'rev-parse','HEAD')!=args.commit: fail('source HEAD differs from requested commit')
    if git(source,'status','--porcelain'): fail('source checkout must be clean for staging')
    if git(source,'merge-base',GRAPH_SELECTION_BASE,args.commit)!=GRAPH_SELECTION_BASE: fail('source commit does not descend from PR105 graph-selection baseline')
    if git(source,'merge-base',APPROVAL_BASE,args.commit)!=APPROVAL_BASE: fail('source commit does not descend from PR106 approval base')
    changed=set(git(source,'diff','--name-only','--diff-filter=ACMRT',GRAPH_SELECTION_BASE,args.commit).splitlines())
    # Evidence is hash-bound in the source commit, never selected for graph extraction.
    
    allowed=EXPECTED_PATHS | JSON_HASH_ONLY_PATHS
    unexpected={p for p in changed if not p.startswith('docs/evidence/') and p not in allowed}
    if unexpected: fail(f'unreviewed source paths in PR108 diff: {sorted(unexpected)}')
    allowed |= {'tests/fixtures/pr83_policy_contract.json'}
    source_paths={p for p in changed if not p.startswith('docs/evidence/')}
    if source_paths!=allowed: fail(f'PR108 changed path set differs: missing={sorted(allowed-source_paths)}')
    selected=set(EXPECTED_PATHS)
    hash_only=sorted(p for p in changed if p not in selected)
    if not (source/PR106_DOC).is_file() or (source/PR106_DOC).is_symlink(): fail('PR106 carry-forward document missing or symlinked')
    selected.add(PR106_DOC)
    for name in selected:
        p=source/name
        if not p.is_file() or p.is_symlink(): fail(f'missing or symlinked source: {name}')
    helper_dir=source/'docs/evidence/pr105_observation_pairing_20261026/kg'
    sys.path.insert(0,str(helper_dir))
    preflight=load('pr108_stage_preflight',helper_dir/'preflight_kg.py')
    apply=load('pr108_stage_apply',helper_dir/'apply_kg.py')
    preflight.SOURCE=source; preflight.ROOT=ROOT; preflight.MAINT=MAINT
    preflight.PRIOR=RECEIPT; preflight.PRIOR_SHA=RECEIPT_SHA; preflight.EXPECTED_SNAPSHOTS=132
    preflight.PR105_SNAPSHOT=SNAPSHOT; preflight.GRAPH_BASE=GRAPH_SELECTION_BASE; preflight.BASE=APPROVAL_BASE
    # Preserve PR105's 128-folder lineage and add the exact PR107 published folders.
    inventory=dict(prior['dated_snapshot_baseline'])
    for folder,members in prior['post_apply_snapshot_additions'].items():
        inventory[folder]={name:{'sha256':row['sha256']} for name,row in members.items()}
    preflight.EXPECTED_SOURCE=prior['maintained_source_snapshot_after']
    pub_path=Path('/var/tmp/pr107_kg_publication_20261026/publish_receipt.json')
    pub_sha='35603e219745640dc2c520198db9cb3e8446e26d48ac3ca4de18b9977f943c3e'
    pr107_stage_path=Path('/var/tmp/pr107_kg_stage_20261026_v2/stage_receipt.json')
    pr107_stage_sha='2b28ee23e0d1d190b6b940dd0e0d69d395d443c5ee55fa49280d749851cb639d'
    if not pub_path.is_file() or sha(pub_path)!=pub_sha: fail('PR107 publication receipt hash drift')
    pub=json.loads(pub_path.read_text())
    if pub.get('status')!='PASS' or pub.get('stage_sha256')!=pr107_stage_sha or pub.get('dated_snapshot_count_after')!=132: fail('PR107 published baseline receipt mismatch')
    if not pr107_stage_path.is_file(): fail('PR107 stage receipt unavailable')
    pr107_stage=json.loads(pr107_stage_path.read_text())
    if pr107_stage.get('stage_sha256')!=pr107_stage_sha: fail('PR107 stage receipt fingerprint mismatch')
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for staged_name,published_name in (('2026-10-26','2026-10-26-pr107-graphify-raw'),('2026-10-26-pr107-t39-capture','2026-10-26-pr107-t39-capture')):
            staged=Path('/var/tmp/pr107_kg_stage_20261026_v2/staging')/label/'graphify-out'/staged_name
            if not staged.is_dir(): fail(f'PR107 staged snapshot unavailable: {staged}')
            inventory[str(root/'graphify-out'/published_name)]={p.name:{'sha256':sha(p)} for p in sorted(staged.iterdir()) if p.is_file()}
    actual=preflight.current_snapshot_inventory(GRAPH_ROOTS,expected_count=132)
    if actual!=inventory: fail('current 132 dated snapshot inventory differs from PR107 published baseline')
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        if sha(root/'graphify-out/graph.json')!=pub['corpora'][label]['sha256']: fail(f'{label} graph baseline differs from PR107 receipt')
    wiki={f'wiki/{name}':sha(ROOT/'wiki'/name) for name in WIKI_FILES}
    for name in WIKI_FILES:
        if wiki[f'wiki/{name}']!=pub['wiki_sha256'][f'wiki/{name}']: fail(f'derived wiki baseline differs from PR107 receipt: {name}')
    version=subprocess.check_output([prior['graphify_interpreter'],'-m','graphify','--version'],text=True).strip()
    if version!=prior['graphify_version']: fail('pinned Graphify version mismatch')
    # Reuse the exact PR105 plan and stage routines; change only PR108 identifiers/data.
    helpers=prior['pinned_helpers']
    artifacts={}; metadata={}; backup={}
    graphfiles=tuple(helpers['graph_artifact_names'])
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        gd=root/'graphify-out'; artifacts[label]={}; metadata[label]={}
        for name in graphfiles:
            p=gd/name
            if p.exists(): artifacts[label][name]=sha(p)
        for p in sorted(gd.iterdir()):
            if p.is_dir() or p.name in graphfiles: continue
            if not p.is_file() or p.is_symlink(): fail(f'unexpected graph metadata path: {p}')
            metadata[label][p.name]=sha(p)
        backup[label]=preflight.automatic_backup_condition(gd)
        if not backup[label]['automatic_backup_enabled']: fail(f'automatic raw snapshot disabled for {label}')
    if sha(Path(helpers['pr98_engine']['path']))!=helpers['pr98_engine']['sha256']: fail('pinned PR98 guard engine hash drift')
    engine=load('pr108_guard_engine',Path(helpers['pr98_engine']['path']))
    pins=engine.immutable_pin_snapshot(json.loads(RECEIPT.read_text())) if hasattr(engine,'immutable_pin_snapshot') else None
    if pins is not None and len(pins)!=197: fail('inherited immutable pin count mismatch')
    # Verify protected content and maintained-source inventory with the pinned guard chain.
    oldprior=preflight.PRIOR; oldsha=preflight.PRIOR_SHA
    try:
        # The PR98 engine embeds a preceding PR97 chain; use the PR105 receipt's carried pins above.
        guard=load('pr108_legacy_guard',source/'docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py')
        guard=guard._load_pinned_helper()
        if sha(guard.GUARD)!=guard.GUARD_SHA: fail('pinned host guard hash drift')
        host=load('pr108_host_guard',guard.GUARD)
        maintained=engine.snapshot_identity(host.maintained_source_snapshot())
        if maintained!=prior['maintained_source_snapshot_after']: fail('maintained source inventory drift')
        _,protected,chain=engine.load_previous_helpers()
        protected_hashes=protected.protected_content(host)
        if protected_hashes!=prior['protected_content_sha256']: fail('protected wiki/profile content drift')
    except Exception as exc: fail(f'protected baseline verification failed: {exc}')
    date_today=date.today().isoformat()
    plan={
      'source':str(source),'source_commit':args.commit,'approval_base':APPROVAL_BASE,
      'graph_selection_base':GRAPH_SELECTION_BASE,'pr_url':'https://github.com/gonos2k/Cloud-BAL/pull/108',
      'prior_receipt_sha256':RECEIPT_SHA,'automatic_snapshot_date':date_today,
      'selected_graph_paths':sorted(selected),'selected_source_sha256':{n:sha(source/n) for n in sorted(selected)},
      'hash_only_paths':hash_only,'hash_only_sha256':{n:sha(source/n) for n in hash_only},
      'baseline_graph_artifacts':artifacts,'baseline_graphify_metadata':metadata,
      'graphify_automatic_backup_conditions':backup,'pinned_helpers':helpers,
      'maintained_source_snapshot':prior['maintained_source_snapshot_after'],
      'active250_root_go_snapshot':preflight.active250_root_go_snapshot(),
      'inherited_immutable_pin_count':197,'protected_content_sha256':prior['protected_content_sha256'],
      'prior_forecast':{'cohort':'PR106 H/A/N one-hour requests','state':'INCOMPLETE_CLOSED',
        'evidence_path':str(source/'docs/evidence/pr106_closed_forecast_20261026/closed_verified.json'),
        'evidence_sha256':sha(source/'docs/evidence/pr106_closed_forecast_20261026/closed_verified.json')},
      'new_diagnostic_run':{'arm':'HYDRO','requested_seconds':780,'state':'RUNNER_LAUNCHED_NO_CLOSED_RESULT',
        'evidence_path':str(source/'docs/evidence/pr107_t39_capture_20261026/launch.json'),
        'evidence_sha256':sha(source/'docs/evidence/pr107_t39_capture_20261026/launch.json')},
      'forecast_verdict':'PR106_INCOMPLETE; PR107_DIAGNOSTIC_PENDING',
      'physical_approval':'FAIL_OPEN','observation_skill':'NOT_EVALUATED',
    }
    plan['plan_sha256']=hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (out/'staging').mkdir(parents=True)
    # Existing PR105 routines use preflight constants plus the reviewed plan and output path.
    apply.SNAPSHOT_FILES=('graph.json','GRAPH_REPORT.md','manifest.json')
    preflight.WIKI_FILES=WIKI_FILES
    # Small PR108 finalizer: preserve PR105/PR106 wiki state and update only derived KG pages.
    apply.preflight=preflight
    def finalize(plan_arg,stage_root,stage_maint,build):
        records=build['corpora']
        limits=('Separate KLAPS50 and Cloud-BAL graphs index the PR106 closed-status document plus allowlisted PR108 source/docs/tests; evidence payloads are hash-bound only. '
                'Cross-file Fortran CALL extraction is partial. Graph freshness is navigation evidence, not runtime or scientific approval.')
        for label,directory in (('KLAPS50',stage_root),('Cloud-BAL',stage_maint)):
            report=directory/'graphify-out/GRAPH_REPORT.md'
            content=report.read_text()
            section=(f"## Graph Freshness\n\n- PR108 source `{plan_arg['source_commit']}`; approval base "
                     f"`{APPROVAL_BASE}`; graph-selection base `{GRAPH_SELECTION_BASE}`; "
                     f"{len(plan_arg['selected_graph_paths'])} selected paths.\n- {limits}\n")
            report.write_text(apply.update_graph_freshness(content,section,report))
            mirror='graph-report-klaps50.md' if label=='KLAPS50' else 'graph-report-cloud-bal.md'
            import shutil
            shutil.copy2(report,stage_root/'wiki'/mirror)
            snap=directory/'graphify-out'/SNAPSHOT; snap.mkdir()
            for name in apply.SNAPSHOT_FILES: shutil.copy2(directory/'graphify-out'/name,snap/name)
            records[label]['snapshot']=SNAPSHOT
        idx=stage_root/'wiki/graph-report.md'; lines=idx.read_text().splitlines(); seen=set()
        for i,line in enumerate(lines):
            for label in ('KLAPS50','Cloud-BAL'):
                if line.startswith(f'| {label} |'):
                    row=records[label]; folder='.' if label=='KLAPS50' else 'Cloud-BAL/'
                    mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[i]=(f"| {label} | `{folder}` | {SNAPSHOT} (PR108 input execution contracts) | {row['nodes']} | "
                              f"{row['edges']} | {row['communities']} | [[{mirror}]] |")
                    seen.add(label)
        if seen!={'KLAPS50','Cloud-BAL'}: fail('graph index does not contain exactly both corpora')
        idx.write_text('\n'.join(lines)+'\n')
        page=stage_root/'wiki/index.md'; raw=page.read_bytes(); start=raw.find(b'## Graph snapshot')
        if start<0: fail('wiki index Graph snapshot section missing')
        end=raw.find(b'\n## ',start+3); end=len(raw) if end<0 else end
        section='## Graph snapshot\n\n'+'\n'.join(
          f"- {label}: {SNAPSHOT}; {records[label]['nodes']} nodes / {records[label]['edges']} edges / {records[label]['communities']} communities."
          for label in ('KLAPS50','Cloud-BAL'))+'\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n'
        updated=raw[:start]+section.encode()+raw[end:]
        updated,count=re.subn(rb'(?m)^(date_modified:\s*)[^\r\n]+',lambda m:m.group(1)+date_today.encode(),updated,count=1)
        if count!=1: fail('wiki index date_modified not unique')
        page.write_bytes(updated)
        entry=(f"\n## [{date_today}] kg-update | PR108 input execution contracts\n- Source `{args.commit}`; approval base `{APPROVAL_BASE}`; graph-selection base `{GRAPH_SELECTION_BASE}`.\n")
        for label in ('KLAPS50','Cloud-BAL'):
            r=records[label]; entry+=(f"- {label}: {SNAPSHOT}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; delta nodes={r['delta_nodes']}, edges={r['delta_edges']}.\n")
        entry+=(f"- Maintained-source inventory: 627 entries; inherited immutable pins: 197; active250 ROOTGO source pins: 250 verified. Source review/test evidence remains with the PR108 validation records; this graph update reports extraction only.\n- PR106 H/A/N cohort remains INCOMPLETE; the PR107 T39 diagnostic remains pending with no closed result in its pinned launch observation. Physical approval FAIL_OPEN; observation skill NOT_EVALUATED.\n- Extraction limits: {limits}\n")
        with (stage_root/'wiki/log.md').open('a') as f:f.write(entry)
        return {'corpora':records,'limitations':limits}
    apply.finalize_stage=finalize
    # stage input and extraction through pinned PR105 routines, no maintained-root writes.
    stage_root,stage_maint,build=apply.prepare_stage(plan,out)
    final=apply.finalize_stage(plan,stage_root,stage_maint,build)
    stage_inventory=apply.stage_inventory(stage_root,stage_maint)
    if any(sha(source/n)!=h for n,h in plan['selected_source_sha256'].items()): fail('selected source changed during staging')
    if any(sha(source/n)!=h for n,h in plan['hash_only_sha256'].items()): fail('hash-only evidence changed during staging')
    if preflight.current_snapshot_inventory(GRAPH_ROOTS,expected_count=132)!=actual: fail('maintained dated snapshots changed during staging')
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        if sha(root/'graphify-out/graph.json')!=pub['corpora'][label]['sha256']: fail(f'{label} maintained graph changed during staging')
    for name,h in wiki.items():
        if sha(ROOT/name)!=h: fail(f'maintained wiki changed during staging: {name}')
    if engine.snapshot_identity(host.maintained_source_snapshot())!=prior['maintained_source_snapshot_after']: fail('maintained-source snapshot changed during staging')
    if protected.protected_content(host)!=prior['protected_content_sha256']: fail('protected wiki/profile inventory changed during staging')
    if preflight.active250_root_go_snapshot()!=plan['active250_root_go_snapshot']: fail('active250 ROOTGO pins changed during staging')
    payload={'plan':plan,'build':final,'stage_inventory':stage_inventory,
             'prior_receipt_sha256':RECEIPT_SHA,'baseline_dated_snapshot_count':132,
             'expected_dated_snapshot_count_after_apply':136,
             'staged_raw_dirs':build.get('raw_stage_paths',{})}
    payload['stage_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (out/'stage_receipt.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'STAGE_ONLY_NO_MAINTAINED_WRITES','stage_sha256':payload['stage_sha256'],
                      'output':str(out),'corpora':final['corpora'],'paths':sorted(selected)},indent=2))
if __name__=='__main__': main()
