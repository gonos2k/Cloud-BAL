#!/usr/bin/env python3
"""Seal the reviewed activation-path evidence; this does not validate WRF science."""
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
B = ROOT/'docs/evidence/cp02_activation_path_20261110'
SOURCES = ('tools/cp02_activation_path.py','tools/cp02_weak_activation.py','tools/plot_cp02_activation_path.py',
           'tests/test_cp02_activation_path.py','tests/test_cp02_weak_activation.py')
REPORT = 'docs/CP02_ACTIVATION_PATH_20261110.md'
STAMP = '2026-11-10-activation-path'

def require(ok,message):
    if not ok: raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def bind(path,digest):
    path=Path(path)
    if not path.is_absolute():
        require('..' not in path.parts,'unsafe path');path=ROOT/path
    require(path.is_file() and not path.is_symlink() and sha(path)==digest,'changed or absent: '+str(path))

def receipt(name,status):
    value=json.loads((B/name).read_text())
    require(value.get('status')==status,'incomplete receipt: '+name)
    return value

def outputs(folder,status):
    item=receipt(folder+'/receipt.json',status)
    require(bool(item.get('outputs')),'empty output receipt: '+folder)
    for record in item.get('inputs',[]):bind(record['path'],record['sha256'])
    for name,digest in item['outputs'].items(): bind(B/folder/name,digest if isinstance(digest,str) else digest['sha256'])
    return item

def csv_rows(name):
    with (B/name).open(newline='') as f:return list(csv.DictReader(f))

def verify():
    clean=receipt('validation/clean_export.json','PASS')
    require((clean['expected_tests'],clean['passed'],clean['test_files'],clean['exit_code'])==(545,545,90,0) and clean['source_inputs_unchanged'],'clean test scope differs')
    for name in SOURCES:bind(name,clean['overlay_sha256'][name])
    for path,digest in clean['guarded_source_input_sha256'].items():bind(path,digest)
    historical=outputs('analysis','PASS')
    require(historical['points']==[12446,12892,9774,12300] and historical['steps']==list(range(982,991)) and historical['k']==16 and historical['native_rows']==432 and historical['paired_rows']==36,'historical scope differs')
    require(len(csv_rows('analysis/native_loops.csv'))==432 and len(csv_rows('analysis/paired_weighted.csv'))==36,'historical row count differs')
    outputs('weak_analysis','COMPLETE'); weak=receipt('weak_analysis/summary.json','COMPLETE')
    require((weak['points'],weak['columns'],weak['levels'],weak['steps'],weak['public_ledger_rows'],weak['surface_checks'])==(3,8,39,[361,540],1755,6),'weak scope differs')
    require(weak['native_activation_pairs']=={'CONTROL':56160,'MP10':112320},'weak loop coverage differs')
    require(len(csv_rows('weak_analysis/public_ledger.csv'))==1755 and len(csv_rows('weak_analysis/surface_check.csv'))==6,'weak row count differs')
    native=receipt('native/proof/comparability.json','PASS')
    require(native['schema']=='cp02_activation_weak_comparability_v1' and set(native['arms'])=={'CONTROL','MP10'},'native scope differs')
    for key,path in (('schema_sha256','native/schema/schema.json'),('source_receipt_sha256','native/source/source_receipt.json'),('selector_sha256','cohorts/native_columns.csv'),('mapping_receipt_sha256','cohorts/mapping_receipt.json'),('selected_points_sha256','cohorts/selected_points.csv'),('supplement_sha256','native/schema/contract_supplement.json')):bind(B/path,native[key])
    for arm,item in native['arms'].items():
        histories=item['history4byte_equal']
        require(len(histories)==4 and all(x['exact'] is True and x['actual_sha256']==x['reference_sha256'] for x in histories),'native history parity differs')
        for key,path in (('capture_receipt_sha256',f'native/compact/{arm}/capture_receipt.json'),('raw_recount_sha256',f'native/compact/{arm}/raw_recount_receipt.json'),('packing_receipt_sha256',f'native/packed/{arm}/packing_receipt.json'),('surface_audit_sha256',f'native/compact/{arm}/surface_audit.json'),('shared_comparison_sha256',f'native/proof/{arm}/run_shared_comparison.json'),('history_comparison_sha256',f'native/proof/{arm}/run_history_comparison.json')):bind(B/path,item[key])
    local=receipt('local_replay/results/receipt.json','PASS');require(local['row_count']==12 and len(csv_rows('local_replay/results/comparisons.csv'))==12,'local comparison scope differs')
    bind(B/'local_replay/results/comparisons.csv',local['comparisons_sha256'])
    require(set(local['inputs'])=={'synthetic','control_nonbinding','mp10_nonbinding','mp10_binding'},'local input scope differs')
    for name,item in local['inputs'].items():bind(B/'local_replay/results'/(name+'.log'),item['log_sha256'])
    recount=receipt('local_replay/portable_recount_receipt.json','PASS')
    require((recount['loop1_words'],recount['loop2_words'])==(86,24) and len(recount['phases'])==8,'portable bit coverage differs')
    for item in recount['inputs']:bind(item['path'],item['sha256'])
    candidate=receipt('forecast/proof/comparability.json','PASS')
    require(candidate['schema']=='cp02_nn_end_forecast_comparability_v1' and candidate['unchanged_inputs'] is True and len(candidate['histories'])==7 and candidate['initial_history_sha256']==candidate['initial_reference_sha256'],'candidate proof differs')
    for key,path in (('candidate_source_sha256','forecast/source/MP10_NN_END.f90'),('policy_sha256','forecast/policy.json'),('build_receipt_sha256','forecast/proof/records/build_build_receipt.json'),('probe_receipt_sha256','forecast/proof/records/probe_probe_receipt.json'),('prepared_sha256','forecast/proof/records/run_prepared.json'),('run_receipt_sha256','forecast/proof/records/run_run_receipt.json'),('finite_sanity_sha256','forecast/proof/finite_sanity.json')):bind(B/path,candidate[key])
    prepared=json.loads((B/'forecast/proof/records/run_prepared.json').read_text());run=json.loads((B/'forecast/proof/records/run_run_receipt.json').read_text())
    require(len(prepared['inputs'])==89 and run['inputs_after']==prepared['inputs'] and run['status']=='PASS' and run['exit_code']==0,'candidate 89 inputs/run differ')
    candidate_dir=Path(candidate['histories'][0]['path']).parent
    for name,digest in prepared['inputs'].items():bind(candidate_dir/name,digest)
    finite=receipt('forecast/proof/finite_sanity.json','PASS');require(len(finite['fields'])==11 and len(set(finite['fields']))==11 and len(finite['histories'])==7,'finite field scope differs')
    for history,proof in zip(finite['histories'],candidate['histories']):
        require(history['name']==Path(proof['path']).name and history['sha256']==proof['sha256'] and set(history['fields'])==set(finite['fields']) and all(v['nonfinite']==0 and v['values']>0 for v in history['fields'].values()),'finite proof differs')
        bind(proof['path'],proof['sha256'])
    evaluation=outputs('evaluation/results','COMPLETE')
    require(evaluation['policy_sha256']==candidate['policy_sha256'] and evaluation['prior_score_rows']=='all 180 categorical and 30 continuous rows unchanged','evaluation source/prior differs')
    sizes={'categorical_scores.csv':216,'continuous_scores.csv':36,'weak_bands.csv':108,'false_alarm_transitions.csv':72,'admission_constraints.csv':26}
    for file,n in sizes.items():require(len(csv_rows('evaluation/results/'+file))==n,'score coverage differs: '+file)
    gates=csv_rows('evaluation/results/admission_constraints.csv');protection=[r for r in gates if r['goal']=='protection'];recovery=[r for r in gates if r['goal']=='recovery']
    require((len(protection),len(recovery))==(11,15) and (sum(r['satisfied']=='True' for r in protection),sum(r['satisfied']=='True' for r in recovery))==(9,12),'gate verdict differs')
    for row in gates:
        a=Fraction(int(row['candidate_hit']),int(row['candidate_denominator']));b=Fraction(int(row['baseline_hit']),int(row['baseline_denominator']))
        require((row['satisfied']=='True')==(a>=b),'fraction comparison differs')
    verdict=json.loads((B/'evaluation/results/verdict.json').read_text())
    require(verdict['passed']==21 and verdict['required']==26 and verdict['all_gates_pass'] is False and 'B1 remains' in verdict['selection'],'candidate decision differs')
    for folder,count in (('figures',8),('evaluation/figures',7),('evaluation/supplementary_figures',12)):
        item=outputs(folder,'COMPLETE');require(len(list((B/folder).glob('*.png')))==count and len([x for x in item['outputs'] if x.endswith('.png')])==count,'figure coverage differs')
    gallery=receipt('gallery_receipt.json','PASS');require(gallery['figure_count']==27 and gallery['zip_crc']=='PASS' and gallery['local_and_archive_links']=='PASS' and len(gallery['members'])==55,'gallery coverage differs')
    bind(B/'FIGURES.md',gallery['gallery_sha256']);bind(REPORT,gallery['report_sha256']);bind(B/'all_figures.zip',gallery['archive_sha256'])
    with zipfile.ZipFile(B/'all_figures.zip') as archive:
        require(archive.testzip() is None and set(archive.namelist())==set(gallery['members']),'archive members/CRC differ')
        for name,info in gallery['members'].items():
            bind(name,info['sha256']);data=archive.read(name)
            require(len(data)==info['size_bytes'] and hashlib.sha256(data).hexdigest()==info['sha256'],'archive content differs: '+name)
    replay=receipt('validation/tree_replay_receipt.json','PASS')
    require(replay['focused_tests_passed']==16 and replay['shared_index_unchanged'] is True,'tree replay scope differs')
    expected={'historical':2,'weak':8,'figures':16,'local':1,'scores':12,'evaluation_figures':7,'evaluation_supplement':12,'full_table':1}
    require({k:len(v) for k,v in replay['byte_identical_outputs'].items()}==expected,'tree replay outputs differ')
    for name,item in replay['overlay_files'].items():bind(name,item['sha256'])
    for name,status in (('native_final_review.json','PASS_INDEPENDENT_NATIVE_REVIEW'),('nn_end_forecast_review.json','PASS_INDEPENDENT_CANDIDATE_FORECAST_REVIEW'),('nn_end_score_review.json','PASS_INDEPENDENT_SCORE_RECOUNT'),('independent_kg_review.json','PASS_SOURCE_AND_EVIDENCE_REVIEW'),('final_review.json','PASS')):
        review=receipt('review/'+name,status)
        for path,digest in review.get('sha256',review.get('inputs',{})).items():bind(path,digest)
        for path,digest in review.get('hash_only_sha256',{}).items():bind(path,digest)
    forecast_review=json.loads((B/'review/nn_end_forecast_review.json').read_text())
    bind(B/'forecast/proof/comparability.json',forecast_review['comparability_sha256'])
    bind(B/'forecast/proof/finite_sanity.json',forecast_review['finite_sanity_sha256'])
    bind(B/'forecast/proof/provenance_inventory.json',forecast_review['provenance_inventory_sha256'])
    score_review=json.loads((B/'review/nn_end_score_review.json').read_text())
    bind(B/'evaluation/results/receipt.json',score_review['results_receipt_sha256'])
    bind(B/'forecast/proof/comparability.json',score_review['forecast_proof_sha256'])
    bind(B/'forecast/policy.json',score_review['policy_sha256'])
    stage=receipt('kg/stage_review.json','GO');publication=receipt('kg/publish_receipt.json','PUBLISHED_AND_READBACK_PASS')
    bind(B/'kg/stage_receipt.json',stage['stage_receipt_sha256']);bind(B/'kg/stage_validation.json',stage['stage_validation_sha256'])
    bind(B/'kg/stage_review.json',publication['stage_review_sha256']);bind(B/'kg/stage_receipt.json',publication['stage_receipt_sha256'])
    require((publication['prior_snapshot_count'],publication['published_snapshot_count'])==(262,264),'published snapshot count differs')
    copy=receipt('kg/postpublish_copy_receipt.json','PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')
    independent=receipt('kg/postpublish_independent_readback.json','PASS_INDEPENDENT_POSTPUBLICATION_READBACK')
    require((independent['prior_snapshot_count'],independent['published_snapshot_count'])==(262,264) and len(copy['copied'])==9,'independent KG readback scope differs')
    bind(B/'kg/publish_receipt.json',copy['publish_receipt_sha256'])
    bind(B/'kg/publish_receipt.json',independent['publish_receipt_sha256'])
    bind(B/'kg/postpublish_copy_receipt.json',independent['copy_receipt_sha256'])
    bind(B/'kg/selection_lock.json',independent['selection_lock_sha256'])
    for target in copy['copied']:
        if target['kind']=='file':bind(target['path'],target['hashes'])
        elif target['kind']=='directory':
            for name,digest in target['hashes'].items():bind(Path(target['path'])/name,digest)
        else:raise ValueError('unknown copied target kind')
    prior=receipt('validation/prior_after_kg_audit.json','PASS')
    bind(B/'kg/publish_receipt.json',prior['publication_sha256'])
    aliases={'README.md':'README.md','docs/CURRENT_RESEARCH_STATUS.md':'CURRENT_RESEARCH_STATUS.md',
             **{f'graphify-out/{n}':f'graphify-out/{n}' for n in ('graph.json','GRAPH_REPORT.md','manifest.json')}}
    require(prior['artifact_count']==8656 and prior['alias_count']==5 and prior['published_snapshot_count']==264 and set(prior['changed_current_paths'])==set(aliases),'prior evidence not preserved')
    prior_manifest=ROOT/'docs/evidence/cp02_mp10_process_20261110/validation.json'
    bind(prior_manifest,prior['prior_manifest_sha256'])
    bind(ROOT/'docs/evidence/cp02_mp10_process_20261110/review/final_index_review.json',prior['prior_final_index_review_sha256'])
    bind(B/'kg/prior_audit.json',prior['initial_git_blob_audit_sha256'])
    prior_rows={x['path']:x for x in json.loads(prior_manifest.read_text())['artifacts']}
    require(set(aliases).issubset(prior_rows),'prior alias entries missing')
    for name,target in aliases.items():bind(B/'kg/prior_aliases'/target,prior_rows[name]['sha256'])
    return {'related_tests':545,'test_files':90,'focused_tree_tests':16,'historical_rows':432,'weak_public_rows':1755,'weak_surface_checks':6,'local_rows':12,'local_packed_words':110,'native_byte_equal_histories':8,'candidate_histories':7,'candidate_unchanged_inputs':89,'candidate_finite_fields_per_history':11,'categorical_rows':216,'continuous_rows':36,'weak_rows':108,'false_alarm_rows':72,'gates_passed':21,'gates_required':26,'decision':'NOT_ADOPTED_RETAIN_B1','prior_artifacts_preserved':8656,'figures':27,'zip_members':55,'scope':replay['scope'],'global_water_energy_budget_closed':False}

def artifacts():
    paths={ROOT/name for name in (*SOURCES,'README.md','docs/CURRENT_RESEARCH_STATUS.md',REPORT)}
    paths.update(p for p in B.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT/'graphify-out'/STAMP).glob('*'))
    paths.update(ROOT/'graphify-out'/name for name in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    require((ROOT/'graphify-out'/STAMP).is_dir(),'dated Cloud-BAL graph snapshot missing')
    excluded={B/'validation.json',B/'review/final_index_review.json'};result=[]
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc','.lock'):continue
        require(path.is_file() and not path.is_symlink(),'unsafe artifact '+str(path))
        require(path.stat().st_size<100*1024**2,'artifact exceeds 100 MiB')
        with path.open('rb') as f:require(f.read(4)!=b'\x7fELF','ELF must remain external')
        result.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'size_bytes':path.stat().st_size})
    require(bool(result),'empty manifest')
    return result

if __name__=='__main__':
    output=B/'validation.json'
    require(not output.exists() and not output.is_symlink(),'preserve manifest')
    checks=verify();rows=artifacts()
    with output.open('x') as f:json.dump({'status':'PASS','schema':'cp02_activation_path_validation_v1','checks':checks,'artifact_count':len(rows),'artifacts':rows,'excluded_self_referential':['validation.json','review/final_index_review.json']},f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','artifact_count':len(rows)}))
