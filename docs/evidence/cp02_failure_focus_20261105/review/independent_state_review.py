#!/usr/bin/env python3
"""Independently validate extracted B1 failure-focus history snapshots."""
from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_focus_20261105'
STATE = EVIDENCE / 'state/extracted'
PLAN_PATH = EVIDENCE / 'state/extraction_plan.json'
RECEIPT_PATH = STATE / 'receipt.json'
RD, RV, CP = 287.0, 461.6, 1004.5
QMIN = 1e-15
CASES = ('ORIGINAL', 'A', 'C', 'B1_OLD_KDM6')
HOURS = tuple(range(12, 19))
MASS_FIELDS = ('QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP',
               'QNRAIN', 'T', 'THM', 'P', 'PB')
SURFACE_FIELDS = ('RAINC', 'RAINNC', 'RAINSH', 'MU', 'MUB', 'HGT', 'MAPFAC_MX', 'MAPFAC_MY')
HYBRID_FIELDS = {'C1H': 39, 'C2H': 39, 'DNW': 39,
                 'C3F': 40, 'C4F': 40, 'ZNW': 40}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: np.array(archive[key], copy=True) for key in archive.files}


def saturation_rh(qv: np.ndarray, temperature: np.ndarray, pressure: np.ndarray,
                  phase: bool = False) -> np.ndarray:
    tr = 273.16 / temperature
    liquid_a = -(4 * RV - 4190.0) / RV
    liquid_b = liquid_a + 2.5e6 / (RV * 273.16)
    if phase:
        ice_a = -(4 * RV - 2106.0) / RV
        ice_b = ice_a + 2.85e6 / (RV * 273.16)
        a = np.where(temperature < 273.16, ice_a, liquid_a)
        b = np.where(temperature < 273.16, ice_b, liquid_b)
    else:
        a, b = liquid_a, liquid_b
    es = np.minimum(610.78 * np.exp(np.log(tr) * a) * np.exp(b * (1 - tr)),
                    0.99 * pressure)
    qs = np.maximum((RD / RV) * es / (pressure - es), QMIN)
    return np.maximum(qv / qs, QMIN)


def independent_indices(mapping: dict[str, np.ndarray], flat_ids: np.ndarray):
    y, x = np.divmod(flat_ids.astype(np.int64), 149)
    j = mapping['j0'][y, x] + 5
    i = mapping['i0'][y, x] + 74
    u, v = mapping['u'][y, x], mapping['v'][y, x]
    jj = np.stack((j, j, j + 1, j + 1), axis=-1)
    ii = np.stack((i, i + 1, i, i + 1), axis=-1)
    weights = np.stack(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v), axis=-1)
    return jj, ii, weights


def expected_corner(ds, name: str, jj: np.ndarray, ii: np.ndarray,
                    levels: int, staggered: bool = False) -> np.ndarray:
    var = ds.variables[name]
    var.set_auto_maskandscale(False)
    data = np.asarray(var[0])
    require(data.dtype == np.dtype('float32'), f'{name}: source dtype not float32')
    if data.ndim == 3:
        require(data.shape == (levels, 282, 234), f'{name}: source shape')
        return data[:, jj, ii].transpose(1, 0, 2)
    require(data.shape == (282, 234), f'{name}: source surface shape')
    return data[jj, ii]


def check_output_array(data: dict[str, np.ndarray], case: str, hour: int,
                       source_path: Path, jj: np.ndarray, ii: np.ndarray,
                       weights: np.ndarray, expected_lat: np.ndarray,
                       expected_lon: np.ndarray) -> dict:
    prefix = f'{case}/h{hour:02d}'
    ids = data['flat_index_yx']
    require(ids.shape == (270,) and len(np.unique(ids)) == 270, f'{prefix}: point key inventory')
    require(np.array_equal(data['native_j_zero_based'], jj), f'{prefix}: native j indices')
    require(np.array_equal(data['native_i_zero_based'], ii), f'{prefix}: native i indices')
    np.testing.assert_array_equal(data['corner_weights'], weights)
    np.testing.assert_allclose(weights.sum(axis=-1), 1.0, rtol=0, atol=1e-12)
    require(np.all(weights >= 0), f'{prefix}: negative bilinear weight')
    np.testing.assert_allclose(data['latitude'], expected_lat, rtol=0, atol=1e-9)
    np.testing.assert_allclose(data['longitude'], expected_lon, rtol=0, atol=1e-9)

    checked_fields = 0
    with Dataset(source_path, 'r') as ds:
        raw_time = b''.join(np.asarray(ds.variables['Times'][0]).tolist()).decode('ascii')
        require(raw_time == f'2026-08-16_{hour:02d}:00:00', f'{prefix}: actual Times')
        for name in MASS_FIELDS:
            value = expected_corner(ds, name, jj, ii, 39)
            np.testing.assert_array_equal(data[f'corner_{name}'], value)
            np.testing.assert_allclose(data[f'weighted_raw_{name}'],
                np.sum(value.astype(np.float64) * weights[:, None, :], axis=-1), rtol=0, atol=1e-12)
            checked_fields += 1
        for name, levels in (('PH', 40), ('PHB', 40)):
            value = expected_corner(ds, name, jj, ii, levels, staggered=True)
            np.testing.assert_array_equal(data[f'corner_{name}'], value)
            np.testing.assert_allclose(data[f'weighted_raw_{name}'],
                np.sum(value.astype(np.float64) * weights[:, None, :], axis=-1), rtol=0, atol=1e-12)
            checked_fields += 1
        for name in SURFACE_FIELDS:
            value = expected_corner(ds, name, jj, ii, 1)
            np.testing.assert_array_equal(data[f'corner_{name}'], value)
            np.testing.assert_allclose(data[f'weighted_raw_{name}'],
                np.sum(value.astype(np.float64) * weights, axis=-1), rtol=0, atol=1e-12)
            checked_fields += 1
        for name, levels in HYBRID_FIELDS.items():
            variable = ds.variables[name]
            variable.set_auto_maskandscale(False)
            value = np.asarray(variable[0])
            expected_dim = 'bottom_top_stag' if levels == 40 else 'bottom_top'
            require(variable.dimensions == ('Time', expected_dim) and value.shape == (levels,),
                    f'{prefix}/{name}: native hybrid contract')
            require(value.dtype == np.dtype('float32') and np.isfinite(value).all(),
                    f'{prefix}/{name}: native coefficient dtype/value')
            np.testing.assert_array_equal(data[f'native_hybrid_{name}'], value)
            np.testing.assert_array_equal(data[f'weighted_raw_{name}'], value.astype(np.float64))
            checked_fields += 1
        for attr in ('DX', 'DY'):
            require(float(getattr(ds, attr)) == 5000.0, f'{prefix}: {attr}')
            np.testing.assert_equal(data[f'{attr}_m'], np.float32(getattr(ds, attr)))
        ptop = ds.variables['P_TOP']
        ptop.set_auto_maskandscale(False)
        require(ptop.dimensions == ('Time',) and ptop.shape == (1,), f'{prefix}: P_TOP dims')
        np.testing.assert_equal(data['P_TOP_Pa'], np.asarray(ptop[0], dtype=np.float32))
        lat = expected_corner(ds, 'XLAT', jj, ii, 1)
        lon = expected_corner(ds, 'XLONG', jj, ii, 1)
        np.testing.assert_allclose(np.sum(lat.astype(np.float64)*weights, axis=-1), expected_lat, rtol=0, atol=1e-9)
        np.testing.assert_allclose(np.sum(lon.astype(np.float64)*weights, axis=-1), expected_lon, rtol=0, atol=1e-9)
        checked_fields += 2
        if 'W' in ds.variables:
            value = expected_corner(ds, 'W', jj, ii, 40, staggered=True)
            np.testing.assert_array_equal(data['corner_w_staggered_m_s'], value)
            mass_w = (value[:, :-1, :].astype(np.float64)+value[:, 1:, :].astype(np.float64))/2
            np.testing.assert_array_equal(data['corner_w_mass_level_m_s'], mass_w)
            np.testing.assert_allclose(data['weighted_w_mass_level_m_s'],
                np.sum(mass_w*weights[:, None, :], axis=-1), rtol=0, atol=1e-12)
            checked_fields += 1
    return {'raw_native_fields_checked': checked_fields, 'actual_times_checked': 1}


def check_derived(data: dict[str, np.ndarray], weights: np.ndarray, prefix: str):
    tpert = data['corner_T'].astype(np.float64)
    thm = data['corner_THM'].astype(np.float64)
    qv = data['corner_QVAPOR'].astype(np.float64)
    pressure = data['corner_P'].astype(np.float64) + data['corner_PB'].astype(np.float64)
    temp = (tpert + 300.0) * (pressure / 100000.0) ** (RD / CP)
    np.testing.assert_allclose(data['corner_theta_dry_K'], tpert + 300.0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(data['corner_temperature_K'], temp, rtol=2e-15, atol=2e-12)
    np.testing.assert_allclose(data['corner_pressure_Pa'], pressure, rtol=0, atol=0)
    np.testing.assert_allclose(data['corner_rh_liquid'], saturation_rh(qv, temp, pressure), rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(data['corner_rh_ice_or_water'], saturation_rh(qv, temp, pressure, True), rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(data['weighted_theta_dry_K'], np.sum((tpert+300.)*weights[:,None,:],axis=-1), rtol=0, atol=1e-12)
    np.testing.assert_allclose(data['weighted_temperature_K'], np.sum(temp*weights[:,None,:],axis=-1), rtol=2e-15, atol=2e-12)
    np.testing.assert_allclose(data['weighted_pressure_Pa'], np.sum(pressure*weights[:,None,:],axis=-1), rtol=0, atol=1e-10)
    np.testing.assert_allclose(data['weighted_rh_liquid'], np.sum(data['corner_rh_liquid']*weights[:,None,:],axis=-1), rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(data['weighted_rh_ice_or_water'], np.sum(data['corner_rh_ice_or_water']*weights[:,None,:],axis=-1), rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(data['weighted_theta_m_K'], np.sum((thm+300.)*weights[:,None,:],axis=-1), rtol=0, atol=1e-12)
    qrain, qnrain = data['corner_QRAIN'].astype(np.float64), data['corner_QNRAIN'].astype(np.float64)
    valid = (qrain>0)&(qnrain>0)
    np.testing.assert_array_equal(data['corner_dm_valid'], valid)
    expected_dm = np.full(qrain.shape, np.nan, dtype=np.float64)
    expected_dm[valid] = 5000.0 / np.cbrt(4000.0*np.pi*qnrain[valid]/qrain[valid])
    np.testing.assert_allclose(data['corner_dm_mass_weighted_mm'], expected_dm, rtol=1e-14, atol=1e-14, equal_nan=True)
    required = weights[:,None,:] > 0
    allowed = np.all(valid | ~required, axis=-1)
    coverage = np.sum(np.where(valid,weights[:,None,:],0.0),axis=-1)
    expected_weighted = np.sum(np.where(valid,expected_dm,0.0)*weights[:,None,:],axis=-1)
    expected_weighted = np.where(allowed,expected_weighted,np.nan)
    np.testing.assert_array_equal(data['weighted_dm_valid'],allowed)
    np.testing.assert_allclose(data['valid_weight_dm_mass_weighted_mm'],coverage,rtol=0,atol=1e-12)
    np.testing.assert_allclose(data['weighted_dm_mass_weighted_mm'],expected_weighted,rtol=1e-14,atol=1e-14,equal_nan=True)
    height = ((data['corner_PH'].astype(np.float64)+data['corner_PHB'].astype(np.float64))[:,:-1,:] +
              (data['corner_PH'].astype(np.float64)+data['corner_PHB'].astype(np.float64))[:,1:,:])/(2*9.81)-data['corner_HGT'][:,None,:]
    np.testing.assert_allclose(data['corner_height_agl_m'],height,rtol=0,atol=1e-12)
    np.testing.assert_allclose(data['weighted_height_agl_m'],np.sum(height*weights[:,None,:],axis=-1),rtol=0,atol=1e-10)
    require(data['corner_T'].dtype==np.float32 and data['corner_THM'].dtype==np.float32,prefix+': raw T/THM dtype')
    require(data['corner_temperature_K'].dtype==np.float64 and data['corner_rh_liquid'].dtype==np.float64 and data['weighted_temperature_K'].dtype==np.float64,prefix+': diagnostic precision')
    return {'diagnostics_rederived': ['Tdry','T','RH_liquid','RH_ice_or_water','Dm','height_AGL'],
            'dm_valid_corner_levels': int(valid.sum()),
            'dm_invalid_corner_levels': int((~valid).sum()),
            'dm_undefined_weighted_levels': int((~allowed).sum())}


def main():
    plan=json.loads(PLAN_PATH.read_text());receipt=json.loads(RECEIPT_PATH.read_text())
    require(plan['status']=='FROZEN_BEFORE_STATE_EXTRACTION','plan status')
    require(receipt['status']=='PASS','extraction receipt status')
    require(receipt['plan_sha256']==sha256(PLAN_PATH),'plan hash in extraction receipt')
    require(plan['extractor']['sha256']==sha256(ROOT/'tools/cp02_b1_failure_state.py'),'extractor hash')
    require(plan['feature_implementation']['sha256']==sha256(ROOT/'tools/cp02_failure_state_features.py'),'feature source hash')
    require(receipt['inputs_proposal_sha256']==plan['inputs_proposal']['sha256'],'proposal pin')
    require(receipt['membership_sha256']==plan['membership']['sha256'],'membership pin')
    require(receipt['matched_controls_sha256']==plan['matched_controls']['sha256'],'controls pin')
    require(receipt['targets_receipt_sha256']==plan['targets_receipt']['sha256'],'targets receipt pin')
    require(receipt['cases']==list(CASES) and receipt['hours_utc']==list(HOURS),'case/hour inventory')
    require(receipt['points']==270 and receipt['levels']==39 and len(receipt['records'])==28,'output coverage')
    proposal=json.loads(Path(plan['inputs_proposal']['path']).read_text())
    membership=list(csv.DictReader(Path(plan['membership']['path']).open(newline='',encoding='utf-8')))
    ids=np.asarray([int(row['flat_index_yx']) for row in membership],dtype=np.int64)
    require(ids.shape==(270,) and len(np.unique(ids))==270,'focus ids')
    reference_record=proposal['paired_score_arrays']['ORIGINAL'][0]
    with np.load(reference_record['path'],allow_pickle=False) as archive:
        all_flat=np.asarray(archive['flat_index_yx'],dtype=np.int64)
        all_lat=np.asarray(archive['latitude'],dtype=np.float64)
        all_lon=np.asarray(archive['longitude'],dtype=np.float64)
        lookup={int(x):i for i,x in enumerate(all_flat)}
        indices=np.asarray([lookup[int(x)] for x in ids])
        expected_lat,expected_lon=all_lat[indices],all_lon[indices]
    with np.load(proposal['mapping']['path'],allow_pickle=False) as archive:
        mapping={key:np.asarray(archive[key]) for key in archive.files}
    jj,ii,weights=independent_indices(mapping,ids)
    receipt_by={(row['case'],row['hour_utc']):row for row in receipt['records']}
    require(set(receipt_by)=={(case,hour) for case in CASES for hour in HOURS},'record key inventory')
    output_hashes={};source_hashes={};surface_residuals=[];derived_counts=[];sample_raw_counts=[]
    previous={}
    for case in CASES:
        for hour in HOURS:
            r=receipt_by[(case,hour)];path=STATE/r['output']
            require(path.is_file() and not path.is_symlink(),'output file present')
            require(path.stat().st_size==r['output_size_bytes'] and sha256(path)==r['output_sha256'],f'{case}h{hour}: output hash')
            output_hashes[path.name]=r['output_sha256']
            source=Path(r['input_path']);require(source.is_file(),'input source present')
            source_pin=proposal['cases'][case][hour-12]
            require(str(source)==source_pin['path'] and r['input_path']==source_pin['path'],f'{case}h{hour}: source path pin')
            require(source.stat().st_size==source_pin['size_bytes'],'source size')
            require(r['input_sha256']==source_pin['sha256'],f'{case}h{hour}: receipt source hash pin')
            source_hashes[path.name]=r['input_sha256']
            data=read_npz(path)
            require(np.array_equal(data['flat_index_yx'],ids),f'{case}h{hour}: point keys')
            require(data['corner_weights'].shape==(270,4),'weights shape')
            require(data['corner_weights'].dtype==np.float64,'weights dtype')
            require(data['membership_cohort_labels'].shape==(270,) and data['membership_is_control'].shape==(270,),'membership labels')
            require(data['corner_QVAPOR'].dtype==np.float32 and data['corner_QRAIN'].dtype==np.float32 and data['corner_T'].dtype==np.float32 and data['corner_THM'].dtype==np.float32,'raw field float32')
            require(data['corner_temperature_K'].dtype==np.float64 and data['corner_rh_liquid'].dtype==np.float64 and data['weighted_temperature_K'].dtype==np.float64,'REAL64 diagnostics')
            for name,nz in ((n,39) for n in MASS_FIELDS):require(data[f'corner_{name}'].shape==(270,nz,4),f'{case}h{hour}/{name} shape')
            for name,nz in (('PH',40),('PHB',40)):require(data[f'corner_{name}'].shape==(270,nz,4),f'{case}h{hour}/{name} shape')
            for name in SURFACE_FIELDS:require(data[f'corner_{name}'].shape==(270,4),f'{case}h{hour}/{name} shape')
            for name,nz in HYBRID_FIELDS.items():require(data[f'native_hybrid_{name}'].shape==(nz,) and data[f'native_hybrid_{name}'].dtype==np.float32,f'{case}h{hour}/{name} shape')
            derived_counts.append(check_derived(data,weights,f'{case}h{hour}'))
            if (case,hour) in {('ORIGINAL',13),('A',14),('C',17),('B1_OLD_KDM6',14)}:
                rawcheck=check_output_array(data,case,hour,source,jj,ii,weights,expected_lat,expected_lon)
                source_hashes[path.name]=sha256(source)
                sample_raw_counts.append({'case':case,'hour':hour,**rawcheck})
            # Direct component increments must equal consecutive REAL32 source fields subtracted in REAL64.
            for field in ('RAINC','RAINNC','RAINSH'):
                cumulative=data[f'corner_{field.lower()}_cumulative_mm']
                inc=data[f'corner_{field.lower()}_increment_mm']
                weighted=data[f'weighted_{field.lower()}_increment_mm']
                if hour==12:
                    require(np.isnan(inc).all() and np.isnan(weighted).all(),f'{case} h12 {field} increment must be undefined')
                else:
                    old=previous[(case,hour-1)][f'corner_{field.lower()}_cumulative_mm'].astype(np.float64)
                    expected=cumulative.astype(np.float64)-old
                    np.testing.assert_array_equal(inc,expected)
                    require(np.all(inc>=-1e-6),f'{case}h{hour}/{field}: reset bound')
                    np.testing.assert_allclose(weighted,np.sum(inc*weights,axis=-1),rtol=0,atol=1e-12)
                if field=='RAINSH':
                    require(np.max(np.abs(cumulative))<=1e-10,f'{case}h{hour}: RAINSH cumulative')
                    if hour>12:require(np.max(np.abs(inc))<=1e-10,f'{case}h{hour}: RAINSH increment')
            if hour>12:
                score_rec=proposal['paired_score_arrays'][case][hour-13]
                with np.load(score_rec['path'],allow_pickle=False) as archive:
                    score_ids=np.asarray(archive['flat_index_yx'],dtype=np.int64)
                    score_lookup={int(v):i for i,v in enumerate(score_ids)}
                    score=np.asarray(archive[{'ORIGINAL':'ORIGINAL','A':'IMPROVED_BG_FIXED','C':'C','B1_OLD_KDM6':'ORIGINAL_B1_100'}[case]],dtype=np.float64)
                    score=score[[score_lookup[int(v)] for v in ids]]
                actual=data['weighted_rainc_increment_mm']+data['weighted_rainnc_increment_mm']
                require(actual.shape==(270,) and score.shape==(270,),f'{case}h{hour}: surface vector shape')
                error=np.abs(actual-score);allowed=plan['surface_abs_tolerance_mm']+plan['surface_rel_tolerance']*np.abs(score)
                require(np.all(error<=allowed),f'{case}h{hour}: surface score mismatch')
                surface_residuals.append(float(error.max()))
            previous[(case,hour)]=data

    require(len(surface_residuals)==24,'surface comparison count')
    require(receipt.get('surface_score_checks') and len(receipt['surface_score_checks'])==24,'receipt surface checks')
    # Hash every paired score NPZ (small) and confirm all current source records correspond to the plan.
    for case in CASES:
        for rec in proposal['paired_score_arrays'][case]:
            f=Path(rec['path']);require(f.is_file() and f.stat().st_size==rec['size_bytes'] and sha256(f)==rec['sha256'],f'{case} score input pin')
    summary={'snapshots':28,'cases':4,'hours_per_case':7,'points_per_snapshot':270,
             'raw_native_fields_reopened':sum(row['raw_native_fields_checked'] for row in sample_raw_counts),
             'representative_history_files_reopened':len(sample_raw_counts),
             'surface_score_comparisons':len(surface_residuals),'max_surface_score_residual_mm':max(surface_residuals),
             'dm_valid_corner_levels':sum(row['dm_valid_corner_levels'] for row in derived_counts),
             'dm_invalid_corner_levels':sum(row['dm_invalid_corner_levels'] for row in derived_counts),
             'dm_undefined_weighted_levels':sum(row['dm_undefined_weighted_levels'] for row in derived_counts)}
    result={'schema':'cp02_b1_failure_state_independent_review_v1','status':'PASS_STATE_EXTRACTION_REVIEW',
            'plan_sha256':sha256(PLAN_PATH),'extractor_sha256':sha256(ROOT/'tools/cp02_b1_failure_state.py'),
            'feature_source_sha256':sha256(ROOT/'tools/cp02_failure_state_features.py'),
            'extraction_receipt_sha256':sha256(RECEIPT_PATH),'target_receipt_sha256':sha256(plan['targets_receipt']['path']),
            'surface_fix_review_sha256':sha256(EVIDENCE/'review/state_extraction_surface_fix_review.json'),
            'output_sha256':output_hashes,'representative_source_sha256':source_hashes,
            'coverage':summary,'surface_max_residuals_mm':surface_residuals,
            'representative_raw_selection_checks':sample_raw_counts,
            'representative_derived_checks':['dry potential temperature versus separate THM','per-corner physical T from perturbation T and P+PB','per-corner liquid and phase RH','REAL64 weighted fields','raw native float32 corners','all 270 mapped indices and bilinear weights','P_TOP/DX/DY and hybrid coefficients','W and height diagnostics'],
            'limits':['The fields are history-derived Eulerian snapshots, not captured KDM6 process rates or direct physical tendencies.','No evaporation, transport, flux, causal, dry-mass, water-budget, or energy-budget claim.','The four source NetCDF files were reopened for field-by-field corner comparison; other input files were validated by frozen plan, size and execution receipt hashes.']}
    out=EVIDENCE/'review/independent_state_review.json';out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':result['status'],'review_sha256':sha256(out),'coverage':summary},indent=2))

if __name__=='__main__':main()
