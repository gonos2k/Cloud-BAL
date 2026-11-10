#!/usr/bin/env python3
"""Trace paired 20-second paths and five-minute surface pulses at fixed native levels."""
import argparse
import csv
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
import cp02_low_threshold_process as low
import cp02_ice_false_alarm as prior

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_low_threshold_process_20261110'
POINTS = (19145, 19144, 17804)
HOURS = (5, 6)
PAIRS = (('CONSERVATIVE', 'FIX'), ('ICE_FIXED', 'CONSERVATIVE'))
STAGES = ('core', 'cond', 'sed_rsg', 'sed_ice')
FIELDS = dict(low.FIELDS, NR=(None, 'public kg-1'), NI=(None, 'public kg-1'))


def windows(trace, steps):
    """Return 15-call counter changes with explicit starting and ending boundaries."""
    trace = np.asarray(trace, dtype=np.float64)
    steps = np.asarray(steps)
    if trace.ndim != 1 or len(trace) != len(steps) or len(trace) < 16 or not np.isfinite(trace).all() or not np.all(np.diff(steps) == 1):
        raise ValueError('contiguous finite surface boundaries required')
    return [(int(steps[i]), int(steps[i + 15]), float(trace[i + 15] - trace[i])) for i in range(len(trace) - 15)]


def stage_series(a, b, name, expression, contract, indices, weights):
    fields = contract[name + '_delta_fields']
    if expression not in fields:
        return None, None, None
    j = fields.index(expression)
    valid = a[name + '_valid'] & b[name + '_valid']
    # Preserve each actual substep sum and pair only the finished call sums.
    av, _ = low.weighted(a[name + '_delta'][..., j], indices, weights, valid)
    bv, _ = low.weighted(b[name + '_delta'][..., j], indices, weights, valid)
    diff, _ = low.weighted(a[name + '_delta'][..., j] - b[name + '_delta'][..., j], indices, weights, valid)
    return av, bv, diff


def field_arrays(a, b, field, expression, contract, indices, weights):
    j = contract['entry_return_fields'].index('TK=TH*PII' if field == 'TK' else field)
    entry, _ = low.weighted(a['entry'][..., j].astype(np.float64) - b['entry'][..., j].astype(np.float64), indices, weights)
    returned, _ = low.weighted(a['returned'][..., j].astype(np.float64) - b['returned'][..., j].astype(np.float64), indices, weights)
    stages = {name: stage_series(a, b, name, expression, contract, indices, weights) if expression else (None, None, None) for name in STAGES}
    return entry, returned, stages


def finite(value):
    return '' if value is None or not np.isfinite(value) else float(value)


def call_rows(hour, upper, lower, points, field, units, entry, returned, stages):
    for t in range(180):
        for p, point in enumerate(points):
            for k in range(39):
                record = {'hour': hour, 'step': (hour-1)*180+t+1, 'contrast': upper+'-'+lower,
                          'point': int(point['flat_index_yx']), 'k': k+1, 'field': field, 'units': units,
                          'entry_difference': entry[t,p,k], 'return_difference': returned[t,p,k],
                          'local_difference_change': returned[t,p,k]-entry[t,p,k],
                          'between_call_difference_change': '' if t == 0 else entry[t,p,k]-returned[t-1,p,k]}
                for name in STAGES:
                    av, bv, diff = stages[name]
                    for label, values in (('upper',av),('lower',bv),('difference',diff)):
                        record[name+'_'+label] = finite(None if values is None else values[t,p,k])
                yield record


def window_rows(hour, upper, lower, points, field, units, entry, returned, stages, selected):
    for p, point in enumerate(points):
        point_id = int(point['flat_index_yx'])
        for choice in selected[hour, upper+'-'+lower, point_id]:
            start, end = choice['start_boundary'], choice['end_boundary']
            lo, hi = start-(hour-1)*180, end-(hour-1)*180
            for k in range(39):
                ent, ret = entry[lo:hi,p,k], returned[lo:hi,p,k]
                local = np.sum(ret-ent, dtype=np.float64)
                external = np.sum(ent[1:]-ret[:-1], dtype=np.float64)
                rec = {'hour':hour, 'contrast':upper+'-'+lower, 'point':point_id, 'window_kind':choice['kind'],
                       'start_boundary':start,'end_boundary':end,'k':k+1,'field':field,'units':units,
                       'initial_entry_difference':ent[0], 'last_return_difference':ret[-1],
                       'window_difference_change':ret[-1]-ent[0], 'local_difference_change_sum':local,
                       'between_call_difference_change_sum':external,
                       'closure_residual':ret[-1]-ent[0]-local-external}
                for name in STAGES:
                    values = stages[name][2]
                    v = None if values is None else values[lo:hi,p,k]
                    rec[name+'_difference_sum'] = finite(None if v is None or not np.isfinite(v).all() else v.sum(dtype=np.float64))
                yield rec


def choose_windows(traces, points):
    rows=[]; selected={}; steps=traces['step']
    for hour in HOURS:
        lo,hi=(hour-1)*180,hour*180
        for p, point in enumerate(points):
            point_id=int(point['flat_index_yx'])
            for upper,lower in PAIRS:
                a=traces[upper+'_rain_cumulative_mm'][lo:hi+1,p]
                b=traces[lower+'_rain_cumulative_mm'][lo:hi+1,p]
                aw=windows(a,steps[lo:hi+1]);bw=windows(b,steps[lo:hi+1])
                # Earliest tie wins. Maximal signed contrast is deliberately not an absolute maximum.
                choices=(('upper_max', max(range(len(aw)),key=lambda i:aw[i][2])),
                         ('contrast_max', max(range(len(aw)),key=lambda i:aw[i][2]-bw[i][2])))
                selected[hour,upper+'-'+lower,point_id]=[]
                for kind,i in choices:
                    r={'hour':hour,'contrast':upper+'-'+lower,'point':point_id,'kind':kind,
                       'start_boundary':aw[i][0],'end_boundary':aw[i][1],
                       'upper_counter_change_mm':aw[i][2],'lower_counter_change_mm':bw[i][2],
                       'contrast_counter_change_mm':aw[i][2]-bw[i][2]}
                    rows.append(r);selected[hour,upper+'-'+lower,point_id].append(r)
    return rows,selected


def run(compact, points_path, schema_path, proof_path, output):
    if os.path.lexists(output): raise FileExistsError(output)
    proof=json.loads(proof_path.read_text()); schema=json.loads(schema_path.read_text()); contract=schema['compact_contract']
    if proof['status']!='PASS' or set(proof['arms'])!=set(low.ARMS) or proof['schema_sha256']!=low.identity(schema_path)['sha256']:
        raise ValueError('three-arm comparability proof required')
    if low.identity(points_path)['sha256']!=low.SELECTED_POINTS_SHA256: raise ValueError('points differ from pre-capture selection')
    cohort_receipt=points_path.parent/'receipt.json'; cohort=json.loads(cohort_receipt.read_text())
    if cohort['status']!='COMPLETE' or cohort['outputs'][points_path.name]!=low.SELECTED_POINTS_SHA256: raise ValueError('selection receipt differs')
    source=BUNDLE/'native/source/source_receipt.json'; review=BUNDLE/'review/launch_go.json'
    if proof['source_receipt_sha256']!=low.identity(source)['sha256'] or proof['launch_review_sha256']!=low.identity(review)['sha256']: raise ValueError('source/launch proof differs')
    with points_path.open(newline='') as f: all_points=list(csv.DictReader(f))
    if len(all_points)!=21 or len({r['flat_index_yx'] for r in all_points})!=21: raise ValueError('selection scope differs')
    lookup={int(r['flat_index_yx']):r for r in all_points}; points=[lookup[p] for p in POINTS]
    inputs=[low.identity(p) for p in (points_path,cohort_receipt,schema_path,proof_path,source,review,Path(low.__file__),Path(prior.__file__),Path(prior.evaluation.__file__))]
    for arm in low.ARMS:
        _,items=low.read_capture(compact/arm,arm,schema_path,proof['arms'][arm]); inputs.extend(items)
    _,traces,refs=low.surface_tables(compact,all_points); inputs+=refs
    for arm in low.ARMS:
        traces[arm+'_rain_cumulative_mm']=traces[arm+'_rain_cumulative_mm'][:,[list(lookup).index(p) for p in POINTS]]
    surface,selected=choose_windows(traces,points)
    output.parent.mkdir(parents=True,exist_ok=True); stage=Path(tempfile.mkdtemp(prefix='.pulse-',dir=output.parent))
    try:
        low.write_csv(stage/'surface_windows.csv',surface)
        surface_calls=[]
        for hour in HOURS:
            for step in range((hour-1)*180+1,hour*180+1):
                for p, point in enumerate(points):
                    rec={'hour':hour,'step':step,'point':int(point['flat_index_yx'])}
                    for arm in low.ARMS:
                        counter=traces[arm+'_rain_cumulative_mm'][:,p]
                        rec[arm+'_counter_mm']=float(counter[step])
                        rec[arm+'_counter_change_mm']=float(counter[step]-counter[step-1])
                    surface_calls.append(rec)
        low.write_csv(stage/'surface_calls.csv',surface_calls)
        with (stage/'calls.csv.gz').open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,compresslevel=6,mtime=0) as zipped, io.TextIOWrapper(zipped,encoding='utf-8',newline='') as fc, (stage/'window_levels.csv').open('w',newline='') as fw:
            cw=ww=None; count=0; window_count=0
            for hour in HOURS:
                payload={arm:low.load_hour(compact/arm,hour,contract) for arm in low.ARMS}
                ref=payload['FIX']; indices,weights=low.geometry(points,ref['i'],ref['j'])
                for item in payload.values():
                    if any(not np.array_equal(item[k],ref[k]) for k in ('step','i','j','k')): raise ValueError('arm coordinate/time axes differ')
                for upper,lower in PAIRS:
                    for field,(expression,units) in FIELDS.items():
                        entry,returned,stages=field_arrays(payload[upper],payload[lower],field,expression,contract,indices,weights)
                        for row in call_rows(hour,upper,lower,points,field,units,entry,returned,stages):
                            if cw is None: cw=csv.DictWriter(fc,fieldnames=row,lineterminator='\n');cw.writeheader()
                            cw.writerow(row);count+=1
                        for row in window_rows(hour,upper,lower,points,field,units,entry,returned,stages,selected):
                            if ww is None: ww=csv.DictWriter(fw,fieldnames=row,lineterminator='\n');ww.writeheader()
                            ww.writerow(row);window_count+=1
        summary={'hours':list(HOURS),'points':list(POINTS),'contrasts':[a+'-'+b for a,b in PAIRS],
                 'calls_rows':count,'window_level_rows':window_count,'surface_windows':surface,
                 'limits':['Stage differences are paired per-call sums of each arm’s actual substeps; substep ordinals are not matched.',
                           'Stage changes are partial diagnostics, not a closed budget; missing phases are blank.',
                           'Public NR and NI are per kg; no internal number-per-volume stage is added to them.',
                           'TK is source temperature TH*PII; TH is not substituted.',
                           'Between-call changes include all external operations; native k is not a vertical integral.',
                           'A surface window is 15 calls, starting after its first boundary; window endpoint is not window change.']}
        (stage/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        for item in inputs:
            if low.identity(item['path'])!=item: raise ValueError('input changed while analyzing')
        receipt={'status':'COMPLETE','inputs':inputs,'source':low.identity(__file__),'outputs':{p.name:low.identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        prior.evaluation.publish_new(stage,output)
    finally:
        if stage.exists(): shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('compact','points','schema','proof','output'): parser.add_argument('--'+arg,type=Path,required=True)
    args=parser.parse_args()
    run(args.compact,args.points,args.schema,args.proof,args.output)
