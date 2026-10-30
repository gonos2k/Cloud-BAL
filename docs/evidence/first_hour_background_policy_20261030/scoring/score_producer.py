#!/usr/bin/env python3
"""Score the sealed producer candidate against pinned one-hour control arrays."""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
DIR=Path(__file__).resolve().parent
COMMON=DIR/'score_components.py'; COMMON_SHA='48976426853745b703d497916355ec053b3ee14590d6cbf0bec071a4c9f8b26c'
GATE=DIR/'producer_gate.py'; GATE_SHA='aa96a45eea76baf4f4d26238c170db7e250aaf42d8db5772a050e1b7aba460d6'
OLD=ROOT/'docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py'
OLD_SHA='992f38bf7209eb94ee196e76e7383343a8d61872832dc605c7ea18e4bc38333c'
PRIOR=OLD.parent/'results'; PRIOR_SHA='c2f7f449f265b545e88a20bcb024e7944058d34b8f31061a6281cde364281d87'
PRIOR_RECEIPT_SHA='e44db2c2a76fa1b7be3132fd6340e1467c8dc9c1c7982772af51c327c48f0814'
EXPERIMENT=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment')
FORECAST=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG')
CANDIDATE_INPUT='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'


def module(path,sha,name):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError(f'scoring helper changed: {path}')
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m



def check_candidate(old,ev):
    inputs_path=FORECAST/'inputs.json';receipt_path=FORECAST/'receipt.json'
    records=[ev.identity(inputs_path),ev.identity(receipt_path)]
    inputs=json.loads(inputs_path.read_text());receipt=json.loads(receipt_path.read_text())
    if (inputs.get('input_count')!=89 or inputs.get('reference_case')!=str(EXPERIMENT/'run_FIX_H')
        or inputs.get('source_before')!=inputs.get('source_after') or inputs.get('candidate_native_input')!=str(gate_candidate_input())):
        raise ValueError('candidate input preparation mismatch')
    staged=inputs['staged'];source=inputs['source_before']
    if len(staged)!=89 or staged.get('wrfinput_d01')!=CANDIDATE_INPUT:
        raise ValueError('candidate staged input identity mismatch')
    for folder,manifest in ((FORECAST,staged),(EXPERIMENT/'run_FIX_H',source)):
        for name,expected in manifest.items():
            if Path(name).name!=name:raise ValueError('unsafe staged input path')
            item=ev.identity(folder/name)
            if item['sha256']!=expected:raise ValueError('staged or source input changed')
            records.append(item)
    for path,expected in inputs['evidence_before'].items():
        item=ev.identity(Path(path))
        if item['sha256']!=expected:raise ValueError('forecast evidence changed')
        records.append(item)
    if (receipt.get('exit')!=0 or any(receipt.get(k) is not True for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged','evidence_unchanged'))
        or receipt.get('policy')!='HYDRO_BACKGROUND_PRECIP' or receipt.get('evidence_before')!=inputs.get('evidence_before')
        or receipt.get('histories')!=old.HISTORIES or sorted(p.name for p in FORECAST.glob('wrfout*'))!=old.HISTORIES
        or set(receipt.get('output_sha256',{}))!=set(old.HISTORIES)):
        raise ValueError('candidate runtime incomplete')
    for name in old.HISTORIES:
        item=ev.identity(FORECAST/name)
        if item['sha256']!=receipt['output_sha256'][name]:raise ValueError('candidate history hash mismatch')
        records.append(item)
    return staged,records


def gate_candidate_input():
    return FORECAST.parent.parent/'native_HYDRO_BACKGROUND_PRECIP/real/wrfinput_d01'


def run(reference_dir,analysis,odam_dir,output):
    if output.exists() or output.is_symlink():raise ValueError('output exists')
    gate=module(GATE,GATE_SHA,'producer_gate');components=module(COMMON,COMMON_SHA,'producer_components');old=module(OLD,OLD_SHA,'first_hour_scorer')
    scorer=old.load_scorer();ev=scorer.evaluator
    provenance=gate.validate();records=[ev.identity(GATE),ev.identity(COMMON),ev.identity(OLD)]
    for path,digest in ((PRIOR/'hour_13_arrays.npz',PRIOR_SHA),(PRIOR/'receipt.json',PRIOR_RECEIPT_SHA),(old.OLD/'scores/hour_13_arrays.npz',old.REFERENCE_SHA)):
        item=ev.identity(path)
        if item['sha256']!=digest:raise ValueError('pinned prior scoring input changed')
        records.append(item)
    base_staged,base_records=old.checked_run('FIX_H',EXPERIMENT/'run_FIX_H',ev);records.extend(base_records)
    _,original_records=old.checked_run('FIX_ORIGINAL',EXPERIMENT/'run_FIX_ORIGINAL',ev);records.extend(original_records)
    candidate_staged,candidate_records=check_candidate(old,ev);records.extend(candidate_records)
    if (candidate_staged.get('wrf.exe')!=old.FIX_EXE_SHA or base_staged.get('wrf.exe')!=old.FIX_EXE_SHA
        or {k:v for k,v in base_staged.items() if k!='wrfinput_d01'}!={k:v for k,v in candidate_staged.items() if k!='wrfinput_d01'}):
        raise ValueError('forecast non-initial inputs or executable differ')
    with np.load(PRIOR/'hour_13_arrays.npz',allow_pickle=False) as z:
        prior={k:np.array(z[k]) for k in ('reference','latitude','longitude','flat_index_yx','FIX_H','FIX_ORIGINAL')}
    with np.load(old.OLD/'scores/hour_13_arrays.npz',allow_pickle=False) as z:
        archived={k:np.array(z[k]) for k in ('ORIGINAL','reference','latitude','longitude','flat_index_yx')}
    for k in ('reference','latitude','longitude','flat_index_yx'):
        if not np.array_equal(prior[k],archived[k]):raise ValueError('prior reference arrays differ')
    ref_records=scorer.reference_records(reference_dir,analysis);records.extend(ref_records.values())
    inventory,mask,lat,lon,_=ev.load_reference(reference_dir,analysis)
    rn1=odam_dir/'DFS_VSRT_GRD_KLPS_ODAM_RN1.202608161300';item=ev.identity(rn1)
    if item['sha256']!=old.RN1_SHA:raise ValueError('RN1 hash mismatch')
    records.append(item);reference,valid=ev.read_rn1(rn1,13)
    if (int(mask.sum())!=3688 or not valid[mask].all() or not np.array_equal(np.flatnonzero(mask),prior['flat_index_yx'])
        or not np.array_equal(lat[mask],prior['latitude']) or not np.array_equal(lon[mask],prior['longitude'])
        or not np.array_equal(reference[mask],prior['reference'])):raise ValueError('reference differs from fixed NPZ')
    base=components.remap_one_hour(EXPERIMENT/'run_FIX_H',inventory,mask,lat,lon,scorer)
    candidate=components.remap_one_hour(FORECAST,inventory,mask,lat,lon,scorer)
    for result in (base,candidate):
        for identity in result['history_identities']:
            if identity['sha256']!=next(r['sha256'] for r in records if r['path']==identity['path']):raise ValueError('history changed')
    if not np.array_equal(base['values'],prior['FIX_H']):raise ValueError('recomputed H baseline differs from prior')
    if not np.array_equal(base['latitude'],candidate['latitude']) or not np.array_equal(base['longitude'],candidate['longitude']):raise ValueError('forecast grids differ')
    values={'PRODUCER_H':base['values'],'PRODUCER_BG':candidate['values'],'FIX_H':prior['FIX_H'],
            'ORIGINAL':archived['ORIGINAL'],'FIX_ORIGINAL':prior['FIX_ORIGINAL'],'reference':prior['reference']}
    categorical,continuous,transitions=components.score_arrays(values,scorer)
    scorer.verify_records(records)
    for path,sha in provenance.items():
        if gate.digest(Path(path))!=sha:raise ValueError('producer provenance changed during scoring')
    output.mkdir(parents=True,exist_ok=False)
    try:
        np.savez_compressed(output/'hour_13_arrays.npz',**values,latitude=lat[mask],longitude=lon[mask],flat_index_yx=np.flatnonzero(mask))
        for file,rows in [('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('transitions.csv',transitions)]:scorer.write_csv(output/file,rows)
        receipt={'status':'COMPLETE','points':3688,'baseline_reuse':'PRODUCER_H is existing FIX_H forecast; rebuilt HYDRO native input is bitwise identical and executable/other inputs match.',
                 'producer_source_provenance':provenance,'scoring_sources':records,'baseline_reset':base['reset'],'candidate_reset':candidate['reset'],
                 'limitations':'Scoped producer policy/shadow and untraced compiler build, not operational approval or closed water/energy budget; one hour and RN1 may use previous-hour fallback.'}
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    except BaseException:
        shutil.rmtree(output);raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference-dir',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--odam-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.reference_dir,a.analysis,a.odam_dir,a.output)


if __name__=='__main__':main()
