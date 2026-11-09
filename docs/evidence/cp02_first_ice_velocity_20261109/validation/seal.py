#!/usr/bin/env python3
"""Seal reviewed first-ice code, controlled forecasts and portable evaluation."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=ROOT/'docs/evidence/cp02_first_ice_velocity_20261109'
SOURCES=('tests/test_cp02_first_ice_velocity.py','patches/kdm6_first_ice_velocity.patch')


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(name,status=None):
    path=BUNDLE/name
    require(path.is_file() and not path.is_symlink(),f'unsafe or missing receipt: {name}')
    data=json.loads(path.read_text())
    require(status is None or data.get('status')==status,f'receipt failed: {name}')
    return data


def binding(name,expected):
    path=Path(name)
    require(not path.is_absolute() and '..' not in path.parts,f'unsafe artifact path: {name}')
    path=ROOT/path
    require(path.is_file() and not path.is_symlink() and sha(path)==expected,f'artifact changed: {name}')


def bundle_binding(name,expected):
    binding(str((BUNDLE/name).relative_to(ROOT)),expected)


def verify():
    clean=read('validation/clean_export.json','PASS')
    require(clean['passed']==clean['expected_tests']==479 and clean['exit_code']==0
            and clean['source_inputs_unchanged'] is True,'all479 related tests required')
    for path,expected in clean['guarded_source_input_sha256'].items():binding(path,expected)
    for name in ('evaluate.py','plot.py','cohort_diagnostics.py','test_first_ice_evaluation.py'):
        path=str((BUNDLE/'evaluation'/name).relative_to(ROOT));binding(path,clean['overlay_sha256'][path])
    read('review/final_science_report_review.json','GO')
    for path,expected in read('review/final_science_report_review.json')['sha256'].items():binding(path,expected)
    figures=read('review/figure_gallery_review.json','PASS')
    for path,expected in figures['hashes'].items():bundle_binding(path,expected)
    compare=read('forecast/proof/comparability.json','PASS')
    plan=read('forecast/launch_plan.json','FROZEN_CONTROLLED_SIX_HOUR_PLAN')
    require(compare['plan']['sha256']==sha(BUNDLE/'forecast/launch_plan.json'),'forecast plan changed')
    for path,expected in plan['source_sha256'].items():binding(path,expected)
    require(len(compare['control_history_comparison'])==7 and all(x['byte_equal'] for x in compare['control_history_comparison']),'control7 history equality required')
    require(compare['candidate_initial_history']['byte_equal'] is True,'candidate initial history equality required')
    result=read('evaluation/results/receipt.json','COMPLETE')
    require(result['rows']=={'categorical':144,'continuous':24,'constraints_per_candidate':26,'transitions':48},'score coverage differs')
    require(result['scorer']['sha256']==sha(BUNDLE/'evaluation/evaluate.py'),'executed scorer changed')
    for name,expected in result['outputs'].items():bundle_binding('evaluation/results/'+name,expected)
    verdict=read('evaluation/results/verdict.json')
    require(verdict=={'FIRST_ICE_VELOCITY':{'passed_constraints':21,'required_constraints':26},'CONSERVATIVE_SEDIMENTATION':{'passed_constraints':19,'required_constraints':26}},'reviewed verdict changed')
    recount=read('review/independent_recount.json','PASS')
    require(recount['receipt_sha256']==sha(BUNDLE/'evaluation/results/receipt.json'),'independent recount receipt mismatch')
    require(recount['categorical_rows']==144 and recount['continuous_rows']==24 and recount['transition_rows']==48 and recount['constraints_per_candidate']==26,'independent recount incomplete')
    for folder in ('evaluation/cohorts','figures'):
        receipt=read(folder+('/receipt.json' if folder.endswith('cohorts') else '/maps_metadata.json'))
        if folder=='figures':require(receipt['renderer']['sha256']==sha(BUNDLE/'evaluation/plot.py'),'plot source changed')
        else:require(receipt['source']['sha256']==sha(BUNDLE/'evaluation/cohort_diagnostics.py'),'cohort source changed')
        for name,expected in receipt['outputs'].items():bundle_binding(folder+'/'+name,expected)
    repro=read('validation/reproduction.json','PASS')
    require(repro['byte_identical_count']==len(repro['artifacts'])==20 and repro['portable_tests_passed']==5,'portable replay incomplete')
    require(repro['reproducer_sha256']==sha(BUNDLE/'validation/reproduce.py'),'reproducer changed')
    require(len({r['path'] for r in repro['artifacts']})==20,'duplicate replay coverage')
    for r in repro['artifacts']:
        binding(r['path'],r['sha256']);require((ROOT/r['path']).stat().st_size==r['size_bytes'],'replay size differs')
    tree=read('validation/tree_export.json','PASS')
    require(tree['reproduction_receipt_sha256']==sha(BUNDLE/'validation/reproduction.json'),'tree replay receipt mismatch')
    for path,expected in tree['unchanged_source_and_replayed_artifact_sha256'].items():binding(path,expected)
    prior=read('validation/prior_after_kg_audit.json','PASS_PRIOR_246_AND_INDEX_PRESERVED')
    require(prior['artifact_count']==246,'previous evidence audit incomplete')
    read('kg/stage_review.json','GO');read('kg/publish_receipt.json','PUBLISHED_AND_READBACK_PASS');read('kg/postpublish_copy_receipt.json','PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')
    return {'related_tests':479,'portable_tests':5,'portable_byte_identical_artifacts':20,'categorical_rows':144,'continuous_rows':24,'constraints_per_candidate':26,'candidate_passed':21,'previous_candidate_passed':19,'figures':12,'prior_artifacts':246,'retained_configuration':'B1','qualified':False}


def artifacts():
    paths={ROOT/name for name in SOURCES}
    paths.update(ROOT/name for name in ('README.md','docs/CURRENT_RESEARCH_STATUS.md','docs/CP02_FIRST_ICE_VELOCITY_20261109.md'))
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT/'graphify-out/2026-11-09-first-ice-velocity').glob('*'))
    paths.update(ROOT/'graphify-out'/n for n in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    excluded={BUNDLE/'validation.json',BUNDLE/'validation/final_index_review.json'}
    result=[]
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc','.lock'):continue
        require(path.is_file() and not path.is_symlink(),f'unsafe file: {path}')
        require(path.stat().st_size<100*1024**2,f'artifact exceeds100MiB: {path}')
        with path.open('rb') as stream:require(stream.read(4)!=b'\x7fELF',f'executable must remain external: {path}')
        result.append(path)
    return result


if __name__=='__main__':
    target=BUNDLE/'validation.json'
    require(not target.exists() and not target.is_symlink(),'preserve existing manifest')
    checks=verify()
    rows=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in artifacts()]
    target.write_text(json.dumps({'schema':'cp02_first_ice_velocity_validation_v1','status':'PASS','checks':checks,'artifact_count':len(rows),'artifacts':rows,'excluded_self_referential':['validation.json','validation/final_index_review.json']},indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifact_count':len(rows)}))
