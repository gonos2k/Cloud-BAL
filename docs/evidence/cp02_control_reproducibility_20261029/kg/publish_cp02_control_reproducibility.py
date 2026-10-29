from __future__ import annotations
import hashlib, json, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT=ROOT/'Cloud-BAL'
SOURCE=Path('/var/tmp/cloudbal-cp02-capture-evidence')
STAGE=Path('/var/tmp/cp02_reproducibility_kg_20261029')
KG_DIR=Path('/var/tmp/cloudbal-cp02-capture-evidence/docs/evidence/cp02_control_reproducibility_20261029/kg')
BASELINE_PATH=KG_DIR/'baseline.json'
LOCK_PATH=KG_DIR/'selection_lock.json'
RECEIPT_PATH=KG_DIR/'stage_receipt.json'
ROOT_GO_PATH=KG_DIR/'root_go.json'
SNAPSHOT='2026-10-29-cp02-reproducibility'
WIKI_FILES=('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')
GRAPH_FILES=('graph.json','GRAPH_REPORT.md','manifest.json')
SELECTED_PATHS=('tools/cp02_control_density_comparison.py','tests/test_cp02_control_density_comparison.py',
    'tests/test_cp02_density_evidence.py')
DIAGNOSTIC_KEYS={'missing_endpoint_edges','dangling_endpoint_edges','self_loop_edges','exact_duplicate_edges','same_endpoint_group_count'}


def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok:bool,message:str)->None:
    if not ok: raise RuntimeError(message)
def git_status(path:Path)->list[str]:
    return subprocess.check_output(['git','-C',str(path),'status','--short'],text=True).splitlines()
def dated_inventory(root:Path)->dict:
    inventory={}
    for folder in sorted((root/'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            inventory[folder.name]={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
    return inventory
def status_path(line:str)->str: return line[3:] if len(line)>=4 else line
def filtered_cloud_status(lines:list[str])->list[str]:
    allowed={'graphify-out/graph.json','graphify-out/GRAPH_REPORT.md','graphify-out/manifest.json'}
    return [line for line in lines if status_path(line) not in allowed and not status_path(line).startswith(f'graphify-out/{SNAPSHOT}/')]
def baseline_check(baseline:dict)->None:
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        corpus=baseline['maintained_roots'][label]
        require(sha(root/'graphify-out/graph.json')==corpus['graph_sha256'],f'{label} base graph changed')
        require(dated_inventory(root)==corpus['dated_snapshots'],f'{label} prior dated snapshots changed')
        require(git_status(root)==corpus['git_status_exact'],f'{label} dirty-status baseline changed')
def main()->None:
    baseline=json.loads(BASELINE_PATH.read_text())
    lock=json.loads(LOCK_PATH.read_text())
    receipt=json.loads(RECEIPT_PATH.read_text())
    root_go=json.loads(ROOT_GO_PATH.read_text())
    require(subprocess.check_output(['graphify','--version'],text=True).strip()=='graphify 0.9.53','Graphify must remain pinned at 0.9.53')
    require(root_go.get('go')=='GO','explicit root GO is required')
    require(root_go.get('stage_receipt_sha256')==sha(RECEIPT_PATH),'root GO does not match staged receipt')
    require(sha(RECEIPT_PATH)==root_go.get('stage_receipt_sha256'),'stage receipt hash mismatch')
    require(lock.get('status')=='FROZEN','selected source lock is not frozen')
    require(lock.get('review_status')=='GO','three-path independent science/test review is not GO')
    require(receipt.get('status')=='STAGED_ONLY_NO_MAINTAINED_WRITES','stage is not publishable')
    require(receipt.get('source_commit')==receipt.get('source_base_commit')==lock.get('source_commit')=='8c278b643c5fa2b663f32d2b68d0f59e0301a989','source base mismatch')
    require(set(lock.get('selected_source_sha256',{}))==set(SELECTED_PATHS),'frozen selection paths mismatch')
    require(set(receipt.get('selected_code_paths',[]))==set(SELECTED_PATHS),'stage receipt selected paths mismatch')
    require(receipt.get('final_freeze_id')==lock.get('freeze_id')==root_go.get('freeze_id'),'freeze id mismatch')
    require(receipt.get('snapshot')==SNAPSHOT,'snapshot label mismatch')
    require(receipt.get('selected_source_sha256')==lock.get('selected_source_sha256'),'selected source hashes differ from lock')
    for rel,expected in lock['selected_source_sha256'].items():
        require(sha(SOURCE/rel)==expected,f'frozen code changed: {rel}')
    for rel,expected in receipt['hash_only_changed_sha256'].items():
        require(sha(SOURCE/rel)==expected,f'hash-only source changed: {rel}')
    require(sum(len(c['dated_snapshots']) for c in baseline['maintained_roots'].values())==188,'baseline snapshot count is not 188')
    baseline_check(baseline)
    require(not (ROOT/'graphify-out'/SNAPSHOT).exists() and not (MAINT/'graphify-out'/SNAPSHOT).exists(),'target dated snapshot already exists')

    stage_roots={'KLAPS50':STAGE/'KLAPS50','Cloud-BAL':STAGE/'Cloud-BAL'}
    for label in ('KLAPS50','Cloud-BAL'):
        graph_dir=stage_roots[label]/'graphify-out'
        corpus=receipt['corpora'][label]
        require(set(corpus.get('snapshot_file_hashes',{}))==set(GRAPH_FILES),f'{label} snapshot hash schema mismatch')
        require(set(corpus.get('diagnostic_verified_zero_counts',{}))==DIAGNOSTIC_KEYS,f'{label} diagnostic receipt schema mismatch')
        require(all(value==0 for value in corpus['diagnostic_verified_zero_counts'].values()),f'{label} graph diagnostics are not clean')
        for filename in GRAPH_FILES:
            expected=corpus['snapshot_file_hashes'][filename]
            require(sha(graph_dir/filename)==expected,f'{label} staged {filename} hash mismatch')
            require(sha(graph_dir/SNAPSHOT/filename)==expected,f'{label} staged snapshot {filename} hash mismatch')
        graph=json.loads((graph_dir/'graph.json').read_text())
        require(len(graph['nodes'])==corpus['nodes'],f'{label} staged node count mismatch')
        require(len(graph.get('links',graph.get('edges',[])))==corpus['edges'],f'{label} staged edge count mismatch')

    wiki_stage=STAGE/'wiki'
    current_log=(ROOT/'wiki/log.md').read_text()
    staged_log=(wiki_stage/'log.md').read_text()
    require(staged_log.startswith(current_log),'maintained wiki log changed after stage')
    require(len(staged_log)>len(current_log),'staged wiki log has no appended entry')
    require(sha(wiki_stage/'graph-report-klaps50.md')==receipt['corpora']['KLAPS50']['report_sha256'],'KLAPS50 wiki report differs from staged graph report')
    require(sha(wiki_stage/'graph-report-cloud-bal.md')==receipt['corpora']['Cloud-BAL']['report_sha256'],'Cloud-BAL wiki report differs from staged graph report')
    for name in WIKI_FILES: require((wiki_stage/name).is_file(),f'missing staged wiki file {name}')

    backup=STAGE/'apply_backup'
    require(not backup.exists(),'apply backup already exists; refusing second application')
    backup.mkdir()
    targets=[]
    for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        gd=root/'graphify-out'; sd=stage_roots[label]/'graphify-out'
        targets.extend((sd/name,gd/name) for name in GRAPH_FILES)
    targets.extend((wiki_stage/name,ROOT/'wiki'/name) for name in WIKI_FILES)
    for _,target in targets:
        key=hashlib.sha256(str(target).encode()).hexdigest()
        shutil.copy2(target,backup/key)
    (backup/'index.json').write_text(json.dumps({hashlib.sha256(str(target).encode()).hexdigest():str(target) for _,target in targets},indent=2,sort_keys=True)+'\n')

    created=[]
    try:
        for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            gd=root/'graphify-out'; sd=stage_roots[label]/'graphify-out'
            for name in GRAPH_FILES: shutil.copy2(sd/name,gd/name)
            destination=gd/SNAPSHOT; destination.mkdir(); created.append(destination)
            for name in GRAPH_FILES: shutil.copy2(sd/SNAPSHOT/name,destination/name)
        for name in WIKI_FILES: shutil.copy2(wiki_stage/name,ROOT/'wiki'/name)

        readback={}
        for label,root in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            corpus=receipt['corpora'][label]
            gd=root/'graphify-out'; graph=json.loads((gd/'graph.json').read_text())
            require(len(graph['nodes'])==corpus['nodes'],f'{label} published node count mismatch')
            require(len(graph.get('links',graph.get('edges',[])))==corpus['edges'],f'{label} published edge count mismatch')
            for name in GRAPH_FILES:
                expected=corpus['snapshot_file_hashes'][name]
                require(sha(gd/name)==expected and sha(gd/SNAPSHOT/name)==expected,f'{label} graph readback mismatch: {name}')
            inventory=dated_inventory(root); old=baseline['maintained_roots'][label]['dated_snapshots']
            require({k:v for k,v in inventory.items() if k!=SNAPSHOT}==old,f'{label} prior snapshots changed')
            require(inventory[SNAPSHOT]==corpus['snapshot_file_hashes'],f'{label} snapshot inventory mismatch')
            require(len(inventory)==len(old)+1,f'{label} dated snapshot count mismatch')
            readback[label]={'nodes':len(graph['nodes']),'edges':len(graph.get('links',graph.get('edges',[]))),'communities':len({n.get('community') for n in graph['nodes'] if n.get('community') is not None}),'graph_sha256':sha(gd/'graph.json'),'prior_snapshots_preserved':len(old),'new_snapshot':SNAPSHOT,'new_snapshot_files':inventory[SNAPSHOT]}
        for name in WIKI_FILES: require(sha(ROOT/'wiki'/name)==sha(wiki_stage/name),f'wiki readback mismatch: {name}')
        require(git_status(ROOT)==baseline['maintained_roots']['KLAPS50']['git_status_exact'],'KLAPS50 dirty status changed')
        require(filtered_cloud_status(git_status(MAINT))==filtered_cloud_status(baseline['maintained_roots']['Cloud-BAL']['git_status_exact']),'Cloud-BAL unrelated dirty status changed')
    except Exception:
        for destination in created:
            if destination.exists(): shutil.rmtree(destination)
        for _,target in targets:
            shutil.copy2(backup/hashlib.sha256(str(target).encode()).hexdigest(),target)
        raise

    result={'status':'PUBLISHED_AND_READBACK_PASSED','root_go':root_go['go'],'root_go_stage_receipt_sha256':root_go['stage_receipt_sha256'],'frozen_lock_id':lock['freeze_id'],'snapshot':SNAPSHOT,'applied_at_utc':datetime.now(timezone.utc).isoformat(),'stage_receipt_sha256':sha(RECEIPT_PATH),'source_selected_hashes':receipt['selected_source_sha256'],'hash_only_changed_paths':receipt['hash_only_changed_paths'],'corpora':readback,'wiki_files':{name:sha(ROOT/'wiki'/name) for name in WIKI_FILES},'preservation':{'prior_dated_snapshots_total':188,'KLAPS50_prior_snapshots_preserved':92,'Cloud-BAL_prior_snapshots_preserved':96,'unrelated_dirty_state':'preserved; Cloud-BAL status may additionally show scoped graph files and new snapshot'},'diagnostics':{label:receipt['corpora'][label]['diagnostic_verified_zero_counts'] for label in ('KLAPS50','Cloud-BAL')},'validation_scope':'selected CP02 control density comparison tool and focused tests; graph freshness is not runtime, physical approval, or scientific validation'}
    (KG_DIR/'apply_receipt.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
