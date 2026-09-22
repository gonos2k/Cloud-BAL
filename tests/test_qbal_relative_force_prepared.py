#!/usr/bin/env python3
"""Independent manufactured stream checks for the relative-force driver."""
import argparse
from pathlib import Path
import subprocess

import numpy as np
from diagnose_qbal_relative_force import read_output


def write_case(path, valid, reference=3, bad=None):
    p = np.array([100000., 70000., 5000.])
    lat = np.array([.50, .50, .501, .501])
    lon = np.array([2.0, 2.001, 2.001, 2.0])
    parameters = np.array([.6, 2., 6371000.])
    xy = np.vstack((parameters[2]*np.cos(.6)*(lon-2.),
                    parameters[2]*(np.sin(lat)-np.sin(.6))/np.cos(.6)))
    support = valid[:, :-1]*valid[:, 1:]
    layers = np.empty((4, 4, 2))
    for k, factor in enumerate((1., 2.)):
        layers[0, :, k] = factor*(3.+2e-4*xy[0]+3e-4*xy[1])
        layers[1, :, k] = factor*(1.-1e-4*xy[0]+2e-4*xy[1])
    layers[2] = layers[0]+layers[1]
    layers[3] = 1e-9
    layers[:, support == 0] = np.nan
    tri = np.array([[1, 2, 3], [1, 3, 4]], np.int32).T
    ps = np.full(4, 101000.)
    if bad == 'nan': layers[0, 0, 0] = np.nan
    if bad == 'flag': valid[0, 0] = 2
    if bad == 'underground': ps[0] = 90000.
    if bad == 'pressure': p[1] = p[0]
    if bad == 'geometry': lon[1], lat[1] = lon[0], lat[0]
    if bad == 'triangle': tri[0, 0] = 5
    if bad == 'mask': support[0, 0] = 0
    with path.open('wb') as stream:
        np.array([4, 3, 2, reference], '<i4').tofile(stream)
        for x in (parameters, p, lat, lon, ps, layers):
            np.asarray(x, '<f8').ravel(order='F').tofile(stream)
        for x in (valid, support, tri):
            np.asarray(x, '<i4').ravel(order='F').tofile(stream)
    if bad == 'suffix': path.write_bytes(path.read_bytes()+b'x')
    if bad == 'truncate': path.write_bytes(path.read_bytes()[:-1])
    return layers, xy, tri-1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executables', type=Path, nargs='+')
    parser.add_argument('--artifact-dir', type=Path, required=True)
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=False)
    count = 0
    for b, exe in enumerate(args.executables):
        for mode in ('all', 'gap', 'unknown_reference', 'isolated', 'middle_reference'):
            valid = np.ones((4, 3), np.int32)
            reference = 2 if mode == 'middle_reference' else 3
            if mode == 'gap': valid[0, 1] = 0
            if mode == 'unknown_reference': valid[:, 2] = 0
            if mode == 'isolated': valid[:, :2] = 0
            inp = args.artifact_dir/f'{b}_{mode}.bin'; out = inp.with_suffix('.out')
            layers, xy, tri = write_case(inp, valid, reference)
            with inp.with_suffix('.log').open('w') as log:
                subprocess.run([str(exe.resolve()), str(inp.resolve()), str(out.resolve())], stdout=log, stderr=log, check=True)
            result = read_output(out, 4, 3, 2)
            phi = np.full((3, 4, 3), np.nan)
            ref = reference-1
            phi[:, valid[:, ref] == 1, ref] = 0
            for k in range(ref-1, -1, -1):
                for n in range(4):
                    if valid[n, k] and valid[n, k+1]: phi[:, n, k] = phi[:, n, k+1]-9.80665*layers[:3, n, k]
            for k in range(ref+1, 3):
                for n in range(4):
                    if valid[n, k] and valid[n, k-1]: phi[:, n, k] = phi[:, n, k-1]+9.80665*layers[:3, n, k-1]
            np.testing.assert_allclose(result['phi'], phi, rtol=2e-14, atol=1e-11, equal_nan=True)
            for t in range(2):
                ids = tri[:, t]
                matrix = np.column_stack((np.ones(3), xy[:, ids].T))
                latc = np.arcsin(np.sin(.6)+xy[1, ids].mean()*np.cos(.6)/6371000.)
                for k in range(3):
                    if not np.isfinite(phi[:, ids, k]).all():
                        assert result['triangle_support'][t, k] == 0
                        continue
                    for c in range(3):
                        slope = np.linalg.solve(matrix, phi[c, ids, k])[1:]
                        expected = -slope*np.array([np.cos(.6)/np.cos(latc), np.cos(latc)/np.cos(.6)])
                        np.testing.assert_allclose(result['acceleration_en'][:, c, t, k], expected, rtol=1e-10, atol=2e-13)
            count += 1
        for bad in ('nan', 'flag', 'underground', 'pressure', 'geometry', 'triangle', 'mask', 'suffix', 'truncate', 'reference'):
            inp = args.artifact_dir/f'{b}_{bad}.bin'; out = inp.with_suffix('.out')
            write_case(inp, np.ones((4, 3), np.int32), 0 if bad == 'reference' else 3, bad)
            with inp.with_suffix('.log').open('w') as log:
                result = subprocess.run([str(exe.resolve()), str(inp.resolve()), str(out.resolve())], stdout=log, stderr=log)
            assert result.returncode != 0 and not out.exists(), bad
            count += 1
    print('PASS:', count, 'prepared relative-force cases')


if __name__ == '__main__':
    main()
