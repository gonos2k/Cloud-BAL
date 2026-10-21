"""Compare immutable staged inputs; never read a running forecast history."""
from pathlib import Path
import hashlib
import json
import sys

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from pr87_native_history import _finite

RUNS = {
    'OFF': Path('/var/tmp/pr93_OFF_600s_c4_bound_20261020'),
    'COUPLED': Path('/var/tmp/pr93_COUPLED_600s_c4_bound_20261020'),
    'HYDRO': Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr94_physics_20261021/runs_on_lustre/HYDRO_600s_c4_current'),
}
NAMES = ('T', 'QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP',
         'QNCLOUD', 'QNICE', 'QNRAIN', 'QIB', 'P', 'PB', 'PH', 'PHB',
         'U', 'V', 'W', 'MU', 'MUB')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    paths, identities = {}, {}
    for arm, root in RUNS.items():
        preflight = json.loads((root / 'preflight.json').read_text())
        path = root / 'run/wrfinput_d01'
        expected = preflight['candidate_wrfinput_sha256']
        if sha(path) != expected:
            raise ValueError(f'{arm} staged input differs from preflight candidate')
        paths[arm] = path
        identities[arm] = {'path': str(path), 'sha256': expected}
    records = {}
    with netCDF4.Dataset(paths['OFF']) as off, netCDF4.Dataset(paths['COUPLED']) as coupled, netCDF4.Dataset(paths['HYDRO']) as hydro:
        datasets = {'OFF': off, 'COUPLED': coupled, 'HYDRO': hydro}
        for ds in datasets.values():
            ds.set_auto_mask(False)
        times = {arm: netCDF4.chartostring(ds['Times'][:]).tolist() for arm, ds in datasets.items()}
        if any(value != ['2026-08-16_13:00:00'] for value in times.values()):
            raise ValueError('staged inputs must each have the declared initial valid time')
        for name in NAMES:
            variables = [ds[name] for ds in datasets.values()]
            metadata = [{'dtype': str(v.dtype), 'dimensions': list(v.dimensions),
                         'shape': list(v.shape), 'units': str(getattr(v, 'units', '')),
                         'stagger': str(getattr(v, 'stagger', ''))} for v in variables]
            if not all(row == metadata[0] for row in metadata):
                raise ValueError(f'{name} metadata differs across staged inputs')
            arrays = {arm: _finite(ds, name, 0) for arm, ds in datasets.items()}
            comparisons = {}
            for label, a, b in [('HYDRO_minus_OFF', 'OFF', 'HYDRO'), ('COUPLED_minus_HYDRO', 'HYDRO', 'COUPLED')]:
                delta = arrays[b] - arrays[a]
                comparisons[label] = {'changed_values': int(np.count_nonzero(delta)),
                                      'rms': float(np.sqrt(np.mean(delta * delta))),
                                      'max_abs': float(np.max(np.abs(delta)))}
            records[name] = {'raw_variable': metadata[0], 'comparison': comparisons}
    if any(sha(paths[arm]) != row['sha256'] for arm, row in identities.items()):
        raise ValueError('immutable model input changed during comparison')
    result = {'schema': 'pr95_staged_initial_input_comparison_v1', 'identities': identities,
              'scope': 'Full raw staged wrfinput arrays before WRF initialization, not runtime history or observed skill.',
              'valid_time': '2026-08-16_13:00:00',
              'treatment': 'Continuity and force priors disabled together in HYDRO; no separate causal attribution.',
              'records': records, 'physical_approval': 'OPEN'}
    Path(__file__).with_name('initial_input_comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
