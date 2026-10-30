#!/usr/bin/env python3
"""Score fixed-H QR/QS factorial interventions against the pinned earlier runs."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
COMMON = ROOT/'docs/evidence/first_hour_zero_rate_20261030/ablation_scoring/score_ablation.py'
COMMON_SHA = '9796a3c0853b3109c56430608a96c2d6b53db4137f9a231d08d0aec62c2e32f5'
PRIOR = COMMON.parent/'results'
PREP_SHA = '659deae74e711c508961d0a8cf1444da9262a7ad982f025fd99484e004decc61'
CASES = {'H_ORIGINAL_QR': ('QRAIN','fc71203e9cce20a1aabc0297d353de7a8879ee6463be6221278a33e76196771d'),
         'H_ORIGINAL_QS': ('QSNOW','c9e5458ab5ffaf5e96a473858d46d430f3f07d99910ffee742296b1443a33d79')}
PAIRED_SHA = '19f9ee9c1d5bb3e4a39a39d7ebce4780a51fb1b0d6e2d56475d4179a0396f5c3'
RECEIPT_SHA = '44c512e1d8f8f35849cb368485da7b3e85f7883edc0863f448761dec9aa316d9'
NAMES = ('FIX_H','H_ORIGINAL_QR','H_ORIGINAL_QS','H_ORIGINAL_QRQS')


def load_common():
    if hashlib.sha256(COMMON.read_bytes()).hexdigest()!=COMMON_SHA: raise ValueError('prior ablation scorer changed')
    spec=importlib.util.spec_from_file_location('prior_ablation_scorer',COMMON)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def verify_single_field(base,donor,candidate,field,common):
    with Dataset(base) as a, Dataset(donor) as b, Dataset(candidate) as c:
        for d in (a,b,c):d.set_auto_mask(False)
        if (set(a.variables)!=set(b.variables) or set(a.variables)!=set(c.variables)
            or set(a.dimensions)!=set(b.dimensions) or set(a.dimensions)!=set(c.dimensions)
            or not common.equal_attrs(a,c)):raise ValueError('native metadata differs')
        for key in a.dimensions:
            if len(a.dimensions[key])!=len(b.dimensions[key]) or len(a.dimensions[key])!=len(c.dimensions[key]) or a.dimensions[key].isunlimited()!=c.dimensions[key].isunlimited():raise ValueError(f'native dimension differs: {key}')
        for name in a.variables:
            x,y,z=a[name],b[name],c[name]
            if x.dimensions!=z.dimensions or x.dtype!=z.dtype or x.shape!=z.shape or not common.equal_attrs(x,z):raise ValueError(f'native field metadata differs: {name}')
            expected=y if name==field else x
            if expected.shape!=z.shape or expected.dtype!=z.dtype or not np.array_equal(expected[:],z[:],equal_nan=expected.dtype.kind in 'fc'):raise ValueError(f'unexpected native field difference: {name}')


def check_inputs(preparation,cases,common,old,ev):
    rec=ev.identity(preparation)
    if rec['sha256']!=PREP_SHA:raise ValueError('preparation receipt hash mismatch')
    prep=json.loads(preparation.read_text());records=[rec]
    if (prep.get('schema')!='initial_qrain_qsnow_single_species_v1' or prep.get('parent_unchanged') is not True
        or prep.get('parent_before')!=prep.get('parent_after')):raise ValueError('invalid preparation')
    _,base_hash,donor_hash=common.PARENTS['H_ORIGINAL_QRQS']
    for name,directory in cases.items():
        field,expected=CASES[name];e=prep['cases'][name];staged=e['all_staged_input_hashes']
        if (e['base_sha256']!=base_hash or e['donor_sha256']!=donor_hash or e['changed_variables']!=[field]
            or e['other_variable_values_and_all_metadata_unchanged'] is not True or e['prior_case_hashes_before_after_equal'] is not True
            or staged.get('wrfinput_d01')!=expected or staged.get('wrf.exe')!=old.FIX_EXE_SHA):raise ValueError(f'{name}: incorrect input identity')
        inputs=directory/'inputs.json';records.append(ev.identity(inputs))
        if json.loads(inputs.read_text())!=e:raise ValueError(f'{name}: input receipt mismatch')
        base,donor=Path(e['base']),Path(e['donor'])
        for path,sha in ((base,base_hash),(donor,donor_hash)):
            item=ev.identity(path)
            if item['sha256']!=sha:raise ValueError('parent input hash mismatch')
            records.append(item)
        prior_staged,prior_records=old.checked_run('FIX_H',Path(e['prior_case']),ev);records.extend(prior_records)
        if {k:v for k,v in staged.items() if k!='wrfinput_d01'}!={k:v for k,v in prior_staged.items() if k!='wrfinput_d01'}:raise ValueError('non-intervention inputs differ')
        for file,digest in staged.items():
            if Path(file).name!=file:raise ValueError('invalid staged filename')
            item=ev.identity(directory/file)
            if item['sha256']!=digest:raise ValueError(f'{name}: staged hash mismatch: {file}')
            records.append(item)
        verify_single_field(base,donor,directory/'wrfinput_d01',field,common)
        path=directory/'receipt.json';records.append(ev.identity(path));r=json.loads(path.read_text())
        if (r.get('exit')!=0 or any(r.get(k) is not True for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged'))
            or r.get('histories')!=old.HISTORIES or sorted(p.name for p in directory.glob('wrfout*'))!=old.HISTORIES
            or set(r.get('output_sha256',{}))!=set(old.HISTORIES)):raise ValueError('incomplete runtime')
        for file in old.HISTORIES:
            item=ev.identity(directory/file)
            if item['sha256']!=r['output_sha256'][file]:raise ValueError('history hash mismatch')
            records.append(item)
    return records


def run(cases,preparation,reference_dir,analysis,odam_dir,output):
    if set(cases)!=set(CASES):raise ValueError('both single-species cases required')
    if output.exists() or output.is_symlink():raise ValueError('output exists')
    common=load_common();old=common.load_base();scorer=old.load_scorer();ev=scorer.evaluator
    records=[ev.identity(COMMON),ev.identity(common.BASE_SCRIPT)];records.extend(check_inputs(preparation,cases,common,old,ev))
    for f,digest in [('hour_13_arrays.npz',PAIRED_SHA),('receipt.json',RECEIPT_SHA)]:
        item=ev.identity(PRIOR/f)
        if item['sha256']!=digest:raise ValueError('prior factorial control changed')
        records.append(item)
    with np.load(PRIOR/'hour_13_arrays.npz',allow_pickle=False) as z:
        values={k:np.array(z[k]) for k in ('reference','latitude','longitude','flat_index_yx','FIX_H','H_ORIGINAL_QRQS')}
    ref_records=scorer.reference_records(reference_dir,analysis);records.extend(ref_records.values())
    inventory,mask,lat,lon,_=ev.load_reference(reference_dir,analysis)
    rn1=odam_dir/'DFS_VSRT_GRD_KLPS_ODAM_RN1.202608161300';item=ev.identity(rn1)
    if item['sha256']!=old.RN1_SHA:raise ValueError('RN1 hash mismatch')
    records.append(item);reference,valid=ev.read_rn1(rn1,13)
    if (int(mask.sum())!=3688 or not np.array_equal(np.flatnonzero(mask),values['flat_index_yx'])
        or not np.array_equal(lat[mask],values['latitude']) or not np.array_equal(lon[mask],values['longitude'])
        or not np.array_equal(reference[mask],values['reference'])):raise ValueError('reference mismatch')
    snaps={};source_lat=source_lon=None
    for name,directory in cases.items():
        snaps[name]={}
        for hour,file in zip((12,13),old.HISTORIES):
            item,identity=scorer.checked_snapshot(directory/file,datetime(2026,8,16,hour,tzinfo=timezone.utc),inventory)
            if identity['sha256']!=next(r['sha256'] for r in records if r['path']==str(directory/file)):raise ValueError('history changed')
            if source_lat is None:source_lat,source_lon=item['lat'],item['lon']
            elif not np.array_equal(source_lat,item['lat']) or not np.array_equal(source_lon,item['lon']):raise ValueError('grid mismatch')
            snaps[name][hour]=item
    prep=json.loads(preparation.read_text())
    prior_dir=Path(prep['cases']['H_ORIGINAL_QR']['prior_case'])
    for hour,file in zip((12,13),old.HISTORIES):
        snapshot,identity=scorer.checked_snapshot(prior_dir/file,datetime(2026,8,16,hour,tzinfo=timezone.utc),inventory)
        if identity['sha256']!=next(r['sha256'] for r in records if r['path']==str(prior_dir/file)) or not np.array_equal(source_lat,snapshot['lat']) or not np.array_equal(source_lon,snapshot['lon']):raise ValueError('baseline history or grid mismatch')
    ev.CASES=tuple(cases);ev.COMPARE_HOURS=(13,);reset=ev.check_resets(snaps)
    x0,x1=inventory['grid']['crop_x_inclusive'];y0,y1=inventory['grid']['crop_y_inclusive'];ys,xs=slice(y0-2,y1),slice(x0-2,x1)
    mapping=ev.build_curvilinear_mapping(source_lat[ys,xs],source_lon[ys,xs],lat,lon,mask)
    common_mask=mask & mapping['valid'] & valid;accumulated={}
    for name,hours in snaps.items():
        accumulated[name]={}
        for hour,snapshot in hours.items():
            total,v=ev.raw_total(snapshot);accumulated[name][hour]=ev.remap_field(total[ys,xs],v[ys,xs],mapping);common_mask &= accumulated[name][hour][1]
    if not np.array_equal(common_mask,mask):raise ValueError('incomplete valid mask')
    for name in cases:
        delta=accumulated[name][13][0]-accumulated[name][12][0]
        if np.any(delta[mask]<-ev.NEGATIVE_TOLERANCE_MM):raise ValueError('negative precipitation')
        values[name]=np.maximum(delta[mask],0)
    categorical=[];continuous=[];transitions=[];metrics={}
    for name in NAMES:
        errors=values[name]-values['reference']
        row={'case':name,'points':len(errors),'mean_forecast_mm':float(np.mean(values[name])),
             'mean_reference_mm':float(np.mean(values['reference'])),'mean_error_mm':float(np.mean(errors)),
             'MAE_mm':float(np.mean(np.abs(errors))),'RMSE_mm':float(np.sqrt(np.mean(errors**2)))}
        continuous.append(row)
        for t in scorer.THRESHOLDS:
            score=scorer.scores(values[name],values['reference'],t);categorical.append({'case':name,'threshold_mm':t,'points':len(errors),**score});metrics[name,t]=score
    for name in NAMES[1:]:
        transitions.extend({'baseline':'FIX_H','candidate':name,'threshold_mm':t,**scorer.transitions(values['FIX_H'],values[name],values['reference'],t)} for t in scorer.THRESHOLDS)
    interaction=[]
    for t in scorer.THRESHOLDS:
        for metric in ('CSI','ETS','POD','FAR','frequency_bias','hit','miss','false_alarm','correct_dry'):
            v=[metrics[name,t][metric] for name in NAMES]
            interaction.append({'threshold_mm':t,'metric':metric,'baseline':v[0],'rain':v[1],'snow':v[2],'both':v[3],
                                'interaction': None if any(x is None for x in v) else v[3]-v[1]-v[2]+v[0]})
    for metric in ('mean_forecast_mm','mean_error_mm','MAE_mm','RMSE_mm'):
        v=[row[metric] for row in continuous]
        interaction.append({'threshold_mm':'','metric':metric,'baseline':v[0],'rain':v[1],'snow':v[2],'both':v[3],
                            'interaction':v[3]-v[1]-v[2]+v[0]})
    scorer.verify_records(records)
    output.mkdir(parents=True,exist_ok=False)
    try:
        np.savez_compressed(output/'hour_13_arrays.npz',**values)
        for file,rows in [('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('transitions.csv',transitions),('interaction.csv',interaction)]:scorer.write_csv(output/file,rows)
        receipt={'status':'COMPLETE','points':3688,'reset_checks':reset,'mapping_residual_max_deg':mapping['residual_max_deg'],'sources':records,
                 'interaction_definition':'both - rain - snow + baseline; outcome interaction, not physical attribution',
                 'limitation':'Unbalanced input intervention, single hour and case; RN1 may use previous-hour fallback and has no coverage bitmap.'}
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    except BaseException:
        shutil.rmtree(output);raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',action='append',required=True)
    p.add_argument('--preparation',type=Path,required=True);p.add_argument('--reference-dir',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--odam-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();cases={}
    for entry in args.case:
        name,sep,path=entry.partition('=')
        if not sep or name not in CASES or name in cases or not path:p.error(f'invalid case: {entry}')
        cases[name]=Path(path)
    run(cases,args.preparation,args.reference_dir,args.analysis,args.odam_dir,args.output)


if __name__=='__main__':main()
