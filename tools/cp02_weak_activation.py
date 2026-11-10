#!/usr/bin/env python3
"""Connect measured activation and NN restoration to three weak-rain columns."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
import cp02_mp10_process as prior
import cp02_low_threshold_process as geometry
from cp02_ice_false_alarm import evaluation
from cp02_ice_surface_components import interpolate

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT/'docs/evidence/cp02_activation_path_20261110'
ARMS = {'CONTROL':1, 'MP10':2}
ACT_FIELDS = ('sw','NC','NN','q','qc','t','den','xl','cpm','dtcld','pi','denr')
DELTA_FIELDS = ('NC_volume','NN_volume','QV','QC','TK')
ACT_INDICES = (1,2,3,4,5)
STEPS = tuple(range(361,541))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path, status):
    value = json.loads(path.read_text())
    require(value.get('status') == status, 'incomplete receipt: '+str(path))
    return value


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def bind_inputs():
    native = BUNDLE/'native'
    schema_path = native/'schema/schema.json'
    points_path = BUNDLE/'cohorts/selected_points.csv'
    columns_path = BUNDLE/'cohorts/native_columns.csv'
    mapping_path = BUNDLE/'cohorts/mapping_receipt.json'
    proof_path = native/'proof/comparability.json'
    proof = read_json(proof_path,'PASS')
    mapping = read_json(mapping_path,'PASS')
    require(proof['schema'] == 'cp02_activation_weak_comparability_v1' and set(proof['arms']) == set(ARMS),
            'paired weak capture scope differs')
    paths = {'schema_sha256':schema_path, 'source_receipt_sha256':native/'source/source_receipt.json',
             'selector_sha256':columns_path, 'selected_points_sha256':points_path,
             'mapping_receipt_sha256':mapping_path, 'supplement_sha256':native/'schema/contract_supplement.json'}
    for key,path in paths.items():
        require(prior.identity(path)['sha256'] == proof[key], 'proof binding differs: '+key)
    require(mapping['selected_points_sha256'] == proof['selected_points_sha256'] and
            mapping['selector_sha256'] == proof['selector_sha256'], 'mapping binding differs')
    inputs = [prior.identity(p) for p in (*paths.values(),proof_path,Path(__file__))]
    surface_path=BUNDLE/'cohorts/parent_surface_corners_0_3h.npz'
    surface_receipt_path=BUNDLE/'cohorts/parent_surface_receipt.json'
    surface_pin=read_json(surface_receipt_path,'PASS')
    require(surface_pin['raw_corners_sha256'] == prior.identity(surface_path)['sha256'] and
            surface_pin['selected_points_sha256'] == proof['selected_points_sha256'], 'surface reference binding differs')
    inputs += [prior.identity(surface_path),prior.identity(surface_receipt_path)]
    inventories = {}
    for arm in ARMS:
        histories=proof['arms'][arm]['history4byte_equal']
        require(len(histories) == len({r['name'] for r in histories}) == 4 and
                all(r['exact'] and r['actual_sha256'] == r['reference_sha256'] ==
                    surface_pin['source_history_sha256'][arm+'/'+r['name']] for r in histories), 'history comparison scope differs')
        folder = native/'packed'/arm
        packing_path = folder/'packing_receipt.json'
        packing = read_json(packing_path,'PASS')
        capture_path = native/'compact'/arm/'capture_receipt.json'
        recount_path = native/'compact'/arm/'raw_recount_receipt.json'
        capture = read_json(capture_path,'COMPLETE')
        recount = read_json(recount_path,'PASS')
        for key,path in (('packing_receipt_sha256',packing_path),('capture_receipt_sha256',capture_path),
                         ('raw_recount_sha256',recount_path)):
            require(prior.identity(path)['sha256'] == proof['arms'][arm][key], 'native receipt binding differs')
        require(packing['capture_receipt_sha256'] == prior.identity(capture_path)['sha256'] and
                packing['raw_recount_sha256'] == prior.identity(recount_path)['sha256'] and
                recount['capture_receipt_sha256'] == prior.identity(capture_path)['sha256'], 'native chain differs')
        files = {r['name']:r for r in packing['outputs']}
        originals = {r['name']:r for r in capture['outputs']}
        require(len(files) == len(packing['outputs']) and set(files) == set(originals) and files,
                'packed inventory differs')
        for name,row in files.items():
            require(Path(name).name == name and row['source_sha256'] == originals[name]['sha256'], 'unsafe or changed packed source')
            actual = prior.identity(folder/name)
            require(actual['sha256'] == row['sha256'] and actual['size_bytes'] == row['size_bytes'], 'packed bytes differ')
            inputs.append(actual)
        inputs += [prior.identity(p) for p in (packing_path,capture_path,recount_path)]
        inventories[arm] = files
    points = read_csv(points_path)
    columns = read_csv(columns_path)
    require([int(r['flat_index_yx']) for r in points] == [12000,12001,12002], 'point contract differs')
    cells = [(int(r['i_fortran']),int(r['j_fortran'])) for r in columns]
    require(len(set(cells)) == len(cells) == 8, 'column contract differs')
    schema = json.loads(schema_path.read_text())
    require(schema['phase_window_steps'] == [[361,540]], 'detailed time window differs')
    for phase in (35,36):
        require(tuple(schema['phases'][str(phase)]['fields']) == ACT_FIELDS, 'activation field order differs')
    return inputs,inventories,points,cells,schema


def activation_changes(before, after):
    """Observed stored-state changes, including source REAL32 rounding."""
    held = (0,6,7,8,9,10,11)
    require(np.array_equal(before[...,held].view(np.uint32),after[...,held].view(np.uint32)),
            'activation constants changed')
    inactive = before[...,0] <= 0
    require(np.array_equal(before[inactive].view(np.uint32),after[inactive].view(np.uint32)),
            'inactive activation changes state')
    return after[...,ACT_INDICES].astype(np.float64)-before[...,ACT_INDICES].astype(np.float64)


def reservoir_limits(before, after):
    low,high = np.float32(1e8),np.float32(2e10)
    expected = np.minimum(np.maximum(before,low),high)
    require(np.array_equal(expected.view(np.uint32),after.view(np.uint32)), 'NN limit differs from source')
    change = after.astype(np.float64)-before.astype(np.float64)
    return np.where(before < low,change,0.),np.where(before > high,-change,0.)


def surface_end(records, steps, cells, loops, fields):
    keys,bits = records
    selected = keys[:,10] == 43
    keys,values = keys[selected],bits[selected]
    require(len(keys) == len(steps)*len(cells)*loops, 'surface coverage differs')
    lookup = {cell:i for i,cell in enumerate(cells)}
    columns = np.array([lookup[int(i),int(j)] for i,j in zip(keys[:,4],keys[:,3])])
    index = (keys[:,0]-steps[0],columns,keys[:,6]-1)
    require(np.all(keys[:,7] == loops) and np.all(keys[:,5] == 1), 'surface axes differ')
    linear = np.ravel_multi_index(index,(len(steps),len(cells),loops))
    require(len(np.unique(linear)) == len(linear), 'duplicate surface position')
    result = np.empty((len(steps),len(cells),loops),np.float32)
    field = fields.index('rain')
    require(np.all(keys[:,11] > field), 'surface rain field absent')
    result[index] = values[:,field].copy().view(np.float32)
    require(np.isfinite(result).all() and np.all(result >= 0), 'invalid cumulative RAINNC')
    return result[:,:,-1]


def write_csv(path, rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def run(output):
    if os.path.lexists(output):
        raise FileExistsError(output)
    inputs,inventories,points,cells,schema = bind_inputs()
    indices,weights = geometry.geometry(points,np.array([p[0] for p in cells]),np.array([p[1] for p in cells]))
    wrapper_path = BUNDLE/'native/runs/read_wrapper.py'
    inputs += [prior.identity(wrapper_path),prior.identity(Path(prior.__file__)),prior.identity(Path(geometry.__file__))]
    spec=importlib.util.spec_from_file_location('weak_native_wrapper',wrapper_path)
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.weak-activation-',dir=output.parent))
    ledgers=[];surface_rows=[];arm_data={};native_counts={}
    try:
        for arm,loops in ARMS.items():
            folder=BUNDLE/'native/packed'/arm
            chunks={name:[] for name in ('activation_pre','activation_post','activation_delta','nn_lower_restore','nn_upper_remove','final_nn_return','main_qr_delta','sed_rsg_qr_delta','entry')}
            for first in range(361,541,3):
                steps=tuple(range(first,first+3))
                state=prior.load_group(folder,inventories[arm],'state',first)
                pre=prior.dense_phase(state,35,steps,cells,loops,tuple(range(12)))
                post=prior.dense_phase(state,36,steps,cells,loops,tuple(range(12)))
                require(np.all(pre[...,9] == np.float32(20/loops)), 'activation time step differs')
                changes=activation_changes(pre,post)
                before=prior.dense_phase(state,33,steps,cells,loops,(13,))[...,0]
                after=prior.dense_phase(state,34,steps,cells,loops,(13,))[...,0]
                lower,upper=reservoir_limits(before,after)
                core=prior.load_group(folder,inventories[arm],'core',first)
                for name,a,b in (('main_qr_delta',6,8),('sed_rsg_qr_delta',9,10)):
                    delta=prior.source_stage(core,a,b,steps,cells,loops,schema)[...,3]
                    chunks[name].append(np.where(np.isfinite(delta).all(axis=3),delta.sum(axis=3),np.nan))
                nn=[]
                for phase in (11,12):
                    n=schema['phases'][str(phase)]['fields'].index('nci(i,k,3)')
                    nn.append(prior.dense_phase(core,phase,steps,cells,loops,(n,))[...,0])
                chunks['activation_pre'].append(pre);chunks['activation_post'].append(post)
                chunks['activation_delta'].append(changes.sum(axis=3))
                chunks['nn_lower_restore'].append(lower.sum(axis=3));chunks['nn_upper_remove'].append(upper.sum(axis=3))
                chunks['final_nn_return'].append((nn[1].astype(np.float64)-nn[0].astype(np.float64)).sum(axis=3))
                chunks['entry'].append(prior.dense_phase(state,30,steps,cells,loops,prior.STATE_INDICES)[:,:,:,0])
            data={name:np.concatenate(values) for name,values in chunks.items()}
            native_counts[arm]=len(STEPS)*len(cells)*39*loops
            for name,sid in (('public_entry',6),('public_return',7)):
                paths=[folder/n for n in inventories[arm] if n.startswith('state_selected_'+('entry' if sid==6 else 'return'))]
                values,_=reader.read_wrapper(paths,sid,STEPS,cells)
                data[name]=values[..., [reader.FIELDS.index(f) for f in prior.PUBLIC]]
            observed={name:prior.weighted(value.astype(np.float64),indices,weights) for name,value in data.items()}
            np.savez_compressed(stage/(arm+'.npz'),step=np.array(STEPS,np.int32),point=np.array([12000,12001,12002]),
                                activation_fields=np.array(ACT_FIELDS),delta_fields=np.array(DELTA_FIELDS),
                                source_fields=np.array(prior.FIELDS),public_fields=np.array(prior.PUBLIC),**observed)
            # RAINNC at the end of each outer step; hour 3 is 360→540.
            surfaces=[]
            for first in range(1,541,3):
                records=prior.load_group(folder,inventories[arm],'surface',first)
                surfaces.append(surface_end(records,tuple(range(first,first+3)),cells,loops,schema['phases']['43']['fields']))
            cumulative=np.concatenate(surfaces)[359:540]
            require(np.all(np.diff(cumulative.astype(np.float64),axis=0) >= 0), 'cumulative RAINNC reset')
            # Match the frozen remapper's sequential four-corner arithmetic.
            reference_path=BUNDLE/'cohorts/parent_surface_corners_0_3h.npz'
            with np.load(reference_path,allow_pickle=False) as reference:
                mapped=interpolate(cumulative[:,indices].astype(np.float64),reference['u'][None],reference['v'][None])
                rainc=interpolate(reference[arm][:,:,0,:].astype(np.float64),reference['u'][:,None],reference['v'][:,None])
                require(np.all(rainc[:,3]-rainc[:,2] == 0), 'hour-3 RAINC is not zero')
            rain=mapped-mapped[0]
            np.savez_compressed(stage/(arm+'_surface.npz'),step=np.arange(360,541,dtype=np.int32),point=np.array([12000,12001,12002]),rainnc_since_hour_start=rain)
            for p,point in enumerate(points):
                expected=float(point[('FIRST_ICE_VELOCITY' if arm=='CONTROL' else 'MP10')+'_h3_mm'])
                require(abs(rain[-1,p]-expected) <= 1e-10, 'RAINNC trace does not reproduce sealed hourly total')
                surface_rows.append({'arm':arm,'point':int(point['flat_index_yx']),'reference_mm':float(point['reference_h3_mm']),
                                     'sealed_hour3_total_mm':expected,'native_hour3_rainnc_mm':float(rain[-1,p]),
                                     'difference_mm':float(rain[-1,p]-expected)})
            arm_data[arm]=data
        # Collapse each arm's actual inner loops before paired comparisons.
        paired={name:prior.paired(arm_data['MP10'][name],arm_data['CONTROL'][name],indices,weights)
                for name in ('activation_delta','nn_lower_restore','nn_upper_remove','final_nn_return','main_qr_delta','sed_rsg_qr_delta','entry','public_entry','public_return')}
        np.savez_compressed(stage/'paired.npz',step=np.array(STEPS,np.int32),point=np.array([12000,12001,12002]),
                            delta_fields=np.array(DELTA_FIELDS),source_fields=np.array(prior.FIELDS),public_fields=np.array(prior.PUBLIC),**paired)
        local,external,change,residual=prior.ledger(paired['public_entry'],paired['public_return'])
        for p,point in enumerate(points):
            for k in range(39):
                for f,field in enumerate(prior.PUBLIC):
                    ledgers.append({'point':int(point['flat_index_yx']),'k':k+1,'field':field,
                                    'entry_difference':float(paired['public_entry'][0,p,k,f]),'local_sum':float(local[p,k,f]),
                                    'between_calls_sum':float(external[p,k,f]),'difference_change':float(change[p,k,f]),
                                    'closure_residual':float(residual[p,k,f])})
        write_csv(stage/'public_ledger.csv',ledgers);write_csv(stage/'surface_check.csv',surface_rows)
        for item in inputs:
            require(prior.identity(item['path']) == item,'input changed')
        summary={'status':'COMPLETE','points':3,'columns':8,'levels':39,'steps':[361,540],
                 'native_activation_pairs':native_counts,'public_ledger_rows':len(ledgers),'surface_checks':len(surface_rows),
                 'scope':['Observed per-loop activation states are descriptive; paired effects sum actual loops before native differencing and weighting.',
                          'Internal NC/NN are per volume; public moment mixing ratios stay separate.',
                          'Lower restoration and upper removal are distinct; number changes are not water mass.',
                          'Surface comparison is RAINNC only; total agreement requires the independently checked zero RAINC hour-3 increments.',
                          'Local and between-call changes are bookkeeping, not process causal contributions.']}
        (stage/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        (stage/'receipt.json').write_text(json.dumps({'status':'COMPLETE','inputs':inputs,
             'outputs':{p.name:prior.identity(p)['sha256'] for p in stage.iterdir()}},indent=2)+'\n')
        evaluation.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
