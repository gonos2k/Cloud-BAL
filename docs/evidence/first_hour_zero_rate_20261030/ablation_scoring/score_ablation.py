#!/usr/bin/env python3
"""Score source-bound reciprocal QR/QS interventions against fixed-executable parents."""
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
BASE_SCRIPT = ROOT / 'docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py'
PRIOR = ROOT / 'docs/evidence/first_hour_zero_rate_20261030/scoring/results'
BASE_SCRIPT_SHA = '992f38bf7209eb94ee196e76e7383343a8d61872832dc605c7ea18e4bc38333c'
PRIOR_ARRAYS_SHA = 'c2f7f449f265b545e88a20bcb024e7944058d34b8f31061a6281cde364281d87'
PRIOR_RECEIPT_SHA = 'e44db2c2a76fa1b7be3132fd6340e1467c8dc9c1c7982772af51c327c48f0814'
PREPARATION_SHA = '79158423cf6ac37981a7ff78bfb4fa1a49e1d09dc765f9cc7c4e67a94d35f8af'
CANDIDATES = {'H_ORIGINAL_QRQS': '8ebf4f06f9a200efe6c0525575504d10857b5605a43d78c2c6d54a129844bf97',
              'ORIGINAL_H_QRQS': '490c213b1b99d135974db97f14969fab55c37e3b32d6b13b1aa998cf0a49331d'}
PARENTS = {'H_ORIGINAL_QRQS': ('FIX_H', '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126', '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'),
           'ORIGINAL_H_QRQS': ('FIX_ORIGINAL', '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc', '7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126')}


def load_base():
    if hashlib.sha256(BASE_SCRIPT.read_bytes()).hexdigest() != BASE_SCRIPT_SHA:
        raise ValueError('prior scoring code changed')
    spec = importlib.util.spec_from_file_location('first_hour_scorer', BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def equal_attrs(a, b):
    return set(a.ncattrs()) == set(b.ncattrs()) and all(np.array_equal(a.getncattr(k), b.getncattr(k)) for k in a.ncattrs())


def verify_native_intervention(base, donor, candidate):
    """Check every native variable and attribute, with only QR/QS drawn from donor."""
    with Dataset(base) as a, Dataset(donor) as b, Dataset(candidate) as c:
        for d in (a, b, c): d.set_auto_mask(False)
        if (set(a.variables) != set(b.variables) or set(a.variables) != set(c.variables)
            or set(a.dimensions) != set(b.dimensions) or set(a.dimensions) != set(c.dimensions)
            or not equal_attrs(a, c)):
            raise ValueError('native dimensions, variables or global attributes differ')
        for key in a.dimensions:
            if (len(a.dimensions[key]) != len(b.dimensions[key]) or len(a.dimensions[key]) != len(c.dimensions[key])
                or a.dimensions[key].isunlimited() != c.dimensions[key].isunlimited()):
                raise ValueError(f'native dimension differs: {key}')
        for name in a.variables:
            x, y, z = a[name], b[name], c[name]
            if (x.dimensions != z.dimensions or x.dtype != z.dtype or x.shape != z.shape or not equal_attrs(x, z)):
                raise ValueError(f'native variable metadata differs: {name}')
            expected = y if name in ('QRAIN', 'QSNOW') else x
            if expected.shape != z.shape or expected.dtype != z.dtype or not np.array_equal(expected[:], z[:], equal_nan=expected.dtype.kind in 'fc'):
                raise ValueError(f'unexpected native field difference: {name}')


def check_preparation(path, cases, old, ev):
    record = ev.identity(path)
    if record['sha256'] != PREPARATION_SHA: raise ValueError('preparation receipt mismatch')
    prep = json.loads(path.read_text())
    if (prep.get('schema') != 'initial_qrain_qsnow_reciprocal_v1' or prep.get('parent_unchanged') is not True
        or prep.get('parent_before') != prep.get('parent_after')): raise ValueError('invalid preparation receipt')
    records = [record]
    for name, directory in cases.items():
        entry = prep['cases'][name]; prior_name, base_hash, donor_hash = PARENTS[name]
        if (entry['base_sha256'] != base_hash or entry['donor_sha256'] != donor_hash
            or entry['changed_variables'] != ['QRAIN','QSNOW']
            or entry['other_variable_values_and_all_metadata_unchanged'] is not True
            or entry['prior_case_hashes_before_after_equal'] is not True
            or entry['all_staged_input_hashes'].get('wrfinput_d01') != CANDIDATES[name]
            or entry['all_staged_input_hashes'].get('wrf.exe') != old.FIX_EXE_SHA):
            raise ValueError(f'{name}: invalid preparation identity')
        inputs = directory / 'inputs.json'; inputs_record = ev.identity(inputs)
        if json.loads(inputs.read_text()) != entry: raise ValueError(f'{name}: input receipt mismatch')
        records.append(inputs_record)
        base, donor = Path(entry['base']), Path(entry['donor'])
        for path, expected in ((base, base_hash), (donor, donor_hash)):
            item = ev.identity(path)
            if item['sha256'] != expected: raise ValueError(f'{name}: parent hash mismatch')
            records.append(item)
        prior_dir = Path(entry['prior_case'])
        prior_staged, prior_records = old.checked_run(prior_name, prior_dir, ev)
        records.extend(prior_records)
        if {k:v for k,v in entry['all_staged_input_hashes'].items() if k != 'wrfinput_d01'} != {k:v for k,v in prior_staged.items() if k != 'wrfinput_d01'}:
            raise ValueError(f'{name}: non-intervention staged inputs differ')
        for file, digest in entry['all_staged_input_hashes'].items():
            if Path(file).name != file: raise ValueError('invalid staged filename')
            item = ev.identity(directory / file)
            if item['sha256'] != digest: raise ValueError(f'{name}: staged input mismatch: {file}')
            records.append(item)
        verify_native_intervention(base, donor, directory/'wrfinput_d01')
        receipt_path = directory / 'receipt.json'; receipt_record = ev.identity(receipt_path)
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('exit') != 0 or any(receipt.get(k) is not True for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged'))
            or receipt.get('histories') != old.HISTORIES or sorted(p.name for p in directory.glob('wrfout*')) != old.HISTORIES
            or set(receipt.get('output_sha256', {})) != set(old.HISTORIES)):
            raise ValueError(f'{name}: incomplete runtime')
        records.append(receipt_record)
        for file in old.HISTORIES:
            item = ev.identity(directory/file)
            if item['sha256'] != receipt['output_sha256'][file]: raise ValueError(f'{name}: history mismatch')
            records.append(item)
    return records


def run(cases, preparation, reference_dir, analysis, odam_dir, output):
    if set(cases) != set(CANDIDATES): raise ValueError('both interventions required')
    if output.exists() or output.is_symlink(): raise ValueError('output exists')
    old = load_base(); scorer = old.load_scorer(); ev = scorer.evaluator
    records = [ev.identity(BASE_SCRIPT)]
    records.extend(check_preparation(preparation, cases, old, ev))
    for file, expected in [('hour_13_arrays.npz', PRIOR_ARRAYS_SHA), ('receipt.json', PRIOR_RECEIPT_SHA)]:
        record = ev.identity(PRIOR/file)
        if record['sha256'] != expected: raise ValueError(f'prior scoring {file} changed')
        records.append(record)
    with np.load(PRIOR/'hour_13_arrays.npz',allow_pickle=False) as z:
        values = {k: np.array(z[k]) for k in ('reference','latitude','longitude','flat_index_yx','FIX_H','FIX_ORIGINAL')}
    ref_records = scorer.reference_records(reference_dir, analysis); records.extend(ref_records.values())
    inventory, mask, lat, lon, _ = ev.load_reference(reference_dir, analysis)
    rn1 = odam_dir/'DFS_VSRT_GRD_KLPS_ODAM_RN1.202608161300'; item = ev.identity(rn1)
    if item['sha256'] != old.RN1_SHA: raise ValueError('RN1 hash mismatch')
    records.append(item); reference, ref_valid = ev.read_rn1(rn1,13)
    if (int(mask.sum()) != 3688 or not np.array_equal(np.flatnonzero(mask),values['flat_index_yx'])
        or not np.array_equal(lat[mask],values['latitude']) or not np.array_equal(lon[mask],values['longitude'])
        or not np.array_equal(reference[mask],values['reference'])): raise ValueError('reference differs from prior arrays')
    snapshots = {}; source_lat = source_lon = None
    prep = json.loads(preparation.read_text())
    all_runs = dict(cases)
    for name, (prior, _, _) in PARENTS.items():
        all_runs[prior] = Path(prep['cases'][name]['prior_case'])
    for name,directory in all_runs.items():
        snapshots[name] = {}
        for hour,file in zip((12,13), old.HISTORIES):
            snap, rec = scorer.checked_snapshot(directory/file,datetime(2026,8,16,hour,tzinfo=timezone.utc),inventory)
            if rec['sha256'] != next(r['sha256'] for r in records if r['path']==str(directory/file)): raise ValueError('history changed')
            if source_lat is None: source_lat,source_lon = snap['lat'],snap['lon']
            elif not np.array_equal(source_lat,snap['lat']) or not np.array_equal(source_lon,snap['lon']):raise ValueError('grid mismatch')
            snapshots[name][hour]=snap
    ev.CASES=tuple(all_runs);ev.COMPARE_HOURS=(13,);reset=ev.check_resets(snapshots)
    x0,x1=inventory['grid']['crop_x_inclusive'];y0,y1=inventory['grid']['crop_y_inclusive'];ys,xs=slice(y0-2,y1),slice(x0-2,x1)
    mapping=ev.build_curvilinear_mapping(source_lat[ys,xs],source_lon[ys,xs],lat,lon,mask)
    common=mask & mapping['valid'] & ref_valid; accumulated={}
    for name,hours in snapshots.items():
        accumulated[name]={}
        for hour,snap in hours.items():
            total,valid=ev.raw_total(snap); accumulated[name][hour]=ev.remap_field(total[ys,xs],valid[ys,xs],mapping);common &= accumulated[name][hour][1]
    if not np.array_equal(common,mask):raise ValueError('incomplete common validity')
    for name in all_runs:
        diff=accumulated[name][13][0]-accumulated[name][12][0]
        if np.any(diff[common] < -ev.NEGATIVE_TOLERANCE_MM):raise ValueError('negative hourly precipitation')
        remapped=np.maximum(diff[common],0)
        if name in ('FIX_H','FIX_ORIGINAL'):
            if not np.array_equal(remapped,values[name]):raise ValueError(f'{name}: baseline differs from pinned paired arrays')
        else:
            values[name]=remapped
    categorical=[];continuous=[];transitions=[]
    for name in ('FIX_H','H_ORIGINAL_QRQS','FIX_ORIGINAL','ORIGINAL_H_QRQS'):
        errors=values[name]-values['reference']
        continuous.append({'case':name,'points':len(errors),'mean_forecast_mm':float(np.mean(values[name])),
            'mean_reference_mm':float(np.mean(values['reference'])),'mean_error_mm':float(np.mean(errors)),
            'MAE_mm':float(np.mean(np.abs(errors))),'RMSE_mm':float(np.sqrt(np.mean(errors**2)))})
        categorical.extend({'case':name,'threshold_mm':t,'points':len(errors),**scorer.scores(values[name],values['reference'],t)} for t in scorer.THRESHOLDS)
    for name,(baseline,_,_) in PARENTS.items():
        transitions.extend({'baseline':baseline,'candidate':name,'threshold_mm':t,**scorer.transitions(values[baseline],values[name],values['reference'],t)} for t in scorer.THRESHOLDS)
    scorer.verify_records(records)
    output.mkdir(parents=True,exist_ok=False)
    try:
        np.savez_compressed(output/'hour_13_arrays.npz',**values)
        scorer.write_csv(output/'categorical_scores.csv',categorical);scorer.write_csv(output/'continuous_scores.csv',continuous);scorer.write_csv(output/'transitions.csv',transitions)
        receipt={'status':'COMPLETE','points':3688,'reset_checks':reset,'mapping_residual_max_deg':mapping['residual_max_deg'],
                 'baseline_binding':'FIX_H and FIX_ORIGINAL arrays from pinned prior score NPZ', 'sources':records,
                 'limitation':'Prescribed QR/QS perturbation is not water-balanced or a production initialization; RN1 lacks a coverage bitmap and may use prior-hour fallback.'}
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    except BaseException:
        shutil.rmtree(output);raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',action='append',required=True,metavar='NAME=RUN_DIRECTORY')
    p.add_argument('--preparation',type=Path,required=True);p.add_argument('--reference-dir',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--odam-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();cases={}
    for entry in args.case:
        name,sep,path=entry.partition('=')
        if not sep or name not in CANDIDATES or name in cases or not path:p.error(f'invalid case {entry}')
        cases[name]=Path(path)
    run(cases,args.preparation,args.reference_dir,args.analysis,args.odam_dir,args.output)


if __name__=='__main__':main()
