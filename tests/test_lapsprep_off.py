#!/usr/bin/env python3
"""Opt-in actual LAPSPREP OFF regression with pinned full builds and retained inputs.

This copies the supplied research case into private roots. It never runs QBAL,
changes a source input, or treats the result as native/scientific acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import netCDF4
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from compare_baseline import read_wps


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise AssertionError(f'Symlink input: {path}')
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path)
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def perturb(root, case, stamp):
    """Change one explicitly classified field cell in a private negative fixture."""
    with netCDF4.Dataset(root/f'lapsprd/lsx/{stamp}.lsx') as ds:
        ds.set_auto_maskandscale(False)
        ps = np.asarray(ds['ps'][0, 0])
    with netCDF4.Dataset(root/f'lapsprd/lq3/{stamp}.lq3', 'r+') as ds:
        ds.set_auto_maskandscale(False)
        levels = np.asarray(ds['level'][:]) * 100
        below = levels[:, None, None] > ps
        if case in ('missing_above', 'nonfinite_below', 'malformed_below'):
            k, j, i = np.argwhere(~below if case == 'missing_above' else below)[0]
            value = {'missing_above': np.float32(1e37), 'nonfinite_below': np.nan,
                     'malformed_below': -0.1}[case]
            ds['sh'][0, k, j, i] = value
            return {'field': 'SH', 'index_kji': [int(k), int(j), int(i)],
                    'case': case, 'value': str(value)}
    if case in ('missing_surface_mr', 'invalid_surface_ps'):
        with netCDF4.Dataset(root/f'lapsprd/lsx/{stamp}.lsx', 'r+') as ds:
            variable = 'mr' if case == 'missing_surface_mr' else 'ps'
            ds[variable][0, 0, 0, 0] = np.float32(1e37)
        return {'field': variable, 'index_kji': [0, 0, 0], 'case': case}
    raise AssertionError(case)


def compare_fields(left, right):
    a, b = read_wps(left), read_wps(right)
    if set(a) != set(b):
        raise AssertionError('WPS inventories differ')
    for key in a:
        if a[key][0:2] != b[key][0:2] or a[key][3] != b[key][3]:
            raise AssertionError(f'WPS metadata differs: {key}')
        np.testing.assert_array_equal(a[key][2], b[key][2], err_msg=str(key))


def run_case(source, source_hashes, build, out, name, qv, off, negative=None, stamp="262281200"):
    dest = out/name
    dest.mkdir()
    private = Path(tempfile.mkdtemp(prefix='lapsprep_off.', dir='/tmp'))
    root = private/'runroot'
    shutil.copytree(source, root)
    if inventory(root) != source_hashes:
        raise AssertionError('Input copy differs')
    control = root/'static/lapsprep.nl'
    control.write_text("&lapsprep_nl\n hotstart=.false., balance=.false.,\n"
                       " output_format='wps ', snow_thresh=1.1,\n"
                       " lwc2vapor_thresh=0.0, make_sfc_uv=.false.,\n"
                       " wind_coordinate='GRID_RELATIVE',\n"
                       f" wps_output_vapor={'.true.' if qv else '.false.'},\n/\n")
    (root/'lapsprd/lapsprep/wps').mkdir(parents=True, exist_ok=True)
    if any((root/'lapsprd/lapsprep/wps').iterdir()):
        raise AssertionError('Preexisting WPS products')
    change = perturb(root, negative, stamp) if negative else None
    before = inventory(root)
    write_json(dest/'input.pre.json', before)
    shutil.copy2(control, dest/'lapsprep.nl')
    output = private/'output.wps'
    shell = '''set -euo pipefail
. "$1/tests/intel_toolchain.sh"
ulimit -s unlimited
export OMP_NUM_THREADS=1 OMP_DYNAMIC=false OMP_STACKSIZE=128M
export LAPS_DATA_ROOT="$2" TMPDIR="$3" CLOUD_BAL_WPS_OUTPUT="$4"
unset CLOUD_BAL_SHADOW_EXPERIMENT
if [[ $6 == yes ]]; then export CLOUD_BAL_SHADOW_EXPERIMENT=OFF; fi
cd "$3"
python3 "$1/scratch/cp02_bound_followup__j5r2y3c/producer_chain/landlock_run.py" "$3" timeout 300 "$5/run_verified.sh" "$7"
'''
    command = ['bash', '-c', shell, 'off-regression', str(REPO), str(root),
               str(private), str(output), str(build), 'yes' if off else 'no', stamp]
    write_json(dest/'invocation.json', {'argv': command, 'timeout_seconds': 300,
                                       'negative_change': change})
    with (dest/'run.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    after = inventory(root)
    write_json(dest/'input.post.json', after)
    record = {'exit': result.returncode, 'output_exists': output.is_file(),
              'inputs_unchanged': before == after, 'private': str(private),
              'qv': qv, 'off': off, 'negative': negative}
    if output.is_file():
        shutil.copy2(output, dest/'output.wps')
        record['wps_sha256'] = digest(output)
    write_json(dest/'execution.json', record)
    if before != after:
        raise AssertionError('Runtime inputs changed')
    if negative:
        if result.returncode == 0 or output.exists():
            raise AssertionError(f'Negative input accepted: {name}')
    else:
        if result.returncode != 0 or not output.is_file():
            raise AssertionError(f'Positive case failed: {name}')
        if off and 'OFF canonical identity verified; host fields retained' not in (dest/'run.log').read_text():
            raise AssertionError('Actual canonical OFF equality marker missing')
    if Path(str(output)+'.shadow.nc').exists():
        raise AssertionError('OFF emitted candidate sidecar')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--stamp', default='262281200')
    parser.add_argument('--positive-only', action='store_true',
                        help='Extend an already validated negative matrix to another real case')
    parser.add_argument('--build-o0', required=True, type=Path)
    parser.add_argument('--build-o2', required=True, type=Path)
    parser.add_argument('--original-wps', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    source_hashes = inventory(args.source)
    write_json(args.output/'source.pre.json', source_hashes)
    records = {}
    for opt, build in [('O0', args.build_o0), ('O2', args.build_o2)]:
        for manifest in ('inputs', 'runtime', 'executable'):
            result = subprocess.run(['sha256sum', '-c', str(build/f'{manifest}.sha256')],
                                    capture_output=True, text=True)
            (args.output/f'{opt}.{manifest}.log').write_text(result.stdout+result.stderr)
            if result.returncode:
                raise AssertionError('Build manifest verification failed')
        for qv in (False, True):
            for off in (False, True):
                name = f'{opt}_qv{int(qv)}_{"OFF" if off else "ordinary"}'
                records[name] = run_case(args.source, source_hashes, build, args.output, name, qv, off, stamp=args.stamp)
                write_json(args.output/'runs.json', records)
            ordinary = args.output/f'{opt}_qv{int(qv)}_ordinary/output.wps'
            off_path = args.output/f'{opt}_qv{int(qv)}_OFF/output.wps'
            compare_fields(ordinary, off_path)
            if digest(ordinary) != digest(off_path):
                raise AssertionError('Same-build ordinary/OFF bytes differ')
            fields = read_wps(off_path)
            if len(fields) != (129 if qv else 108):
                raise AssertionError('Incorrect ordinary field inventory')
            if any(key[0] in ('QC','QI','QR','QS','QG','SOILHGT') for key in fields):
                raise AssertionError('Cold OFF introduced extra physical fields')
            if not qv:
                compare_fields(args.original_wps, off_path)
        no_qv = read_wps(args.output/f'{opt}_qv0_OFF/output.wps')
        qv_fields = read_wps(args.output/f'{opt}_qv1_OFF/output.wps')
        for key in no_qv:
            np.testing.assert_array_equal(no_qv[key][2], qv_fields[key][2])
        for negative in (() if args.positive_only else
                         ('missing_above','nonfinite_below','malformed_below',
                          'missing_surface_mr','invalid_surface_ps')):
            name = f'{opt}_{negative}'
            records[name] = run_case(args.source, source_hashes, build, args.output,
                                     name, False, True, negative, stamp=args.stamp)
            write_json(args.output/'runs.json', records)
    for qv in (0, 1):
        if digest(args.output/f'O0_qv{qv}_OFF/output.wps') != digest(args.output/f'O2_qv{qv}_OFF/output.wps'):
            raise AssertionError('O0/O2 OFF output bytes differ')
    if inventory(args.source) != source_hashes:
        raise AssertionError('Source tree changed')
    write_json(args.output/'RECEIPT.json', {'status':'PASS','scope':'BOUNDED_COLD_OFF_HOST_IDENTITY',
               'authority':'NO_AUTHORITY','runs':records,'original_108_records_exact':True,
               'QV_129_optional_only':True,'ordinary_OFF_byte_equal':True,'O0_O2_byte_equal':True,
               'negative_cases':0 if args.positive_only else 10,'actual_canonical_OFF_checked':True,'source_unchanged':True,
               'test_sha256':digest(Path(__file__)),'full_native_or_cp02_acceptance':False})
    print('Actual cold OFF host identity PASS')


if __name__ == '__main__':
    main()
