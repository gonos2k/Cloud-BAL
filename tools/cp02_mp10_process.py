#!/usr/bin/env python3
"""Compare real inner-loop cleanup and public KDM6 boundaries at fixed points."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
import cp02_low_threshold_process as low
import cp02_ice_false_alarm as publication

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'docs/evidence/cp02_mp10_process_20261110/native'
POINTS_SHA = 'f36d193647d04a4eb811318431dd15f0b92d0644d9815b35a3650d70b073888d'
ARMS = {'CONTROL': 1, 'MP10': 2}
WINDOWS = {1: (1, 180), 3: (361, 540), 6: (901, 1080)}
KEYS = ('step', 'rank', 'call', 'j', 'i', 'k', 'loop', 'loops', 'substep', 'mstep', 'phase', 'nfields')
FIELDS = ('QV','QC','QI','QR','QS','QG','TK','NC_volume','NI_volume','NN_volume','NR_volume')
STATE_INDICES = (1,6,7,8,9,10,2,11,12,13,14)
EXPRESSIONS = ('q(i,k)','qci(i,k,1)','qci(i,k,2)','qrs(i,k,1)','qrs(i,k,2)',
               'qrs(i,k,3)','t(i,k)','nci(i,k,1)','nci(i,k,2)','nci(i,k,3)','nrs(i,k,1)')
PUBLIC = ('QV','QC','QI','QR','QS','QG','TK','NR','NI','TH','P','PII','DEN','NC','NN')
MASS = (0,1,2,3,4,5)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path.resolve()), 'sha256': digest, 'size_bytes': path.stat().st_size}


def read_json(path, status):
    result = json.loads(Path(path).read_text())
    require(result.get('status') == status, 'incomplete receipt: ' + str(path))
    return result


def bind_inputs(packed, points, schema, proof):
    pin = read_json(proof, 'PASS')
    require(pin.get('schema') == 'cp02_mp10_process_comparability_v1' and set(pin['arms']) == set(ARMS),
            'paired process proof scope differs')
    require(identity(points)['sha256'] == POINTS_SHA, 'selection differs from pre-capture points')
    require(pin['schema_sha256'] == identity(schema)['sha256'], 'capture schema differs')
    require(pin['selector_sha256'] == identity(points.parent/'native_columns.csv')['sha256'], 'proof native selector differs')
    source_receipt = NATIVE/'source/source_receipt.json'
    postrun_review = NATIVE.parent/'review/compact_v2_go.json'
    require(pin['source_receipt_sha256'] == identity(source_receipt)['sha256'] and
            pin['postrun_review_sha256'] == identity(postrun_review)['sha256'], 'proof source/review differs')
    for name, expected in pin['reviewed_script_sha256'].items():
        require(identity(ROOT/name)['sha256'] == expected, 'reviewed native script changed')
    inputs = [identity(p) for p in (points, points.parent/'receipt.json', schema, proof, source_receipt, postrun_review)]
    cohort = read_json(points.parent/'receipt.json', 'COMPLETE')
    require(cohort['outputs'][points.name] == POINTS_SHA and
            cohort['outputs']['native_columns.csv'] == identity(points.parent/'native_columns.csv')['sha256'],
            'selection receipt differs')
    inventories = {}
    for arm in ARMS:
        folder = packed/arm
        packing_path = folder/'packing_receipt.json'
        capture_path = NATIVE/'compact'/arm/'capture_receipt.json'
        recount_path = NATIVE/'compact'/arm/'raw_recount_receipt.json'
        pack = read_json(packing_path, 'PASS')
        capture = read_json(capture_path, 'COMPLETE')
        recount = read_json(recount_path, 'PASS')
        observed = pin['arms'][arm]
        for key, path in (('packing_receipt_sha256',packing_path), ('capture_receipt_sha256',capture_path),
                          ('raw_recount_sha256',recount_path)):
            require(observed[key] == identity(path)['sha256'], 'proof receipt binding differs: ' + key)
        require(pack['capture_receipt_sha256'] == identity(capture_path)['sha256'] and
                pack['raw_recount_sha256'] == identity(recount_path)['sha256'] and
                recount['capture_receipt_sha256'] == identity(capture_path)['sha256'],
                'packing/raw recount chain differs')
        require(capture['source_receipt_sha256'] == pin['source_receipt_sha256'] and
                capture['schema_sha256'] == identity(schema)['sha256'], 'capture source/schema differs')
        originals = {r['name']:r for r in capture['outputs']}
        files = {r['name']:r for r in pack['outputs']}
        require(len(files) == len(pack['outputs']) and len(originals) == len(capture['outputs']) and
                files and set(files) == set(originals), 'incomplete packed inventory')
        for name, record in files.items():
            require(Path(name).name == name and record['source_sha256'] == originals[name]['sha256'],
                    'packed source inventory differs')
            actual = identity(folder/name)
            require(actual['sha256'] == record['sha256'] and actual['size_bytes'] == record['size_bytes'],
                    'packed artifact changed: ' + name)
            inputs.append(actual)
        inputs += [identity(p) for p in (packing_path,capture_path,recount_path)]
        inventories[arm] = files
    return inputs, inventories


def load_group(folder, names, group, first):
    selected = sorted(name for name in names if name.startswith(f'{group}_{first:06d}_') and name.endswith('.npz'))
    require(selected, f'missing group {group} at step {first}')
    key_parts, bit_parts = [], []
    for name in selected:
        with np.load(folder/name, allow_pickle=False) as data:
            require(set(data.files) == {'keys','bits'}, 'unexpected sparse arrays')
            keys, bits = data['keys'], data['bits']
            require(keys.dtype == np.int32 and keys.ndim == 2 and keys.shape[1] == len(KEYS), 'invalid record keys')
            require(bits.ndim == 2 and len(bits) == len(keys) and bits.dtype ==
                    (np.uint64 if group == 'faces' else np.uint32), 'invalid native bit payload')
            require(np.all((keys[:,0] >= first) & (keys[:,0] <= first+2)), 'record outside chunk')
            require(np.all((keys[:,11] > 0) & (keys[:,11] <= bits.shape[1])), 'invalid field count')
            key_parts.append(keys); bit_parts.append(bits)
    keys, bits = np.concatenate(key_parts), np.concatenate(bit_parts)
    require(len(np.unique(keys, axis=0)) == len(keys), 'duplicate sparse record')
    return keys, bits


def dense_phase(records, phase, steps, cells, loops, field_indices):
    keys, bits = records
    selected = keys[:,10] == phase
    k, v = keys[selected], bits[selected]
    require(len(k) == len(steps)*len(cells)*39*loops, f'phase {phase} coverage differs')
    lookup = {cell:i for i,cell in enumerate(cells)}
    try:
        columns = np.array([lookup[int(i),int(j)] for i,j in zip(k[:,4],k[:,3])])
    except KeyError as error:
        raise ValueError('record outside selected columns') from error
    indices = (k[:,0]-steps[0], columns, k[:,5]-1, k[:,6]-1)
    require(np.all(k[:,7] == loops) and np.all((indices[0] >= 0)&(indices[0] < len(steps))) and
            np.all((indices[2] >= 0)&(indices[2] < 39)) and np.all((indices[3] >= 0)&(indices[3] < loops)),
            'phase axes differ')
    require(np.all(k[:,11] > max(field_indices)), 'required phase field absent')
    linear = np.ravel_multi_index(indices, (len(steps),len(cells),39,loops))
    require(len(np.unique(linear)) == len(linear), 'duplicate phase position')
    result = np.empty((len(steps),len(cells),39,loops,len(field_indices)), dtype=np.float32)
    result[indices] = v[:,field_indices].copy().view(np.float32)
    require(np.isfinite(result).all(), 'nonfinite observed state')
    return result


def source_stage(records, before, after, steps, cells, loops, schema):
    """Sum actual paired substeps in increasing substep order, within each arm."""
    keys,bits = records
    fields = []
    for phase in (before,after):
        names = schema['phases'][str(phase)]['fields']
        if phase == 10:
            names = schema['arm_overrides']['CONTROL and MP10']['phase_10_fields']
        fields.append(names)
    available = np.array([expression in fields[0] and expression in fields[1] for expression in EXPRESSIONS])
    result = np.full((len(steps),len(cells),39,loops,len(FIELDS)), np.nan, dtype=np.float64)
    a,b = keys[:,10] == before,keys[:,10] == after
    ka,kb = keys[a],keys[b]
    if not len(ka) and not len(kb):
        return result
    canonical = lambda k: np.lexsort(tuple(k[:,i] for i in reversed(range(10))))
    ia,ib = canonical(ka),canonical(kb)
    ka,kb = ka[ia],kb[ib]
    require(np.array_equal(ka[:,:10],kb[:,:10]), f'phase {before}/{after} keys differ')
    lookup = {cell:i for i,cell in enumerate(cells)}
    try:
        columns = np.array([lookup[int(i),int(j)] for i,j in zip(ka[:,4],ka[:,3])])
    except KeyError as error:
        raise ValueError('stage outside selection') from error
    index = (ka[:,0]-steps[0],columns,ka[:,5]-1,ka[:,6]-1)
    require(np.all(ka[:,7] == loops), 'stage loop count differs')
    counts = np.zeros(result.shape[:-1], dtype=np.int32)
    np.add.at(counts,index,1)
    va_bits, vb_bits = bits[a][ia], bits[b][ib]
    for f in np.flatnonzero(available):
        va = va_bits[:,fields[0].index(EXPRESSIONS[f])].copy().view(np.float32).astype(np.float64)
        vb = vb_bits[:,fields[1].index(EXPRESSIONS[f])].copy().view(np.float32).astype(np.float64)
        target = np.zeros(result.shape[:-1],dtype=np.float64)
        np.add.at(target,index,vb-va)
        result[...,f] = np.where(counts > 0,target,np.nan)
    return result


def validate_core_arithmetic(records, steps, cells, loops):
    before=dense_phase(records,6,steps,cells,loops,(1,2))
    after=dense_phase(records,8,steps,cells,loops,(1,2))
    heat=dense_phase(records,7,steps,cells,loops,(0,1,2,3,4,5))
    vapor=np.add(before[...,0],np.multiply(heat[...,0],heat[...,3],dtype=np.float32),dtype=np.float32)
    cooling=np.multiply(np.divide(heat[...,1],heat[...,2],dtype=np.float32),heat[...,3],dtype=np.float32)
    temperature=np.subtract(before[...,1],cooling,dtype=np.float32)
    require(np.array_equal(vapor.view(np.uint32),after[...,0].view(np.uint32)), 'native vapor update differs')
    require(np.array_equal(temperature.view(np.uint32),after[...,1].view(np.uint32)), 'native temperature update differs')
    require(np.array_equal(heat[:,:,:,:-1,2].view(np.uint32),heat[:,:,:,1:,2].view(np.uint32)) and
            np.array_equal(heat[:,:,:,:-1,4].view(np.uint32),heat[:,:,:,1:,4].view(np.uint32)),
            'held cpm/xl changed between inner loops')
    return vapor.size


def weighted(values, indices, weights):
    """Weight already promoted native differences; positive-weight NaN remains missing."""
    selected = values[:,indices]
    shape = (1,*weights.shape)+ (1,)*(values.ndim-2)
    w = weights.reshape(shape)
    valid = np.all(np.isfinite(selected) | (w == 0),axis=2)
    total = np.sum(np.where(w == 0,0,selected*w),axis=2,dtype=np.float64)
    return np.where(valid,total,np.nan)


def paired(upper, lower, indices, weights):
    return weighted(upper.astype(np.float64)-lower.astype(np.float64),indices,weights)


def cleanup_columns(state):
    """Return source-carrier mass removal and separate number-area changes."""
    before, zero, end = (state[p] for p in (32,33,34))
    require(np.array_equal(before[..., [1,2]].view(np.uint32), zero[..., [1,2]].view(np.uint32)),
            'zeroing unexpectedly changes vapor or temperature')
    difference = zero.astype(np.float64)-before.astype(np.float64)
    carrier = before[...,3].astype(np.float64)*before[...,4].astype(np.float64)
    require(np.all(carrier > 0), 'invalid source density or thickness')
    removed = (-difference[...,6:11].sum(axis=-1)*carrier).sum(axis=(2,3))
    number = (end[...,11:15].astype(np.float64)-zero[...,11:15].astype(np.float64))
    number_area = (number*before[...,4,None].astype(np.float64)).sum(axis=(2,3))
    return removed, number_area


def loop_metrics(state):
    start,pre_zero,post_zero,end = (state[p] for p in (30,32,33,34))
    require(np.array_equal(end[:,:,:,:-1].view(np.uint32),start[:,:,:,1:].view(np.uint32)),
            'actual inner-loop state carry differs')
    # The PSD block changes number only. Water and temperature equality is observed.
    require(np.array_equal(post_zero[...,:7].view(np.uint32),end[...,:7].view(np.uint32)),
            'unexpected mass/temperature change in PSD block')
    return {'entry':start[:,:,:,0], 'end':end[:,:,:,-1],
            'loop_delta':(end.astype(np.float64)-start.astype(np.float64)).sum(axis=3),
            'zero_delta':(post_zero.astype(np.float64)-pre_zero.astype(np.float64)).sum(axis=3),
            'psd_delta':(end.astype(np.float64)-post_zero.astype(np.float64)).sum(axis=3)}


def ledger(entry, returned):
    local = np.sum(returned-entry,axis=0,dtype=np.float64)
    outside = np.sum(entry[1:]-returned[:-1],axis=0,dtype=np.float64)
    change = returned[-1]-entry[0]
    return local,outside,change,change-local-outside


def write_csv(path, rows):
    rows = iter(rows);first = next(rows)
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=first,lineterminator='\n');writer.writeheader();writer.writerow(first);writer.writerows(rows)


def run(packed, points_path, schema_path, proof_path, output):
    if os.path.lexists(output):
        raise FileExistsError(output)
    inputs,inventories = bind_inputs(packed,points_path,schema_path,proof_path)
    schema = json.loads(schema_path.read_text())
    with points_path.open(newline='') as stream:points=list(csv.DictReader(stream))
    require(len(points) == 30 and len({p['flat_index_yx'] for p in points}) == 30, 'point count differs')
    cells_path=points_path.parent/'native_columns.csv'
    with cells_path.open(newline='') as stream:cells=[(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader(stream)]
    require(len(cells)==len(set(cells))==111,'native column count differs')
    inputs += [identity(cells_path),identity(__file__),identity(ROOT/'tools/cp02_low_threshold_process.py')]
    indices,weights=low.geometry(points,np.array([p[0] for p in cells]),np.array([p[1] for p in cells]))
    wrapper_path=NATIVE/'runs/read_wrapper.py';inputs.append(identity(wrapper_path))
    spec=importlib.util.spec_from_file_location('mp10_native_wrapper',wrapper_path)
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.mp10-analysis-',dir=output.parent))
    summary_rows=[];event_rows=[];arithmetic_counts={arm:0 for arm in ARMS}
    try:
        for hour,(first,last) in WINDOWS.items():
            arm_data={}
            for arm,loops in ARMS.items():
                chunks={name:[] for name in ('entry','end','loop_delta','zero_delta','psd_delta','core_delta','cond_delta','sed_rsg_delta','sed_ice_delta','zero_removed_column','psd_number_column')}
                for start in range(first,last+1,3):
                    steps=tuple(range(start,start+3))
                    records=load_group(packed/arm,inventories[arm],'state',start)
                    raw_states={p:dense_phase(records,p,steps,cells,loops,tuple(range(18))) for p in (30,32,33,34)}
                    require(np.array_equal(raw_states[34][:,:,:,:-1].view(np.uint32),
                                           raw_states[30][:,:,:,1:].view(np.uint32)), 'full native loop carry differs')
                    require(np.all(raw_states[30][...,5] == np.float32(20/loops)), 'actual internal dt differs')
                    removed, number = cleanup_columns(raw_states)
                    chunks['zero_removed_column'].append(removed); chunks['psd_number_column'].append(number)
                    states={p:values[...,STATE_INDICES] for p,values in raw_states.items()}
                    metrics=loop_metrics(states)
                    for name,values in metrics.items():chunks[name].append(values)
                    core=load_group(packed/arm,inventories[arm],'core',start)
                    arithmetic_counts[arm] += validate_core_arithmetic(core,steps,cells,loops)
                    for name,pre,post in (('core_delta',6,8),('cond_delta',11,12),('sed_rsg_delta',9,10),('sed_ice_delta',20,21)):
                        changes=source_stage(core,pre,post,steps,cells,loops,schema)
                        valid=np.isfinite(changes).all(axis=3)
                        chunks[name].append(np.where(valid,changes.sum(axis=3),np.nan))
                    for name,pre,post in (('zero',32,33),('psd',33,34)):
                        change=states[post].astype(np.float64)-states[pre].astype(np.float64)
                        for f,field in enumerate(FIELDS):
                            v=change[...,f];count=int(np.count_nonzero(v))
                            at=np.unravel_index(int(np.argmax(np.abs(v))),v.shape)
                            event_rows.append({'arm':arm,'hour':hour,'chunk_first':start,'operator':name,'field':field,
                                               'observed_inner_updates':v.size,'changed_inner_updates':count,
                                               'changed_native_bits':int(np.count_nonzero(states[pre][...,f].view(np.uint32) != states[post][...,f].view(np.uint32))),
                                               'max_abs_change':float(abs(v[at])), 'max_signed_change':float(v[at]),
                                               'step':start+at[0] if count else '',
                                               'i':cells[at[1]][0] if count else '', 'j':cells[at[1]][1] if count else '',
                                               'k':at[2]+1 if count else '', 'loop':at[3]+1 if count else ''})
                data={name:np.concatenate(values) for name,values in chunks.items()}
                measured=np.zeros_like(data['loop_delta'])
                for name in ('zero_delta','psd_delta','core_delta','cond_delta','sed_rsg_delta','sed_ice_delta'):
                    values=data[name]
                    measured += np.where(np.isfinite(values),values,0.)
                data['unmeasured_loop']=data['loop_delta']-measured
                steps=tuple(range(first,last+1))
                for name,sid in (('public_entry',6),('public_return',7)):
                    paths=[packed/arm/n for n in inventories[arm] if n.startswith('state_selected_'+('entry' if sid==6 else 'return'))]
                    values,_=reader.read_wrapper(paths,sid,steps,cells)
                    data[name]=values[..., [reader.FIELDS.index(f) for f in PUBLIC]]
                arm_data[arm]=data
                observed={name:weighted(value.astype(np.float64),indices,weights) for name,value in data.items()}
                filename=f'{arm}_h{hour:02d}.npz'
                np.savez_compressed(stage/filename,step=np.array(steps,dtype=np.int32),point=np.array([int(p['flat_index_yx']) for p in points]),
                                    k=np.arange(1,40,dtype=np.int32),source_fields=np.array(FIELDS),public_fields=np.array(PUBLIC),
                                    psd_number_fields=np.array(FIELDS[7:]),**observed)
            a,b=arm_data['MP10'],arm_data['CONTROL']
            differences={name:paired(a[name],b[name],indices,weights) for name in a}
            np.savez_compressed(stage/f'paired_h{hour:02d}.npz',step=np.arange(first,last+1,dtype=np.int32),
                                point=np.array([int(p['flat_index_yx']) for p in points]),k=np.arange(1,40,dtype=np.int32),
                                source_fields=np.array(FIELDS),public_fields=np.array(PUBLIC),
                                psd_number_fields=np.array(FIELDS[7:]),**differences)
            local,external,change,residual=ledger(differences['public_entry'],differences['public_return'])
            for p,point in enumerate(points):
                for k in range(39):
                    for f,field in enumerate(PUBLIC):
                        summary_rows.append({'hour':hour,'point':int(point['flat_index_yx']),'k':k+1,'field':field,
                                             'entry_difference':float(differences['public_entry'][0,p,k,f]),
                                             'return_difference':float(differences['public_return'][-1,p,k,f]),
                                             'local_sum':float(local[p,k,f]),'between_calls_sum':float(external[p,k,f]),
                                             'difference_change':float(change[p,k,f]),'closure_residual':float(residual[p,k,f])})
        write_csv(stage/'public_ledger.csv',summary_rows);write_csv(stage/'native_operator_extremes.csv',event_rows)
        summary={'points':30,'columns':111,'levels':39,'windows':WINDOWS,'public_ledger_rows':len(summary_rows),
                 'native_operator_rows':len(event_rows),'arms':ARMS,'core_vapor_temperature_updates_bitwise_replayed':arithmetic_counts,
                 'limits':['Source number fields are internal per-volume; public NR/NI are per-mass and kept separate.',
                           'zero_removed_column is source DEN*DELZ-weighted removal kg/m2; psd_number_column is per-species number/m2 with DELZ only. Neither is a domain budget.',
                           'Between-public-call changes include all external processing; they are not transport alone.',
                           'Different inner-loop and sediment substep ordinals are never paired across configurations.',
                           'Missing stage fields remain NaN; no absent observation is replaced by zero.',
                           'unmeasured_loop subtracts only available observed stages and retains all unmeasured intervals/fields; it is not an assigned physical process.',
                           'Time sums at a native k are not vertically integrated water/energy budgets.',
                           'Bitwise vapor/temperature arithmetic replay and held cpm/xl checks are local operation tests, not a closed energy budget.',
                           'Operator extrema count actual changed inner updates at native cell-levels; these are not independent observations.']}
        (stage/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        for item in inputs:require(identity(item['path'])==item,'input changed during analysis')
        meta={'status':'COMPLETE','inputs':inputs,'source':identity(__file__),'outputs':{p.name:identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(meta,indent=2)+'\n')
        publication.evaluation.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('packed','points','schema','proof','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();run(args.packed,args.points,args.schema,args.proof,args.output)
