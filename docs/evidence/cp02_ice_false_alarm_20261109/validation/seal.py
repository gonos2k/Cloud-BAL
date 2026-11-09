#!/usr/bin/env python3
"""Seal reviewed false-alarm diagnostics; no new forecast or adoption is implied."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
B=ROOT/'docs/evidence/cp02_ice_false_alarm_20261109'
SOURCES=('tools/cp02_ice_false_alarm.py','tools/cp02_ice_surface_components.py','tools/plot_cp02_ice_false_alarm.py','tests/test_cp02_ice_false_alarm.py','tests/test_cp02_ice_surface_components.py')


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(name,status=None):
    path=B/name;require(path.is_file() and not path.is_symlink(),'unsafe receipt: '+name);r=json.loads(path.read_text())
    require(status is None or r.get('status')==status,'receipt not ready: '+name);return r


def bind(name,digest):
    p=Path(name);require(not p.is_absolute() and '..' not in p.parts,'unsafe artifact path');p=ROOT/p
    require(p.is_file() and not p.is_symlink() and sha(p)==digest,'artifact changed: '+name)


def verify():
    clean=read('validation/clean_export.json','PASS')
    require(clean['passed']==clean['expected_tests']==488 and clean['exit_code']==0 and clean['source_inputs_unchanged'],'related488-test validation required')
    for name in SOURCES:bind(name,clean['overlay_sha256'][name])
    for name,expected in clean['guarded_source_input_sha256'].items():bind(name,expected)
    for folder in ('cohorts','surface/native','figures'):
        r=read(folder+'/receipt.json','COMPLETE')
        for name,expected in r['outputs'].items():bind(str((B/folder/name).relative_to(ROOT)),expected)
    require(read('surface/native/receipt.json')['rows']==88512,'native coverage differs')
    native=read('surface/native/receipt.json');require(native['mode']=='native' and native['max_component_sum_rounding_mm']<1e-10,'native component verification missing')
    sources=[r for r in native['inputs'] if r['path']==str(ROOT/'tools/cp02_ice_surface_components.py')]
    require(len(sources)==1 and sources[0]['sha256']==sha(ROOT/'tools/cp02_ice_surface_components.py'),'native executed source missing or changed')
    summary=read('cohorts/summary.json');require(summary['cohorts']=={'persistent':65,'new':26,'resolved':37} and summary['candidate_admission']=={'passed':21,'required':26},'frozen sets or verdict changed')
    for name in ('review/final_science_figure_review.json','review/final_gallery_review.json'):
        r=read(name,'GO');require(r['sha256'],'review lacks bound artifacts')
        for path,digest in r['sha256'].items():bind(path,digest)
    read('review/independent_recount.json','PASS')
    replay=read('validation/reproduction.json','PASS')
    require(replay['byte_identical_count']==len(replay['artifacts'])==12 and replay['portable_tests_passed']==9,'portable replay incomplete')
    require(replay['reproducer_sha256']==sha(B/'validation/reproduce.py'),'reproducer changed')
    require(len({r['path'] for r in replay['artifacts']})==12,'duplicate replay artifact')
    for r in replay['artifacts']:bind(r['path'],r['sha256']);require((ROOT/r['path']).stat().st_size==r['size_bytes'],'replay artifact size differs')
    tree=read('validation/tree_export.json','PASS');require(tree['reproduction_receipt_sha256']==sha(B/'validation/reproduction.json'),'tree replay receipt differs')
    for name,digest in tree['unchanged_source_and_replayed_artifact_sha256'].items():bind(name,digest)
    prior=read('validation/prior_after_kg_audit.json','PASS_PRIOR_189_AND_INDEX_PRESERVED');require(prior['artifact_count']==189,'prior artifact audit incomplete')
    read('kg/stage_review.json','GO');read('kg/publish_receipt.json','PUBLISHED_AND_READBACK_PASS');read('kg/postpublish_copy_receipt.json','PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')
    return {'related_tests':488,'new_tests':9,'portable_byte_identical_artifacts':12,'component_rows':88512,'new_figures':4,'reused_figures':12,'prior_artifacts':189,'new_forecast':False,'candidate_admission':{'passed':21,'required':26},'retained_configuration':'B1'}


def artifacts():
    paths={ROOT/p for p in SOURCES}
    paths.update(ROOT/p for p in ('README.md','docs/CURRENT_RESEARCH_STATUS.md','docs/CP02_ICE_FALSE_ALARM_20261109.md'))
    paths.update(p for p in B.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT/'graphify-out/2026-11-09-ice-false-alarm').glob('*'))
    paths.update(ROOT/'graphify-out'/p for p in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    excluded={B/'validation.json',B/'review/final_index_review.json'}
    result=[]
    for p in sorted(paths):
        if p in excluded or '__pycache__' in p.parts or p.suffix in ('.pyc','.lock'):continue
        require(p.is_file() and not p.is_symlink(),'unsafe artifact: '+str(p));require(p.stat().st_size<100*1024**2,'artifact over100MiB')
        with p.open('rb') as f:require(f.read(4)!=b'\x7fELF','ELF must remain external')
        result.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'size_bytes':p.stat().st_size})
    return result


if __name__=='__main__':
    out=B/'validation.json';require(not out.exists() and not out.is_symlink(),'preserve existing manifest');checks=verify();rows=artifacts()
    out.write_text(json.dumps({'status':'PASS','schema':'cp02_ice_false_alarm_validation_v1','checks':checks,'artifact_count':len(rows),'artifacts':rows,'excluded_self_referential':['validation.json','review/final_index_review.json']},indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifact_count':len(rows)}))
