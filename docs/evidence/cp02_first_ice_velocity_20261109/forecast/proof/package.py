#!/usr/bin/env python3
"""Package a source-pinned controlled-forecast comparability receipt."""
import filecmp
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[5]
PROOF = Path(__file__).resolve().parent
BUNDLE = PROOF.parent
RUNTIME = ROOT.parent / 'runtime'
B1_STAGE = Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
HISTORICAL = ROOT.parent.parent / 'b1_sedimentation_conservation_20261109/runtime/forecasts/CONSERVATIVE'
OLD_INPUTS = 'docs/evidence/six_hour_improvement_20261030/runtime/inputs.json'
OLD_PREP = 'docs/evidence/cp02_grouped_forecast_20261105/runtime/completed/SHAM_A/prepared.json'
PLAN_SHA = 'be640c73cba7d2a1bc77c88924588849b3b2a1415fedfce4faba954acc339e30'
CASES = ('CONTROL', 'ICE_FIXED')

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def identity(path):
    path = Path(path)
    return {'path': str(path), 'size_bytes': path.stat().st_size, 'sha256': sha(path)}

def base_file(path):
    return subprocess.run(['git', 'show', '37b03909b47a4316d8d3a93cd26413c8389019d2:' + path],
                          cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout

def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copy2(source, dest)
    assert sha(source) == sha(dest), str(source)

def compare(a, b):
    a, b = Path(a), Path(b)
    left, right = identity(a), identity(b)
    same = left['size_bytes'] == right['size_bytes'] and filecmp.cmp(a, b, shallow=False)
    assert same and left['sha256'] == right['sha256'], f'history differs: {a} {b}'
    return {'filename': a.name, 'historical': left, 'observed': right, 'byte_equal': same}

def main():
    plan = BUNDLE / 'launch_plan.json'
    assert sha(plan) == PLAN_SHA
    payload = json.loads(plan.read_text())
    for name, expected in payload['source_sha256'].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in payload['external_sha256'].items():
        assert sha(name) == expected, name
    tracked_input_bytes = base_file(OLD_INPUTS)
    tracked_prep_bytes = base_file(OLD_PREP)
    original = json.loads(tracked_input_bytes)['staged']
    old_prep = json.loads(tracked_prep_bytes)
    assert len(original) == 89 and old_prep['source_hashes'] == original
    assert sha(ROOT / OLD_INPUTS) == hashlib.sha256(tracked_input_bytes).hexdigest()
    current_mpi = sha('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun')
    assert current_mpi == old_prep['mpi_sha256']
    receipts = {}
    library_maps = {}
    source_hashes = {'CONTROL': 'ad255ae8b505af6b4ceebd177a54948d8bfff7fcd2c9f6d45c90122be0b57786',
                     'ICE_FIXED': 'c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2'}
    for name in CASES:
        folder = RUNTIME / 'forecasts' / name
        prep_path, run_path = folder/'prepared.json', folder/'run_receipt.json'
        driver_path = RUNTIME / f'{name}_driver_exit.json'
        prep, run, driver = (json.loads(p.read_text()) for p in (prep_path, run_path, driver_path))
        assert prep['source_hashes'] == original and prep['source_receipt_sha256'] == hashlib.sha256(tracked_input_bytes).hexdigest()
        assert prep['mpi_sha256'] == old_prep['mpi_sha256']
        assert set(prep['inputs']) == set(original) and all(prep['inputs'][k] == v for k, v in original.items() if k != 'wrf.exe')
        assert run['status'] == 'PASS' and run['exit_code'] == 0 and driver['status'] == 'PASS'
        assert driver['plan_sha256'] == PLAN_SHA and driver['source_inputs_unchanged'] is True
        assert len(driver['commands']) == 2 and all(row['exit_code'] == 0 for row in driver['commands'])
        assert run['inputs_after'] == prep['inputs'] and run['prepared_sha256'] == sha(prep_path)
        assert run['descendants_sha256'] == sha(folder/'descendants.json')
        assert len(run['histories']) == 7 and len(list(folder.glob('rsl.out.*'))) == 8
        assert all('SUCCESS COMPLETE WRF' in (folder/f'rsl.out.{i:04d}').read_text(errors='replace') for i in range(8))
        assert all(sha(B1_STAGE/key) == value for key,value in original.items())
        assert all(sha(folder/key) == value for key,value in prep['inputs'].items())
        for row in run['histories']:
            assert sha(row['path']) == row['sha256']
        build_path = RUNTIME/'native_build/variants'/name/'build_receipt.json'
        build = json.loads(build_path.read_text())
        assert sha(build_path) == payload['build_receipt_sha256'][name] == prep['build_receipt_sha256']
        assert build['status'] == 'PASS' and build['inputs_unchanged']
        assert build['source']['sha256'] == sha(build['source']['path']) == source_hashes[name]
        assert build['profile_script']['sha256'] == sha(ROOT/'tests/intel_toolchain.sh')
        assert build['compile']['exit_code'] == build['link']['exit_code'] == build['ldd']['exit_code'] == 0
        assert build['archive_member_sha256'] == build['object']['sha256']
        assert build['executable']['sha256'] == prep['inputs']['wrf.exe'] == sha(build['executable']['path'])
        assert all(sha(lib['path']) == lib['sha256'] for lib in build['ldd']['resolved_libraries'])
        library_maps[name] = {lib['path']: lib['sha256'] for lib in build['ldd']['resolved_libraries']}
        assert all(row['exit_code'] == 0 for row in build['archive_commands'])
        receipts[name] = {'build': identity(build_path), 'prepared': identity(prep_path), 'run': identity(run_path), 'driver': identity(driver_path),
                          'all_89_source_hashes_match_base': True, 'non_executable_staged_inputs_match_base': True,
                          'input_after_matches_staged': True, 'rank_success_count': 8, 'finite_history_count': 7}
    assert library_maps['CONTROL'] == library_maps['ICE_FIXED']
    rows = [compare(HISTORICAL/f'wrfout_d01_2026-08-16_{hour:02d}:00:00',
                    RUNTIME/'forecasts/CONTROL'/f'wrfout_d01_2026-08-16_{hour:02d}:00:00') for hour in range(12,19)]
    for row in rows:
        row['historical_sha256'] = row['historical']['sha256']
        row['control_sha256'] = row['observed']['sha256']
    initial = compare(HISTORICAL/'wrfout_d01_2026-08-16_12:00:00',
                      RUNTIME/'forecasts/ICE_FIXED/wrfout_d01_2026-08-16_12:00:00')
    initial['historical_sha256'] = initial['historical']['sha256']
    initial['ice_fixed_sha256'] = initial['observed']['sha256']
    assert sha(plan) == PLAN_SHA
    for name, expected in payload['source_sha256'].items():
        assert sha(ROOT / name) == expected, name
    for name in CASES:
        folder = RUNTIME/'forecasts'/name
        for source in [folder/'prepared.json', folder/'run_receipt.json', folder/'descendants.json', folder/'launcher.log',
                       *sorted(folder.glob('rsl.out.*')), *sorted(folder.glob('rsl.error.*')), *sorted(folder.glob('affinity_rank*.json'))]:
            copy(source, PROOF/name/'run'/source.name)
        for source in [RUNTIME/f'{name}_driver_exit.json', RUNTIME/f'{name}_driver.log']:
            copy(source, PROOF/name/'run'/source.name)
        build = RUNTIME/'native_build/variants'/name
        for n in ('build_receipt.json','compile.log','link.log','ldd.txt','archive_1.log','archive_2.log','archive_3.log'):
            copy(build/n, PROOF/name/'build'/n)
    result={'schema':'cp02_first_ice_velocity_comparability_v1','status':'PASS',
            'plan':identity(plan),'base_commit':'37b03909b47a4316d8d3a93cd26413c8389019d2',
            'historical_input_receipt_sha256':hashlib.sha256(tracked_input_bytes).hexdigest(),
            'historical_prepared_receipt_sha256':hashlib.sha256(tracked_prep_bytes).hexdigest(),
            'historical_mpi_sha256':old_prep['mpi_sha256'],'historical_89_source_inputs':original,
            'cases':receipts,'control_history_comparison':rows,'candidate_initial_history':initial,
            'limits':['History equality is byte-for-byte; forecast skill and conservation across full model physics require separate evaluation.',
                      'The launch plan hash was independently observed during execution and rechecked after completion; no earlier independent observation is claimed.']}
    out=PROOF/'comparability.json'
    with out.open('x') as f: json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print('PASS',out,sha(out))

if __name__ == '__main__': main()
