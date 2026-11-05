#!/usr/bin/env python3
"""Bind cumulative native rain bits and independently project hourly components."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
PROTOCOL = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/state/protocol.json'
PROTOCOL_SHA = '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690'
COHORT_SHA = {'selected_points.csv':'3343201b904a9b9874fea8f174715e37f1d642871f371bf1f378ed8a13a62197',
              'point_corners.csv':'b5d4de1d9209048e6e157ec8d5fe801f8464ee0b9fe307f5656cff32e09923fa',
              'unique_global_corners.csv':'c2ba19be993cd82dfeac0ff1b3a02659d6c137b733903e563da91f4024aa65b9'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, data):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader(); writer.writerows(data)


def run(output):
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(output)
    if sha(PROTOCOL) != PROTOCOL_SHA:
        raise ValueError('prior state protocol changed')
    folder = BUNDLE / 'cohorts/results'
    for name, pin in COHORT_SHA.items():
        if sha(folder/name) != pin:
            raise ValueError('cohort changed: '+name)
    points = rows(folder/'selected_points.csv'); corners = rows(folder/'point_corners.csv')
    cells = rows(folder/'unique_global_corners.csv')
    if (len(points),len(corners),len(cells)) != (39,156,123):
        raise ValueError('cohort scope differs')
    protocol = json.loads(PROTOCOL.read_text()); native=[]; projected=[]; inputs=[]
    by_point = {p['point_id']:[c for c in corners if c['point_id']==p['point_id']] for p in points}
    history = {}
    for arm,model in [('B1','IMPROVED_BG_FIXED'),('DM065','B1_RAIN_NUMBER_DM065')]:
        history[arm]={}
        for hour in range(3):
            pin = protocol['case_time_files'][arm][f'h{hour:02}'];path=Path(pin['path'])
            if path.stat().st_size!=pin['size_bytes'] or sha(path)!=pin['sha256']:
                raise ValueError('source history changed: '+str(path))
            with Dataset(path) as ds:
                time=b''.join(ds.variables['Times'][0].tolist()).decode()
                if time != f'2026-08-16_{12+hour:02}:00:00':
                    raise ValueError('history time differs')
                data={}
                for name in ['RAINNC','RAINC']:
                    var=ds.variables[name];var.set_auto_maskandscale(False)
                    value=np.asarray(var[0],dtype=np.float64)
                    if value.shape!=(282,234) or not np.isfinite(value).all():
                        raise ValueError('invalid surface grid')
                    data[name]=value
            if sha(path)!=pin['sha256']:
                raise ValueError('source changed during read')
            inputs.append({'arm':arm,'hour':hour,**pin});history[arm][hour]=data
            for cell in cells:
                j,i=int(cell['native_j_zero_based']),int(cell['native_i_zero_based'])
                row={'arm':arm,'hour':hour,'wrf_i_1based':i+1,'wrf_j_1based':j+1}
                for name in ['RAINNC','RAINC']:
                    row[name]=float(data[name][j,i]);row[name+'_float32_le_hex']=np.asarray(data[name][j,i],dtype='<f4').tobytes().hex()
                native.append(row)
        for hour in [1,2]:
            array_path=ROOT/f'docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065/hour_{12+hour}_arrays.npz'
            with np.load(array_path,allow_pickle=False) as expected:
                for point in points:
                    cs=by_point[point['point_id']];components={};magnitude=0.
                    if len(cs)!=4 or not math.isclose(math.fsum(float(c['weight']) for c in cs),1.,abs_tol=1e-12):
                        raise ValueError('point corners incomplete')
                    for name in ['RAINNC','RAINC']:
                        terms=[]
                        for c in cs:
                            j,i=int(c['native_j_zero_based']),int(c['native_i_zero_based']);w=float(c['weight'])
                            current,previous=history[arm][hour][name][j,i],history[arm][hour-1][name][j,i]
                            if current<previous:
                                raise ValueError('negative hourly component')
                            terms.append(w*(current-previous));magnitude+=abs(w*current)+abs(w*previous)
                        components[name]=math.fsum(terms)
                    index=int(point['sample_index_zero_based'])
                    if int(expected['flat_index_yx'][index])!=int(point['flat_index_yx']):
                        raise ValueError('sample identity differs')
                    total=math.fsum(components.values());canonical=float(expected[model][index]);residual=total-canonical
                    eps=np.finfo(np.float64).eps;bound=64*eps/(1-64*eps)*magnitude
                    if abs(residual)>bound:
                        raise ValueError('hourly total mismatch beyond arithmetic bound')
                    projected.append({'arm':arm,'point_id':point['point_id'],'flat_index_yx':point['flat_index_yx'],'lead_hour':hour,
                                      'RAINNC_hour_mm':components['RAINNC'],'RAINC_hour_mm':components['RAINC'],
                                      'total_hour_mm':total,'canonical_hour_mm':canonical,'residual_mm':residual,'gamma64_bound_mm':bound})
    if len(native)!=738 or len(projected)!=156:
        raise ValueError('reference row count differs')
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.surface-ref-',dir=output.parent))
    try:
        write_csv(stage/'native_surface.csv',native);write_csv(stage/'point_components.csv',projected)
        receipt={'status':'PASS','source_sha256':sha(Path(__file__)),'prior_protocol_sha256':PROTOCOL_SHA,'cohort_sha256':COHORT_SHA,
                 'history_inputs':inputs,'native_rows':738,'point_component_rows':156,'max_total_residual_mm':max(abs(x['residual_mm']) for x in projected),
                 'units':'Cumulative and hourly precipitation mm; raw words explicit IEEE float32 little-endian hex',
                 'scope':'RAINNC for KDM6 surface check; RAINC separate; scalar component projection not a full water budget',
                 'outputs':{p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if os.path.lexists(output):raise FileExistsError(output)
        os.rename(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)
    print('PASS738native/156component rows',receipt['max_total_residual_mm'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
