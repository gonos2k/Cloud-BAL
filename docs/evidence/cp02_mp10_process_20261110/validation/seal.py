#!/usr/bin/env python3
"""Seal the reviewed MP10 diagnostics without changing a forecast decision."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
B=ROOT/'docs/evidence/cp02_mp10_process_20261110'
SOURCES=('tools/cp02_mp10_failure_cohorts.py','tests/test_cp02_mp10_failure_cohorts.py',
         'tools/cp02_mp10_process.py','tests/test_cp02_mp10_process.py','tools/plot_cp02_mp10_process.py')
REPORT='docs/CP02_MP10_PROCESS_20261110.md'


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def bind(name,expected):
    path=Path(name)
    if not path.is_absolute():
        require('..' not in path.parts,'unsafe path');path=ROOT/path
    require(path.is_file() and not path.is_symlink() and sha(path)==expected,'changed file: '+str(path))


def receipt(name,status):
    value=json.loads((B/name).read_text())
    require(value.get('status')==status,'incomplete receipt: '+name)
    return value


def verify():
    clean=receipt('validation/clean_export.json','PASS')
    require(clean['expected_tests']==clean['passed']==529 and clean['test_files']==87 and
            clean['exit_code']==0 and clean['source_inputs_unchanged'],'related test scope differs')
    for name in SOURCES:bind(name,clean['overlay_sha256'][name])
    for name,digest in clean['guarded_source_input_sha256'].items():bind(name,digest)
    for folder in ('cohorts','surface/results','analysis','figures','science/results'):
        item=receipt(folder+'/receipt.json','COMPLETE')
        for name,digest in item['outputs'].items():bind(B/folder/name,digest)
    analysis=json.loads((B/'analysis/summary.json').read_text())
    require(analysis['points']==30 and analysis['columns']==111 and analysis['levels']==39,'analysis scope differs')
    require(analysis['public_ledger_rows']==52650 and analysis['native_operator_rows']==7920,'analysis rows differ')
    require(analysis['core_vapor_temperature_updates_bitwise_replayed']=={'CONTROL':2337660,'MP10':4675320},
            'core update replay scope differs')
    proof=receipt('native/proof/comparability.json','PASS')
    require(proof['schema']=='cp02_mp10_process_comparability_v1' and set(proof['arms'])=={'CONTROL','MP10'},'native proof scope differs')
    for key,path in (('source_receipt_sha256','native/source/source_receipt.json'),
                     ('schema_sha256','native/schema/schema.json'),
                     ('selector_sha256','cohorts/native_columns.csv'),
                     ('postrun_review_sha256','review/compact_v2_go.json')):
        bind(B/path,proof[key])
    for path,digest in proof['reviewed_script_sha256'].items():bind(path,digest)
    for arm,item in proof['arms'].items():
        require(len(item['history7byte_equal'])==7 and all(r['byte_equal'] for r in item['history7byte_equal']),
                'history comparison incomplete')
        bind(B/'native/compact'/arm/'capture_receipt.json',item['capture_receipt_sha256'])
        bind(B/'native/compact'/arm/'raw_recount_receipt.json',item['raw_recount_sha256'])
        bind(B/'native/packed'/arm/'packing_receipt.json',item['packing_receipt_sha256'])
        bind(B/'native/compact'/arm/'surface_audit.json',item['surface_audit_sha256'])
        bind(B/'native/compact'/arm/'relocation_receipt.json',item['relocation_receipt_sha256'])
    verdict=json.loads((ROOT/'docs/evidence/cp02_pulse_path_20261110/evaluation/results/verdict.json').read_text())
    require(verdict['MP10']=={'passed_constraints':22,'required_constraints':26},'frozen candidate verdict differs')
    require('<!-- 실제 전체 자료 분석 완료 후 수치 결과 추가 -->' not in (ROOT/REPORT).read_text(),'report still draft')
    replay=receipt('validation/tree_replay_receipt.json','PASS')
    require(replay['focused_tests_passed']==15 and replay['shared_index_unchanged'],'replay scope/index differs')
    require({name:len(files) for name,files in replay['byte_identical_outputs'].items()}==
            {'cohorts':6,'analysis':12,'figures':16,'science':2,'surface':1},'replay output coverage differs')
    require(len([p for p in (B/'figures').glob('*.png')])==7,'figure scope differs')
    bind(B/'validation/tree_replay.py',replay['replay_script']['sha256'])
    for name,item in replay['overlay_files'].items():bind(name,item['sha256'])
    for name in ('final_review.json','independent_kg_review.json'):
        review=json.loads((B/'review'/name).read_text())
        require(review.get('status') in ('PASS','PASS_WITH_LIMITATIONS','PASS_SOURCE_AND_EVIDENCE_REVIEW'),'review incomplete')
        for path,digest in review.get('inputs',{}).items():bind(path,digest)
    require(json.loads((B/'kg/stage_review.json').read_text())['status']=='GO','KG stage not reviewed')
    require(json.loads((B/'kg/publish_receipt.json').read_text())['status']=='PUBLISHED_AND_READBACK_PASS','KG not published')
    return {'related_tests':529,'new_focused_tests':15,'points':30,'native_columns':111,'levels':39,
            'history_byte_identical':14,'core_updates_bitwise_replayed':analysis['core_vapor_temperature_updates_bitwise_replayed'],
            'candidate':'MP10','admission':verdict['MP10'],'decision':'NOT_ADOPTED_RETAIN_B1',
            'global_water_energy_budget_closed':False,'scope':replay['scope']}


def artifacts():
    paths={ROOT/name for name in (*SOURCES,'README.md','docs/CURRENT_RESEARCH_STATUS.md',REPORT)}
    paths.update(p for p in B.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT/'graphify-out/2026-11-10-mp10-process').glob('*'))
    paths.update(ROOT/'graphify-out'/n for n in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    excluded={B/'validation.json',B/'review/final_index_review.json'}
    result=[]
    for p in sorted(paths):
        if p in excluded or '__pycache__' in p.parts or p.suffix in ('.pyc','.lock'):continue
        require(p.is_file() and not p.is_symlink(),'unsafe artifact '+str(p))
        require(p.stat().st_size<100*1024**2,'artifact exceeds100MiB')
        with p.open('rb') as stream:require(stream.read(4)!=b'\x7fELF','ELF must remain external')
        result.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'size_bytes':p.stat().st_size})
    return result


if __name__=='__main__':
    output=B/'validation.json'
    require(not output.exists() and not output.is_symlink(),'preserve manifest')
    checks=verify();rows=artifacts()
    output.write_text(json.dumps({'status':'PASS','schema':'cp02_mp10_process_validation_v1','checks':checks,
                                 'artifact_count':len(rows),'artifacts':rows,
                                 'excluded_self_referential':['validation.json','review/final_index_review.json']},indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifact_count':len(rows)}))
