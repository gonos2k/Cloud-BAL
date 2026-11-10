#!/usr/bin/env python3
"""Freeze raw hourly corners and reproduce 0–3 h point totals from parent histories."""
import csv,hashlib,importlib.util,json,sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

BUNDLE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools'))
import cp02_ice_surface_components as surface

spec=importlib.util.spec_from_file_location('parent_surface',ROOT/'docs/evidence/cp02_mp10_process_20261110/surface/extract.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
PIN=ROOT/'docs/evidence/cp02_activation_path_20261110/native/runs/reference_pins.json'
WORK=ROOT.parent.parent

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    points=list(csv.DictReader((BUNDLE/'selected_points.csv').open()))
    if [int(p['flat_index_yx']) for p in points]!=[12000,12001,12002]:raise ValueError('point ids differ')
    inv,_,_,_,_=surface.module(surface.EVAL).load_reference(surface.REFERENCE,surface.ANALYSIS)
    j=np.array([int(p['native_j0_zero_based']) for p in points]);i=np.array([int(p['native_i0_zero_based']) for p in points])
    u=np.array([float(p['weight_j0_i1'])+float(p['weight_j1_i1']) for p in points]);v=np.array([float(p['weight_j1_i0'])+float(p['weight_j1_i1']) for p in points])
    # Use original mapped u/v values, not sums of rounded printed weights.
    with np.load(ROOT/'docs/evidence/cp02_pulse_path_20261110/evaluation/results/bilinear_mapping.npz') as m:
        y,x=np.unravel_index([12000,12001,12002],m['valid'].shape);u=m['u'][y,x].copy();v=m['v'][y,x].copy()
    pins=json.loads(PIN.read_text());rows=[];raw={};history={}
    for arm,case in [('CONTROL','FIRST_ICE_VELOCITY'),('MP10','MP10')]:
        directory=WORK/'b1_pulse_path_20261110/runtime/forecasts'/arm;fields=[]
        for h in range(12,19):
            name=f'wrfout_d01_2026-08-16_{h:02d}:00:00';path=directory/name
            actual=sha(path)
            if actual!=pins[arm]['history_sha256'][name]:raise ValueError('parent history differs')
            fields.append(parent.extract_snapshot(path,datetime(2026,8,16,h,tzinfo=timezone.utc),inv,j,i));history[f'{arm}/{name}']=actual
        corners=np.stack(fields,axis=1);components,total=surface.replay(corners,u,v,1e-6);raw[arm]=corners[:,:4].copy()
        for n,point in enumerate(points):
            for lead in range(1,4):
                expected=float(point[f'{case}_h{lead}_mm'])
                if total[n,lead-1]!=expected:raise ValueError(f'normalized forecast differs: {arm} {point["flat_index_yx"]} {lead}')
                rows.append({'arm':arm,'flat_index_yx':point['flat_index_yx'],'lead_hour':lead,'rainc_mm':float(components[n,lead-1,0]),'rainnc_mm':float(components[n,lead-1,1]),'total_mm':float(total[n,lead-1])})
    out=BUNDLE/'parent_surface_corners_0_3h.npz';np.savez_compressed(out,**raw,u=u,v=v,flat_index_yx=np.array([12000,12001,12002],dtype=np.int32))
    csvpath=BUNDLE/'parent_surface_normalized_1_3h.csv'
    with csvpath.open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    result={'status':'PASS','method':'parent surface evaluator: clip cumulative corners, add RAINC+RAINNC at native corners, bilinear remap, difference and clip; exact equality against sealed hourly total','axes':'point,history 0..3, component RAINC/RAINNC, corner 00/10/01/11','source_history_sha256':history,'reference_pins_sha256':sha(PIN),'selected_points_sha256':sha(BUNDLE/'selected_points.csv'),'raw_corners_sha256':sha(out),'normalized_csv_sha256':sha(csvpath),'generator_sha256':sha(Path(__file__))}
    (BUNDLE/'parent_surface_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
