#!/usr/bin/env python3
"""Replay selected native process boundaries from the sealed MP10 capture.

No model is run. Values are native REAL32 promoted before subtraction; actual
substeps and inner loops are resolved within each arm before spatial weighting.
"""
import argparse
import csv
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import cp02_mp10_process as prior
from cp02_ice_false_alarm import evaluation

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_mp10_process_20261110'
NATIVE = BUNDLE / 'native'
POINTS = (12446, 12892, 9774, 12300)
CONSTANTS_SOURCE = ROOT / 'docs/evidence/cp02_activation_path_20261110/reference/module_model_constants.F'
CONSTANTS_SHA = '5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062'
TERMS = ('praut', 'pracw', 'prevp', 'paacw', 'paacw', 'pseml', 'pgeml')
SIGNS = (1, 1, 1, 1, 1, -1, -1)


def select_points(path, ids):
    with path.open() as stream:
        selected_rows = [r for r in csv.DictReader(stream) if int(r['flat_index_yx']) in ids]
    selected = {int(r['flat_index_yx']): r for r in selected_rows}
    if set(selected) != set(ids) or len(selected_rows) != len(selected):
        raise ValueError('selected point missing or duplicated')
    return selected


def corners(point):
    i, j = int(point['native_i0_fortran_one_based']), int(point['native_j0_fortran_one_based'])
    weights = [float(point[f'weight_j{dj}_i{di}']) for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1))]
    if min(weights) < 0 or not np.isclose(sum(weights), 1):
        raise ValueError('invalid interpolation weights')
    return [(i, j, w) for (i, j), w in zip(((i,j),(i+1,j),(i,j+1),(i+1,j+1)), weights)]


def fields(schema, phase):
    if phase == 10:
        return schema['arm_overrides']['CONTROL and MP10']['phase_10_fields']
    return schema['phases'][str(phase)]['fields']


def load_records(folder, arm, steps, cells, level, schema):
    receipt = json.loads((folder / 'packing_receipt.json').read_text())
    if receipt['status'] != 'PASS':
        raise ValueError('packing receipt failed')
    inventory = {row['name']: row for row in receipt['outputs']}
    records, used = {}, []
    for first in sorted({1 + (step-1)//3*3 for step in steps}):
        for group, phases in (('core', {5,6,7,8,10,11,12,21}), ('state', {33,34})):
            names = sorted(n for n in inventory if n.startswith(f'{group}_{first:06d}_') and n.endswith('.npz'))
            if not names:
                raise ValueError(f'{arm} missing {group} chunk {first}')
            for name in names:
                actual = prior.identity(folder/name)
                if actual['sha256'] != inventory[name]['sha256'] or actual['size_bytes'] != inventory[name]['size_bytes']:
                    raise ValueError(f'packed artifact mismatch: {name}')
                used.append(actual)
            keys, bits = prior.load_group(folder, names, group, first)
            mask = np.isin(keys[:,0], steps) & (keys[:,5] == level) & np.isin(keys[:,10], list(phases))
            for key, data in zip(keys[mask], bits[mask]):
                step, rank, call, j, i, k, loop, loops, substep, mstep, phase, nfields = map(int, key)
                if (i,j) not in cells:
                    continue
                names_phase = fields(schema, phase)
                if nfields != len(names_phase):
                    raise ValueError(f'phase {phase} field count mismatch')
                record_key = (step,i,j,loop,phase,substep)
                if record_key in records:
                    raise ValueError(f'duplicate native record: {record_key}')
                records[record_key] = (loops, mstep, dict(zip(names_phase, data[:nfields].copy().view(np.float32))))
    return records, used


def boundary(records, step, i, j, loop, phase, last=False):
    matches = [(key, value) for key,value in records.items()
               if key[:5] == (step,i,j,loop,phase)]
    if not matches:
        return None
    if last:
        matches.sort(key=lambda x:x[0][5])
        key, (loops, mstep, values) = matches[-1]
        if key[5] != mstep or [x[0][5] for x in matches] != list(range(1,mstep+1)):
            raise ValueError('incomplete warm sedimentation substeps')
        return values
    if len(matches) != 1 or matches[0][0][5] != 0:
        raise ValueError('unexpected boundary multiplicity')
    return matches[0][1][2]


def delta(before, after, a, b=None):
    if before is None or after is None:
        return None
    return float(after[b or a]) - float(before[a])


def main_qr(before, after, rates):
    if before is None or after is None or rates is None:
        return {}, None, None
    dt = before['dtcld']
    contributions = {}
    for term, sign in zip(TERMS, SIGNS):
        if term == 'paacw' and term in contributions:
            continue
        factor = 2 if term == 'paacw' else 1
        contributions[term] = float(rates[f'{term}(i,k)']) * float(dt) * sign * factor
    # The original equation adds in source order, rounds each REAL32 operation,
    # multiplies by dt, adds QR and applies max. It is not a sum of rounded terms.
    expr = rates['praut(i,k)']
    for term, sign in zip(TERMS[1:], SIGNS[1:]):
        value = rates[f'{term}(i,k)']
        expr = np.float32(expr + value if sign == 1 else expr - value)
    predicted = max(np.float32(before['qrs(i,k,1)'] + np.float32(expr * dt)), np.float32(0))
    observed = float(after['qrs(i,k,1)']) - float(before['qrs(i,k,1)'])
    return contributions, observed, float(after['qrs(i,k,1)']) - float(predicted)


def warm_lower_bound(temperature, freezing, cpm, snow, graupel, ice):
    """Outward REAL32 bound for melting all three available frozen reservoirs."""
    values = (temperature, freezing, cpm, snow, graupel, ice)
    if any(v is None or not np.isfinite(v) for v in values) or cpm <= 0 or min(snow,graupel,ice) < 0:
        return None
    up = lambda x: np.nextafter(np.float32(x), np.float32(np.inf), dtype=np.float32)
    down = lambda x: np.nextafter(np.float32(x), np.float32(-np.inf), dtype=np.float32)
    ratio = up(np.float32(np.float32(350000.) / np.float32(cpm)))
    lower = np.float32(temperature)
    for reservoir in (snow,graupel,ice):
        cooling = up(np.float32(ratio * np.float32(reservoir)))
        lower = down(np.float32(lower - cooling))
    return float(lower) - float(np.float32(freezing))


def native_rows(records, arm, point_id, point, steps, level, freezing):
    for step in steps:
        for i,j,weight in corners(point):
            loop_counts = {v[0] for key,v in records.items() if key[0] == step and key[1:3] == (i,j)}
            if len(loop_counts) != 1:
                raise ValueError('missing or inconsistent loop count')
            loops = loop_counts.pop()
            if loops != {'CONTROL': 1, 'MP10': 2}[arm]:
                raise ValueError('unexpected captured loop count')
            for loop in range(1,loops+1):
                p = {phase:boundary(records,step,i,j,loop,phase,phase in (10,21))
                     for phase in (5,6,7,8,10,11,12,21,33,34)}
                row = dict(point=point_id,arm=arm,step=step,i=i,j=j,k=level,weight=weight,loop=loop,loops=loops)
                warm = [v[1] for key,v in records.items() if key[:5] == (step,i,j,loop,10)]
                row['warm_substeps'] = warm[-1] if warm else None
                row['temperature_10'] = float(p[10]['t(i,k)']) if p[10] else None
                row['temperature_6'] = float(p[6]['t(i,k)']) if p[6] else None
                if p[10] and p[21] and p[7]:
                    if p[10]['t(i,k)'].view(np.uint32) != p[21]['t(i,k)'].view(np.uint32):
                        raise ValueError('ice sedimentation changed temperature')
                    row['warm_bound_margin_k'] = warm_lower_bound(
                        p[10]['t(i,k)'], freezing, p[7]['cpm(i,k)'],
                        p[10]['qrs(i,k,2)'], p[10]['qrs(i,k,3)'], p[21]['qci(i,k,2)'])
                else:
                    row['warm_bound_margin_k'] = None
                for label,a,b,field_a,field_b in (
                    ('activation_nn',8,11,'nci(i,k,3)',None), ('activation_qv',8,11,'q(i,k)',None),
                    ('combined_nc',8,11,'nci(i,k,1)',None), ('combined_qc',8,11,'qci(i,k,1)',None),
                    ('final_nn',11,12,'nci(i,k,3)',None), ('floor_nn',33,34,'nci3',None),
                    ('pre_main_qr',10,6,'qrs(i,k,1)',None), ('pre_main_qs',10,6,'qrs(i,k,2)',None),
                    ('pre_main_qg',10,6,'qrs(i,k,3)',None), ('pre_main_qv',10,6,'q(i,k)',None),
                    ('pre_main_t',10,6,'t(i,k)',None)):
                    row[label] = delta(p[a],p[b],field_a,field_b)
                for phase in (8,11,12,33,34):
                    field = 'nci3' if phase in (33,34) else 'nci(i,k,3)'
                    row[f'nn_{phase}'] = float(p[phase][field]) if p[phase] else None
                contrib, row['main_qr'], row['main_qr_replay_error'] = main_qr(p[6],p[8],p[5])
                for term in dict.fromkeys(TERMS):
                    row['exposure_'+term] = contrib.get(term)
                yield row


def aggregate(rows):
    """Sum loops per native corner and arm, subtract arms, then weight corners."""
    metrics = [k for k in rows[0] if k.startswith(('activation_', 'combined_', 'final_', 'floor_', 'pre_main_', 'main_qr', 'exposure_'))]
    groups = {}
    for row in rows:
        key = (row['point'],row['step'],row['i'],row['j'],row['arm'])
        groups.setdefault(key,[]).append(row)
    result = []
    for point,step in sorted({(r['point'],r['step']) for r in rows}):
        output = {'point':point,'step':step,'k':rows[0]['k']}
        cells = sorted({(r['i'],r['j'],r['weight']) for r in rows if r['point']==point and r['step']==step})
        for metric in metrics:
            values = []
            for i,j,w in cells:
                if w == 0:
                    continue
                sums = []
                for arm in ('CONTROL','MP10'):
                    items = groups.get((point,step,i,j,arm),[])
                    if not items or len(items) != items[0]['loops'] or any(r[metric] is None for r in items):
                        sums.append(None)
                    else:
                        sums.append(sum(r[metric] for r in items))
                values.append(None if None in sums else (sums[1]-sums[0])*w)
            output[metric] = None if any(v is None for v in values) else sum(values)
        result.append(output)
    return result


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def verify_inputs(inputs):
    for recorded in inputs:
        if prior.identity(recorded['path']) != recorded:
            raise ValueError('input changed during replay: ' + recorded['path'])


def validate_coverage(rows, paired, points, steps, level):
    expected = {(point_id, step, i, j, arm, loop)
                for point_id, point in points.items() for step in steps
                for i,j,_weight in corners(point)
                for arm,loops in (('CONTROL',1),('MP10',2)) for loop in range(1,loops+1)}
    actual = [(r['point'],r['step'],r['i'],r['j'],r['arm'],r['loop']) for r in rows]
    pairs = [] if paired is None else [(r['point'],r['step']) for r in paired]
    if len(actual) != 432 or len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError('native replay coverage differs')
    if paired is None:
        return
    if (len(pairs) != 36 or len(set(pairs)) != len(pairs)
            or set(pairs) != {(p,s) for p in points for s in steps}
            or any(r['k'] != level for r in rows + paired)):
        raise ValueError('paired replay coverage differs')


def run(out, steps=range(982,991), ids=POINTS, level=16):
    out = Path(out)
    steps, ids = tuple(steps), tuple(ids)
    if steps != tuple(range(982,991)) or ids != POINTS or level != 16:
        raise ValueError('this replay requires its fixed selected scope')
    if os.path.lexists(out):
        raise FileExistsError(out)
    points_path = BUNDLE/'cohorts/selected_points.csv'
    schema_path = NATIVE/'schema/schema.json'
    proof_path = NATIVE/'proof/comparability.json'
    source_receipt = NATIVE/'source/source_receipt.json'
    provenance = [points_path,points_path.parent/'native_columns.csv',points_path.parent/'receipt.json',
                  schema_path,proof_path,CONSTANTS_SOURCE,source_receipt,
                  Path(__file__).resolve(),Path(prior.__file__).resolve(),
                  Path(prior.publication.__file__).resolve(),Path(evaluation.__file__).resolve(),
                  *(NATIVE/'source'/f'{arm}.f90' for arm in ('CONTROL','MP10'))]
    inputs = [prior.identity(p) for p in provenance]
    schema = json.loads(schema_path.read_text())
    proof = json.loads(proof_path.read_text())
    if proof['status'] != 'PASS' or prior.identity(schema_path)['sha256'] != proof['schema_sha256']:
        raise ValueError('capture proof or schema mismatch')
    if prior.identity(source_receipt)['sha256'] != proof['source_receipt_sha256']:
        raise ValueError('source receipt proof mismatch')
    source_pin = json.loads(source_receipt.read_text())
    for arm in ('CONTROL','MP10'):
        if prior.identity(NATIVE/'source'/f'{arm}.f90')['sha256'] != source_pin['arms'][arm]['source_sha256']:
            raise ValueError('captured source mismatch: ' + arm)
    cohort = json.loads((points_path.parent/'receipt.json').read_text())
    if (prior.identity(points_path)['sha256'] != prior.POINTS_SHA or cohort.get('status') != 'COMPLETE'
            or cohort['outputs'][points_path.name] != prior.POINTS_SHA
            or prior.identity(points_path.parent/'native_columns.csv')['sha256'] != proof['selector_sha256']
            or cohort['outputs']['native_columns.csv'] != proof['selector_sha256']):
        raise ValueError('point selection mismatch')
    if prior.identity(CONSTANTS_SOURCE)['sha256'] != CONSTANTS_SHA:
        raise ValueError('host constants source mismatch')
    points = select_points(points_path,ids)
    cells = {(i,j) for point in points.values() for i,j,w in corners(point)}
    rows = []
    for arm in ('CONTROL','MP10'):
        folder = NATIVE/'packed'/arm
        packing_identity = prior.identity(folder/'packing_receipt.json')
        inputs.append(packing_identity)
        if packing_identity['sha256'] != proof['arms'][arm]['packing_receipt_sha256']:
            raise ValueError('packing proof mismatch')
        records, used = load_records(folder,arm,steps,cells,level,schema)
        packing = json.loads((folder/'packing_receipt.json').read_text())
        inventory = {r['name']: r for r in packing['outputs']}
        freezing_values = []
        for first in sorted({1 + (step-1)//3*3 for step in steps}):
            names = sorted(n for n in inventory if n.startswith(f'constants_{first:06d}_') and n.endswith('.npz'))
            if not names:
                raise ValueError('missing captured constants')
            for name in names:
                identity = prior.identity(folder/name)
                if identity['sha256'] != inventory[name]['sha256'] or identity['size_bytes'] != inventory[name]['size_bytes']:
                    raise ValueError('captured constants hash mismatch')
                used.append(identity)
            keys, bits = prior.load_group(folder,names,'constants',first)
            freezing_values.extend(bits[np.isin(keys[:,0],steps),1].tolist())
        if len(set(freezing_values)) != 1:
            raise ValueError('missing or inconsistent captured freezing point')
        freezing = np.array(freezing_values[0],dtype=np.uint32).view(np.float32)[()]
        inputs.extend(used)
        for point_id, point in points.items():
            rows.extend(native_rows(records,arm,point_id,point,steps,level,freezing))
    validate_coverage(rows,None,points,steps,level)
    paired = aggregate(rows)
    validate_coverage(rows,paired,points,steps,level)
    verify_inputs(inputs)
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.'+out.name+'-',dir=out.parent))
    try:
        output_names = ('native_loops.csv','paired_weighted.csv')
        write_csv(stage/output_names[0],rows)
        write_csv(stage/output_names[1],paired)
        output_hashes = {name:prior.identity(stage/name)['sha256'] for name in output_names}
        verify_inputs(inputs)
        receipt = {'status':'PASS','source':'sealed packed data; no model run',
                   'points':list(ids),'steps':list(steps),'k':level,
                   'native_rows':len(rows),'paired_rows':len(paired),
                   'inputs':inputs,'outputs':output_hashes}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if os.path.lexists(out):
            raise FileExistsError(out)
        evaluation.publish_new(stage,out)
    finally:
        if stage.exists():
            shutil.rmtree(stage)



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.output)


if __name__ == '__main__':
    main()
