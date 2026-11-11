#!/usr/bin/env python3
"""Seal tested sources, reviewed evidence and separately dated graph artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[4]
B=Path('docs/evidence/moment_feasibility_20261111')
K=B/'kg'
STAMP='2026-11-11-moment-feasibility'
MANIFEST=B/'ARTIFACT_MANIFEST.json'
INDEX_REVIEW=B/'review/final_index_review.json'
EXPECTED={
 'src/common/cloud_bal_microphysics_initialization.f90', 'src/common/cloud_bal_phase_moments.f90',
 'tools/initialize_model_moments.py','tools/model_moment_driver.f90','tools/plot_moment_feasibility.py',
 'tests/test_initialize_model_moments.py','tests/test_microphysics_initialization.f90',
 'tests/test_phase_consumer_native.f90','tests/test_phase_initialization_chain.f90',
 'tests/test_phase_moments.f90','tests/source_extract_phase_consumer.py'}


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def require(condition,message):
    if not condition: raise ValueError(message)


def read(path,status=None):
    path=ROOT/path
    require(path.is_file() and not path.is_symlink(),f'missing or unsafe receipt: {path}')
    value=json.loads(path.read_text())
    if status is not None:require(value.get('status')==status,f'incorrect status: {path}')
    return value


def bind(path,digest):
    path=Path(path)
    require(not path.is_absolute() and '..' not in path.parts,f'unsafe path: {path}')
    path=ROOT/path
    require(path.is_file() and not path.is_symlink() and sha(path)==digest,f'changed or missing: {path}')


def checked_map(mapping):
    require(isinstance(mapping,dict) and bool(mapping),'empty hash map')
    for path,digest in mapping.items():bind(path,digest)


def main():
    output=ROOT/MANIFEST
    require(not output.exists() and not output.is_symlink(),'manifest already exists')
    validation=read(B/'validation/validation_receipt.json','PASS')
    checked_map(validation['source_sha256'])
    require(EXPECTED <= set(validation['source_sha256']),'tested source scope incomplete')
    require(set(validation['commands'])=={'unit','boundary','figures'},'validation commands differ')
    for result in validation['commands'].values():
        require(result['exit_code']==0,'validation command failed')
        bind(result['log'],result['log_sha256'])
    for name,digest in validation['exact_figure_outputs'].items():bind(B/'figures'/name,digest)
    temperature=read(B/'review/temperature_independent_review.json')
    require(temperature.get('result')=='pass' and temperature.get('findings')==[], 'independent review failed')
    checked_map(temperature['sha256'])
    source=read(K/'source_review.json','PASS_SOURCE_REVIEW_WITH_BROAD_VALIDATION_PENDING')
    lock=read(K/'selection_lock.json','FROZEN')
    require(lock['snapshot']==STAMP and set(lock['selected_source_sha256'])==EXPECTED,'KG selection differs')
    require(source['selection_lock_sha256']==sha(ROOT/K/'selection_lock.json') and
            source['source_sha256']==lock['selected_source_sha256'] and
            source['hash_only_sha256']==lock['hash_only_sha256'],'source review/selection mismatch')
    for path,digest in lock['selected_source_sha256'].items():
        require(validation['source_sha256'].get(path)==digest,f'unvalidated selected source: {path}')
    checked_map(lock['selected_source_sha256']);checked_map(lock['hash_only_sha256'])
    stage=read(K/'stage_receipt.json','STAGED_ONLY_NO_MAINTAINED_WRITES')
    require(stage['snapshot']==STAMP and stage['selection_lock_sha256']==sha(ROOT/K/'selection_lock.json') and
            stage['selected_source_sha256']==lock['selected_source_sha256'],'KG stage differs')
    require(stage['final_validation_sha256']==sha(ROOT/B/'validation/validation_receipt.json') and
            stage['source_review_sha256']==sha(ROOT/K/'source_review.json'),'KG final validation binding differs')
    stage_review=read(K/'stage_review.json','GO')
    require(stage_review['stage_receipt_sha256']==sha(ROOT/K/'stage_receipt.json') and
            stage_review['selection_lock_sha256']==sha(ROOT/K/'selection_lock.json') and
            stage_review['checks'] and all(stage_review['checks'].values()),'KG stage review differs')
    prior=read(K/'prior_audit.json','PASS_PRIOR_104_GIT_BLOBS_AND_INDEX')
    require(prior['artifact_count']==104 and prior['maintained_roots_written'] is False,'prior audit differs')
    bind('docs/evidence/physical_moment_handoff_20261110/validation.json',prior['manifest_sha256'])
    bind('docs/evidence/physical_moment_handoff_20261110/review/final_index_review.json',prior['final_index_sha256'])
    publication=read(K/'publish_receipt.json','PUBLISHED_AND_READBACK_PASS')
    require(publication['snapshot']==STAMP and publication['prior_snapshot_count']==266 and
            publication['new_maintained_snapshot_count']==268,'KG publication counts differ')
    require(publication['selection_lock_sha256']==sha(ROOT/K/'selection_lock.json') and
            publication['stage_review_sha256']==sha(ROOT/K/'stage_review.json'),'KG publication pins differ')
    copied=read(K/'source_copy_receipt.json','COPIED_AND_READBACK_PASS')
    require(copied['publish_receipt_sha256']==sha(ROOT/K/'publish_receipt.json'),'KG copy receipt differs')
    for entry in publication['targets']:
        path=Path(entry['path'])
        require(path.is_absolute() and path.is_file() and not path.is_symlink() and sha(path)==entry['sha256'],
                f'published target changed: {path}')
    post=read(K/'postpublish_independent_review.json','GO')
    require(post['publish_receipt_sha256']==sha(ROOT/K/'publish_receipt.json') and
            post['source_copy_receipt_sha256']==sha(ROOT/K/'source_copy_receipt.json') and
            post['prior_snapshot_count']==266 and post['current_snapshot_count']==268 and
            post['checks'] and all(post['checks'].values()),'KG independent readback differs')
    package=read(B/'validation/figure_package_receipt.json','PASS')
    checked_map(package['source_sha256'])
    archive=ROOT/B/'all_figures.zip'
    require(sha(archive)==package['zip_sha256'],'figure package changed')
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None and set(z.namelist())==set(package['members_sha256']),'figure archive differs')
        for name,digest in package['members_sha256'].items():
            require(hashlib.sha256(z.read(name)).hexdigest()==digest,f'archive member differs: {name}')
    changed=subprocess.check_output(['git','diff','--name-only','-z','HEAD'],cwd=ROOT).split(b'\0')
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    paths={Path(x.decode()) for x in changed+untracked if x}
    paths.update(p.relative_to(ROOT) for p in (ROOT/B).rglob('*') if p.is_file() or p.is_symlink())
    paths.update(Path('graphify-out')/name for name in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    paths.update(Path('graphify-out')/STAMP/name for name in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    paths.discard(MANIFEST);paths.discard(INDEX_REVIEW)
    paths=sorted(p for p in paths if '__pycache__' not in p.parts and p.suffix not in ('.pyc','.lock'))
    require(EXPECTED <= {str(p) for p in paths},'expected source missing from manifest')
    records={}
    for name in paths:
        path=ROOT/name
        require(path.is_file() and not path.is_symlink(),f'unsupported artifact: {name}')
        records[str(name)]={'sha256':sha(path),'bytes':path.stat().st_size,
                            'mode':'100755' if path.stat().st_mode & 0o111 else '100644'}
    receipt={'status':'PASS','base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'artifacts':records,'excluded':[str(MANIFEST),str(INDEX_REVIEW)],
             'scope':'Tested implementation, reviewed scientific evidence and dated graphs; no WRF forecast or first-use claim.'}
    with output.open('x') as f:f.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifacts':len(records)}))

if __name__=='__main__':main()
