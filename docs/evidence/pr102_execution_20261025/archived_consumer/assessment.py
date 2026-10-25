"""Assess the closed PR102 calls without changing their inputs or outputs."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

import netCDF4

SOURCE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL')
sys.path.insert(0, str(SOURCE / 'tools'))
import pr102_native_ww_bound as bound
import pr99_native_consumer_replay as native
from pr99_native_consumer_metrics import read_ww

RUN = Path('/var/tmp/pr102_archived_consumer_20261025')
OUT = Path('/var/tmp/pr102_archived_consumer_assessment_20261025')
EXPECTED_HELPER = '97fc385f47ae8d6c02d1cc43e6d2a02c9974effcf2d26f78f759bfc111ac825c'

def pin(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def check(row):
    if pin(row['path'])['sha256'] != row['sha256']:
        raise ValueError(f'closed artifact changed: {row["path"]}')

if OUT.exists():
    raise ValueError('assessment directory must be fresh')
if pin(bound.__file__)['sha256'] != EXPECTED_HELPER:
    raise ValueError('reviewed helper changed')
runs = json.loads((RUN / 'runs.json').read_text())
if runs['status'] != 'COMPLETE':
    raise ValueError('native calls are not closed')
check(runs['proposal'])
proposal = json.loads(Path(runs['proposal']['path']).read_text())
composition = SOURCE / 'docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json'
dependencies = [Path(__file__), Path(bound.__file__), Path(native.__file__),
                SOURCE / 'tools/pr87_native_history.py',
                SOURCE / 'tools/pr94_cloud_response.py',
                SOURCE / 'tools/pr99_native_consumer_metrics.py', composition,
                RUN / 'runs.json', Path(runs['proposal']['path'])]
arrays, actual = {}, {}
artifacts = []
for name, record in runs['cohorts'].items():
    if record['status'] != 'COMPLETE' or record['returncode'] != 0:
        raise ValueError('a native call did not close successfully')
    for key in ('launch', 'log', 'input', 'output'):
        check(record[key])
        dependencies.append(Path(record[key]['path']))
    dependencies.append(RUN / name / 'receipt.json')
    launch = json.loads(Path(record['launch']['path']).read_text())
    check(launch['input_binary'])
    dependencies.append(Path(launch['input_binary']['path']))
    with netCDF4.Dataset(record['input']['path']) as dataset:
        dataset.set_auto_mask(False)
        arrays[name], *_ = native.native_arrays(dataset, 0)
    # Reconstruct the exact binary payload read by the closed Fortran call.
    payload = b''.join(arrays[name][key].astype('<f4').tobytes(order='F')
                       for key in native.ARRAY_ORDER)
    payload += b''.join(arrays[name][key].astype('<f4').tobytes()
                        for key in ('RDX', 'RDY'))
    if hashlib.sha256(payload).hexdigest() != launch['input_binary']['sha256']:
        raise ValueError('source reference inputs differ from the actual native call')
    actual[name] = read_ww(Path(record['output']['path']))
before = [pin(path) for path in dict.fromkeys(dependencies)]
OUT.mkdir()
check_result = bound.compare_actual(arrays['candidate'], arrays['reference_hydro'],
                                    actual['candidate'], actual['reference_hydro'],
                                    composition)
for row in before:
    check(row)
report = {
    'schema': 'pr102_native_consumer_check_v1',
    'status': 'COMPLETE' if check_result['status'] == 'PASS' else 'INCOMPLETE',
    'candidate_wrfinput_sha256': runs['cohorts']['candidate']['input']['sha256'],
    'native_consumer': bound.CONSUMER,
    'archive_member_sha256': bound.ARCHIVE_MEMBER_SHA256,
    'compiler_profile_sha256': bound.COMPILER_PROFILE_SHA256,
    'archived_consumer_executable': runs['executable'],
    'base_c2_executable_sha256': '387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a',
    'dry_mass_check': check_result,
    'artifacts': before + [runs['canonical_provenance'], runs['archive_identity']],
    'physical_approval': 'FAIL_OPEN',
    'observation_skill': 'NOT_EVALUATED',
    'scope': 'Selected stored-input calc_ww_cp comparison only. The retained callee object is byte-identical in C1/C2; strict standalone driver flags do not establish all parent callee compilation flags. This is not an acoustic dry-mass update or full WRF integration.',
    'end_utc': datetime.now(timezone.utc).isoformat(),
}
(OUT / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'dry_mass_check': check_result}, indent=2))
if report['status'] != 'COMPLETE':
    raise SystemExit(1)
