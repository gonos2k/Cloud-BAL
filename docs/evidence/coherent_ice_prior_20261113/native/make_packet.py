#!/usr/bin/env python3
"""Bind and package an already validated all-rank native return capture."""
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
BASE = ROOT / 'scratch/coherent_ice_prior_20261113/native'
SOURCE = ROOT / 'scratch/first_call_water_budget_20261112/Cloud-BAL'
sys.path.insert(0, str(SOURCE / 'tools'))
from propose_ice_background import grid_fingerprint, native_time


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy(source, destination):
    shutil.copy2(source, destination)
    if sha(source) != sha(destination):
        raise ValueError('copied file hash differs')


def main():
    run = BASE / 'full'
    validation_path = run / 'validation.json'
    validation = json.loads(validation_path.read_text())
    if validation['status'] != 'PASS':
        raise ValueError('native capture validation did not pass')
    input_hashes_path = BASE / 'input_hashes.json'
    input_hashes = json.loads(input_hashes_path.read_text())
    for name, digest in input_hashes.items():
        if sha(run / 'run' / name) != digest:
            raise ValueError('postrun input changed: ' + name)
    expected_probe = '92a560ea3d0829b7fa9e29e2d782d4ea4bd1b25ec5ebcc021c67de86d44f19e5'
    if sha(BASE / 'capture.py') != expected_probe:
        raise ValueError('capture script changed')
    source_path = SOURCE / 'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90'
    source_hash = sha(source_path)
    if source_hash != 'f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595':
        raise ValueError('CONTROL source changed')
    initial = run / 'run/wrfinput_d01'
    history = run / 'run/wrfout_d01_2026-08-16_12:00:00'
    baseline = ROOT / 'scratch/actual_prior_first_use_20261112/prior_forecast/run/wrfout_d01_2026-08-16_12:00:00'
    history_hash = sha(history)
    if history_hash != sha(baseline) or history_hash != '1da306199931df895a959b1746b570ee13724e86d8f6684694e00ad65c55d840':
        raise ValueError('12 UTC history differs from baseline')
    with Dataset(initial) as a, Dataset(history) as b:
        initial_time, history_time = native_time(a), native_time(b)
        initial_grid, history_grid = grid_fingerprint(a), grid_fingerprint(b)
        if (initial_time, history_time) != ('2026-08-16_06:00:00','2026-08-16_12:00:00') or initial_grid != history_grid:
            raise ValueError('native time or grid mismatch')
        if getattr(b, 'START_DATE', None) != initial_time or getattr(b, 'SIMULATION_START_DATE', None) != initial_time:
            raise ValueError('history cycle start mismatch')
    packet = run / 'packet'
    packet.mkdir(exist_ok=False)
    copy(validation_path, packet / 'run_validation.json')
    copy(input_hashes_path, packet / 'input_hashes.json')
    copy(BASE / 'capture.py', packet / 'capture.py')
    copy(BASE / 'validate_capture.py', packet / 'validate_capture.py')
    for name in ('launcher.log','start.utc','end.utc','exit.status','ldd.txt'):
        copy(run / name, packet / name)
    for i in range(8):
        copy(run / f'run/rsl.error.{i:04d}', packet / f'rsl.error.{i:04d}')
    evidence_names = ['run_validation.json','input_hashes.json','capture.py','validate_capture.py',
                      'launcher.log','start.utc','end.utc','exit.status','ldd.txt'] + [f'rsl.error.{i:04d}' for i in range(8)]
    context = {'schema':'coherent_ice_snapshot_context_v1','grid_sha256':initial_grid,'shape_zyx':[39,282,234],
               'cycle_start':initial_time,'valid_time':history_time,'target_step':1080,'time_step_seconds':20,
               'executable_sha256':input_hashes['wrf.exe'],'microphysics_source_sha256':source_hash,
               'capture_script_sha256':expected_probe,
               'mass_basis':'dry_air',
               'field_units':{'QI':'kg kg-1 dryair','QS':'kg kg-1 dryair','QV':'kg kg-1 dryair',
                              'NI':'kg-1 dryair','DEN':'kg m-3 native KDM wrapper density',
                              'TH':'K dry potential temperature','PII':'1','P':'Pa','DELZ':'m'},
               'field_basis_limitations':'Labels are caller/native source-contract and ABI interpretations, not an independent density-basis audit. TH*PII reconstructs context temperature and is not an exact inner-KDM temperature claim.',
               'actual_input_sha256':sha(initial),'actual_boundary_sha256':sha(run/'run/wrfbdy_d01'),
               'replayed_history_sha256':history_hash,'baseline_history_sha256':sha(baseline),
               'clock_evidence':'step1080*20 s and 06–12 namelist/log arithmetic; model clock was not read at breakpoint',
               'coverage_scope':'Only wrapper-return processed physical-domain intersections; no history fill or unsupported-edge values.',
               'run_verification':[{'path':name,'sha256':sha(packet/name)} for name in evidence_names]}
    (packet/'context.json').write_text(json.dumps(context,indent=2)+'\n')
    ranks=[]
    for rank in range(8):
        meta_name=f'kdm_return_rank{rank}.json';bin_name=f'kdm_return_rank{rank}.bin';gz_name=bin_name+'.gz'
        copy(run/meta_name,packet/meta_name)
        with (run/bin_name).open('rb') as raw,(packet/gz_name).open('xb') as dest:
            with gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as compressed:
                shutil.copyfileobj(raw,compressed)
        with gzip.open(packet/gz_name,'rb') as stream:
            uncompressed=hashlib.file_digest(stream,'sha256').hexdigest()
        if uncompressed!=json.loads((packet/meta_name).read_text())['binary_sha256']:
            raise ValueError('compressed rank roundtrip differs')
        ranks.append({'rank':rank,'metadata':{'path':meta_name,'sha256':sha(packet/meta_name)},
                      'binary':{'path':gz_name,'sha256':sha(packet/gz_name)},'compression':'gzip'})
    manifest={'schema':'coherent_ice_snapshot_manifest_v1','context':{'path':'context.json','sha256':sha(packet/'context.json')},'ranks':ranks}
    (packet/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('packet',packet,'manifest_sha256',sha(packet/'manifest.json'),'compressed_bytes',sum((packet/x['binary']['path']).stat().st_size for x in ranks))


if __name__=='__main__':
    main()
