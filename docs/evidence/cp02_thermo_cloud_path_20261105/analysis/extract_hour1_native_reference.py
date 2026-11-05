#!/usr/bin/env python3
"""Extract fixed hourly native-corner rain states from pinned prior histories."""
import hashlib
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
PROTOCOL = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/state/protocol.json'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if sha(PROTOCOL) != '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690':
        raise ValueError('prior protocol differs')
    receipt = BUNDLE / 'analysis/full_capture_receipt.json'
    if sha(receipt) != 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245':
        raise ValueError('capture receipt differs')
    cells = json.loads(receipt.read_text())['native_cells_i_j_1based']
    protocol = json.loads(PROTOCOL.read_text()); arrays = {}; sources = {}
    for arm in ('B1', 'DM065'):
        pin = protocol['case_time_files'][arm]['h01']; source = Path(pin['path'])
        if source.stat().st_size != pin['size_bytes'] or sha(source) != pin['sha256']:
            raise ValueError('prior history differs')
        with Dataset(source) as ds:
            stamp = b''.join(ds.variables['Times'][0].tolist()).decode()
            if stamp != '2026-08-16_13:00:00':
                raise ValueError('wrong source time')
            for field in ('QRAIN', 'QNRAIN'):
                values = np.stack([np.asarray(ds[field][0, :, j-1, i-1], dtype='f4') for i, j in cells], axis=1)
                if values.shape != (39, 123) or not np.isfinite(values).all():
                    raise ValueError('bad extracted native state')
                arrays[arm + '_' + field] = values
        if sha(source) != pin['sha256']:
            raise ValueError('history changed during extraction')
        sources[arm] = {'path': str(source), 'sha256': pin['sha256'], 'size_bytes': pin['size_bytes']}
    target = BUNDLE / 'analysis/hour1_native_history.npz'
    receipt_path = BUNDLE / 'analysis/hour1_native_history_receipt.json'
    if target.exists() or receipt_path.exists():
        raise FileExistsError('reference already exists')
    try:
        with target.open('xb') as stream:
            np.savez_compressed(stream, **arrays)
        record = {'status': 'PASS', 'scope': 'Full 39 native levels for 123 fixed native cells, QRAIN and QNRAIN at +1 h; raw float32 values, not interpolated.',
                  'prior_protocol_sha256': sha(PROTOCOL), 'capture_receipt_sha256': sha(receipt),
                  'sources': sources, 'array_sha256': sha(target), 'size_bytes': target.stat().st_size,
                  'extractor_sha256': sha(Path(__file__))}
        with receipt_path.open('x') as stream:
            json.dump(record, stream, indent=2); stream.write('\n')
    except BaseException:
        target.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise
    print(json.dumps(record))


if __name__ == '__main__':
    main()
