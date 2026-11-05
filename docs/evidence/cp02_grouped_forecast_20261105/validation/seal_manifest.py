#!/usr/bin/env python3
"""Seal only a fully reviewed, scored and graph-published forecast evidence batch."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
BUNDLE=ROOT/'docs/evidence/cp02_grouped_forecast_20261105'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def require(condition,message):
    if not condition:raise ValueError(message)


def main():
    required={'validation/clean_export.json':'PASS','review/score_recount/recount_receipt.json':'PASS',
              'review/final_science_report_review.json':'PASS',
              'review/independent_kg_review.json':'PASS_SOURCE_AND_EVIDENCE_REVIEW',
              'kg/stage_review.json':'GO','kg/publish_receipt.json':'PUBLISHED_AND_READBACK_PASS',
              'kg/postpublish_copy_receipt.json':'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK',
              'runtime/comparability.json':'PASS','analysis/receipt.json':'COMPLETE',
              'figures/rendered/render_receipt.json':'COMPLETE'}
    for name,status in required.items():
        path=BUNDLE/name
        require(path.is_file() and json.loads(path.read_text()).get('status')==status,'unfinished validation/review: '+name)
    tests=json.loads((BUNDLE/'validation/clean_export.json').read_text())
    require(tests['passed']==tests['expected_tests'] and tests['passed']>=390 and tests['exit_code']==0
            and tests['overlay_unchanged'] is True,'immutable clean export did not pass')
    require(json.loads((BUNDLE/'analysis/receipt.json').read_text())['rows']==
            {'categorical':180,'continuous':30,'contrasts':180,'weak_transitions':24,'gates':52},'analysis scope differs')
    winner=json.loads((BUNDLE/'analysis/winner.json').read_text())
    require(winner['winner']=='B1_RETAINED' and not winner['qualified_candidates'],'reported retained configuration differs')
    require(json.loads((BUNDLE/'validation/pr149_artifact_audit.json').read_text())['artifact_count']==414,'prior scope differs')
    extras=['README.md','docs/CURRENT_RESEARCH_STATUS.md','docs/CP02_GROUPED_FORECAST_20261105.md',
            'tools/cp02_grouped_forecast.py','tools/plot_cp02_grouped_forecast.py','runtime/score_new_histories.py',
            'tests/test_score_new_histories.py']
    extras += [str(p.relative_to(ROOT)) for p in (ROOT/'tests').glob('*grouped*py')]
    extras += [f'graphify-out/{prefix}{name}' for prefix in ('','2026-11-05-grouped-forecast/')
               for name in ('graph.json','manifest.json','GRAPH_REPORT.md')]
    paths={ROOT/name for name in extras}
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file())
    excluded={BUNDLE/'validation.json',BUNDLE/'validation/final_index_review.json'}
    rows=[]
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc','.lock'):continue
        require(not path.is_symlink() and path.is_file(),'unsafe artifact '+str(path))
        require(path.stat().st_size<100*1024**2,'unsplit large artifact '+str(path))
        rows.append({'path':str(path.relative_to(ROOT)),'size_bytes':path.stat().st_size,'sha256':sha(path)})
    result={'schema':'cp02_grouped_forecast_validation_v1','status':'PASS_COMPLETED_FORECAST_BATCH',
            'base_commit':'76a70db52d4813cccad8ad0c098ca1d1c91df518',
            'pr_base_branch':'research/b1-two-hour-process','pr_head_branch':'research/b1-grouped-forecast',
            'case_initial_utc':'2026-08-16T12:00:00Z','new_six_hour_forecasts':2,'oldsum_six_hour_rebuild_controls':2,
            'native_operation_capture_cases':3,'retained_configuration':'IMPROVED_BG_FIXED','goal_met':False,
            'candidate_gates':{'C':{'protection':8,'recovery':2,'total':10,'new_recovery':0},
                               'D':{'protection':9,'recovery':2,'total':11,'new_recovery':0}},
            'tests':{'passed':tests['passed'],'expected':tests['expected_tests'],'source':'validation/clean_export.json'},
            'required_reviews':required,'artifact_count':len(rows),'artifacts':rows,
            'exclusions':['Self manifest and final index review prevent recursive hashes.',
                          'Transient locks/Python bytecode and external full ELF/NetCDF payloads are excluded; native identities remain hash-bound.'],
            'open_items':['No qualified candidate; current B1 retained.',
                          'Single weather case; RN1 upstream time/coverage/QC and independent cases remain unresolved.',
                          'Domain water/energy budgets and causal process attribution remain open.',
                          'C2 T39 and H/A/N one-hour completion remain separate unfinished work.']}
    with (BUNDLE/'validation.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print('PASS:',len(rows),'bounded artifacts')


if __name__=='__main__':main()
