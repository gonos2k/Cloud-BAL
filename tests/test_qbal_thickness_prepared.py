#!/usr/bin/env python3
"""Exercise gaps, matched support and transactionality in the compiled driver."""
import argparse
from decimal import Decimal, localcontext
from pathlib import Path
import subprocess

import numpy as np
from diagnose_qbal_thickness_attribution import read_result


def write_input(path, p, ps, state, valid):
    nn, nz = valid.shape
    with path.open('wb') as stream:
        np.array([nn, nz], '<i4').tofile(stream)
        for value in (p, ps, state):
            np.asarray(value, dtype='<f8').ravel(order='F').tofile(stream)
        np.asarray(valid, dtype='<i4').ravel(order='F').tofile(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executables', nargs='+', type=Path)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=False)
    p = np.array([100000., 95000., 80000., 60000., 5000.])
    ps = np.array([101000., 90000.])
    state = np.zeros((2, 5, 5))
    state[:, :, 0] = 300
    state[:, :, 1] = .01
    state[:, :, 2] = 302
    state[:, :, 3] = .012
    state[:, :, 4] = [0, 400, 1200, 3000, 20000]
    valid = np.array([[1, 1, 0, 1, 1], [0, 0, 1, 1, 1]], dtype='i4')
    state[valid == 0] = np.nan
    expected_mask = valid[:, :-1] * valid[:, 1:]
    good = args.artifact_dir / 'gaps.bin'
    write_input(good, p, ps, state, valid)
    checks = 0
    for number, exe in enumerate(args.executables):
        out = args.artifact_dir / f'result{number}.bin'
        run = subprocess.run([str(exe.resolve()), str(good.resolve()), str(out.resolve())], capture_output=True, text=True)
        (args.artifact_dir / f'valid{number}.log').write_text(run.stdout + run.stderr)
        assert run.returncode == 0, run.stderr
        mask, layer, column = read_result(out, 2, 5)
        assert np.array_equal(mask, expected_mask)
        assert np.isnan(layer[:, mask == 0]).all()
        with localcontext() as context:
            context.prec = 70
            d = Decimal
            alpha = 1/d('.622')-1
            for node, k in zip(*np.where(mask)):
                scale = d('287.05')/d('9.80665')*(d(str(p[k]))/d(str(p[k+1]))).ln()
                ta, qa, tf, qf = [d(float(state[node, k, j])) for j in range(4)]
                before = scale*ta*(1+alpha*qa)
                after = scale*tf*(1+alpha*qf)
                temp = scale*(1+alpha*(qa+qf)/2)*(tf-ta)
                moist = scale*alpha*(ta+tf)/2*(qf-qa)
                expected = np.array([float(x) for x in (before, after, temp, moist, after-before)])
                np.testing.assert_allclose(layer[:5, node, k], expected, rtol=3e-13, atol=1e-11)
        for node in range(2):
            np.testing.assert_allclose(column[:, node], layer[:, node, :][:, mask[node] == 1].sum(axis=1), rtol=1e-14, atol=1e-11)
        checks += 1
        for label in ('underground', 'late_nan', 'bad_flag', 'suffix'):
            changed, flags = state.copy(), valid.copy()
            if label == 'underground': flags[1, 0] = 1
            if label == 'late_nan': changed[1, -1, 2] = np.nan
            if label == 'bad_flag': flags[0, 0] = 2
            path = args.artifact_dir / f'{label}{number}.bin'
            target = args.artifact_dir / f'{label}{number}.out'
            write_input(path, p, ps, changed, flags)
            if label == 'suffix':
                with path.open('ab') as stream: stream.write(b'x')
            result = subprocess.run([str(exe.resolve()), str(path.resolve()), str(target.resolve())], capture_output=True, text=True)
            (args.artifact_dir / f'{label}{number}.log').write_text(result.stdout + result.stderr)
            assert result.returncode != 0 and not target.exists(), label
            checks += 1
    print(f'PASS: {checks} prepared-driver cases')


if __name__ == '__main__':
    main()
