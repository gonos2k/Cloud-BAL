#!/usr/bin/env python3
"""Make compact report tables from independently reviewed frozen derivatives."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
PINS={'results/receipt.json':'f76b74141410d5b287c554467fd0f3803fe9a8c8debceb6e33dd30639aa69681',
      'baseline/results/receipt.json':'d93b979f455c7ff07a38deb04af3c6ea1ae8196b01f9775bd7a0420ed2b76219',
      'baseline/results/early_selected.npz':'803c398b178db89271976b941a74db7e3a9010ffe16091c94749f5d1feb5ab1c',
      'baseline/results/entry_frontier.csv':'43c429a7628a5245d90046620a39b8b9d757edd60edfc53829f32bd2f49ecdeb',
      'entry_only/statistics.json':'64087241cb52936fe36001084bc12ba07a730c9b03b210140ac5c7001abddc46',
      'validation/early_selected_review.json':'3e0347ba26c71a59d5848a4081f54c5538ad8e9bdc31129d0a5f17088cf44673'}

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write_csv(path,rows):
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)

def main():
    for name,expected in PINS.items():
        if sha(ROOT/name)!=expected:raise ValueError(f'input changed: {name}')
    receipt=json.loads((ROOT/'results/receipt.json').read_text());stats=json.loads((ROOT/'entry_only/statistics.json').read_text());review=json.loads((ROOT/'validation/early_selected_review.json').read_text())
    if receipt['status']!='PASS' or stats['status']!='PASS' or review['status']!='GO':raise ValueError('input receipt not PASS')
    summary=receipt['summary'];global_rows=[]
    for name,item in summary['comparisons'].items():
        stage,field=name.split('_',1);row={'stage':stage,'field':field,'called_cells':summary['called_cells'],'changed_cells':item['changed']};cross=item['input_NR_cross'];row.update({'neither':cross['neither'],'input_only':cross['input_only'],'sample_only':cross['entry_only'],'both':cross['both']});global_rows.append(row)
    if len(global_rows)!=10 or summary['called_cells']!=2533440 or summary['uncalled_cells']!=40092:raise ValueError('global inventory differs')
    with (ROOT/'baseline/results/entry_frontier.csv').open(newline='') as f:source=list(csv.DictReader(f))
    lookup={(r['point_id'],r['field'],r['mode']):r for r in source}
    if len(source)!=64 or len(lookup)!=64:raise ValueError('frontier inventory differs')
    anchors=[]
    for point in ('NFA05','NFA12','RFA08','RFA11'):
        for field in ('NR','QV','QC','TH','TK','P','PII','QR'):
            a=lookup[point,field,'native'];b=lookup[point,field,'weighted']
            anchors.append({'point_id':point,'flat_index_yx':a['flat_index_yx'],'field':field,
                            'native_first_step_within_four':a['first_sample_step_within_1_to_4'],
                            'native_representative_k':a['representative_k_1based'],'native_i':a['native_i_1based'],'native_j':a['native_j_1based'],
                            'native_delta_at_first_step_max_abs':a['difference_at_first_step_max_abs'],
                            'weighted_first_step_within_four':b['first_sample_step_within_1_to_4'],
                            'weighted_representative_k':b['representative_k_1based'],
                            'weighted_delta_at_first_step_max_abs':b['difference_at_first_step_max_abs']})
    context=[{'metric':'count','value':stats['count']},{'metric':'DM_minus_B1_positive','value':stats['positive_DM_minus_B1']},{'metric':'DM_minus_B1_negative','value':stats['negative_DM_minus_B1']}]
    context += [{'metric':'abs_NR_delta_per_kg_'+k,'value':v} for k,v in stats['abs_NR_delta_per_kg_quantiles'].items()]
    context += [{'metric':'raw_entry_'+k,'value':v} for k,v in stats['QR_sign_partition'].items()]
    domain=[{'metric':key,'cells':summary[key]} for key in ('domain_cells','called_cells','uncalled_cells','input_nr_changed_all','input_nr_changed_called','input_nr_changed_uncalled')]
    with np.load(ROOT/'baseline/results/early_selected.npz',allow_pickle=False) as z:
        p=list(z['point_ids']).index('NFA12'); ix=z['point_corner_indices'][p]; a=z['B1_entry'][1,:,ix,:];b=z['DM065_entry'][1,:,ix,:];first=[]
        for field,index in (('TH',0),('TK',13),('P',14),('PII',15)):
            first.append({'point_id':'NFA12','flat_index_yx':20183,'step':2,'field':field,'equal_native_corner_levels':int((a[...,index]==b[...,index]).sum()),'different_native_corner_levels':int((a[...,index]!=b[...,index]).sum()),'total_native_corner_levels':156})
        if first[0]['different_native_corner_levels']!=0 or any(r['different_native_corner_levels']!=2 for r in first[1:]):raise ValueError('NFA12 step2 check differs')
    out=ROOT/'science/review_tables/results'
    if os.path.lexists(out):raise FileExistsError(out)
    stage=Path(tempfile.mkdtemp(prefix='.report-tables-',dir=out.parent))
    try:
        for name,rows in [('global_cross_tabs.csv',global_rows),('anchor_frontier.csv',anchors),('entry_only_context.csv',context),('domain_scope.csv',domain),('NFA12_step2.csv',first)]:write_csv(stage/name,rows)
        if any(sha(ROOT/name)!=expected for name,expected in PINS.items()):raise ValueError('source changed during recount')
        record={'status':'PASS','source_pins':PINS,'script_sha256':sha(Path(__file__)),'counts':{'global':len(global_rows),'anchor':len(anchors),'entry_only':len(context),'domain':len(domain),'NFA12_step2':len(first)},'outputs':{p.name:sha(p) for p in stage.iterdir()},'semantics':'Numerical state differences; blanks mean none within the first four selected calls. NR is per model-air mass. Native representative at the first changed step maximizes absolute difference over that point’s four corners and levels; weighted representative is separate. The global 14-field stage has no P or PII. Raw QR sign is not an activation threshold or error. No causal attribution.'}
        (stage/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
        if os.path.lexists(out):raise FileExistsError(out)
        os.rename(stage,out)
    finally:
        if stage.exists():shutil.rmtree(stage)
    print('PASS',sha(out/'receipt.json'))

if __name__=='__main__':main()
